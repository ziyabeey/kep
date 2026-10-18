//! SQLite reference store (`labs/core/kepcore/store.py`): idempotent ingest,
//! ordered updates and a transactional outbox.
//!
//! No external database, production source, social account or push service
//! is used. The schema is the reference's, so either side can open a file the
//! other wrote, and stored JSON text is byte-identical to Python's.
//!
//! Rust requires `id` to be a string, and `source_id`, `source_url`,
//! `source_record_hash` and `source_observed_at` to be strings or null.
//! Python's sqlite3 binding would store other scalars as text; Rust rejects
//! them with `TypeError` instead.

use kep_canon::{python_json_dumps, stable_hash};
use kep_core::isotime::istanbul_dt;
use kep_core::pyval::{PyError, py_eq, truthy};
use kep_core::{Query, decide};
use rusqlite::{Connection, OptionalExtension, params};
use serde_json::{Map, Value, json};
use std::path::Path;

const SCHEMA: &str = "
        CREATE TABLE IF NOT EXISTS objects (
          id TEXT PRIMARY KEY, revision INTEGER NOT NULL,
          content_hash TEXT NOT NULL, record_json TEXT NOT NULL,
          source_observed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS observations (
          observation_id TEXT PRIMARY KEY, object_id TEXT NOT NULL REFERENCES objects(id),
          source_id TEXT NOT NULL, source_url TEXT NOT NULL,
          source_record_hash TEXT NOT NULL, observation_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS outbox (
          event_id TEXT PRIMARY KEY, object_id TEXT NOT NULL REFERENCES objects(id),
          revision INTEGER NOT NULL, event_type TEXT NOT NULL, payload_json TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'pending'
        );
        CREATE TABLE IF NOT EXISTS push_queue (
          push_id TEXT PRIMARY KEY, object_id TEXT NOT NULL REFERENCES objects(id),
          revision INTEGER NOT NULL, user_key TEXT NOT NULL, status TEXT NOT NULL,
          consent INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS decisions (
          decision_id TEXT PRIMARY KEY, query_json TEXT NOT NULL,
          decision_json TEXT NOT NULL
        );
        ";

/// Table names in the order `counts()` reports them.
pub const TABLES: [&str; 5] = [
    "objects",
    "observations",
    "outbox",
    "push_queue",
    "decisions",
];

/// What went wrong: an exception the reference would raise, or SQLite itself.
#[derive(Debug)]
pub enum StoreError {
    Py(PyError),
    Sqlite(rusqlite::Error),
}

impl From<PyError> for StoreError {
    fn from(e: PyError) -> Self {
        StoreError::Py(e)
    }
}

impl From<rusqlite::Error> for StoreError {
    fn from(e: rusqlite::Error) -> Self {
        match e.sqlite_error_code() {
            Some(rusqlite::ErrorCode::ConstraintViolation) => {
                StoreError::Py(PyError::IntegrityError)
            }
            _ => StoreError::Sqlite(e),
        }
    }
}

impl StoreError {
    /// The Python exception class name, for parity checks.
    pub fn name(&self) -> String {
        match self {
            StoreError::Py(e) => e.name().to_owned(),
            StoreError::Sqlite(e) => format!("sqlite: {e}"),
        }
    }
}

pub type Result<T> = std::result::Result<T, StoreError>;

/// Result of [`Store::ingest`].
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Ingest {
    Inserted,
    Updated,
    Unchanged,
    IgnoredOlder,
}

impl Ingest {
    pub fn as_str(self) -> &'static str {
        match self {
            Ingest::Inserted => "inserted",
            Ingest::Updated => "updated",
            Ingest::Unchanged => "unchanged",
            Ingest::IgnoredOlder => "ignored_older",
        }
    }
}

/// A stored object row.
struct ObjectRow {
    revision: i64,
    content_hash: String,
    record_json: String,
    source_observed_at: Option<String>,
}

/// `record[key]` for a TEXT column: KeyError if missing, `None` if null.
fn text_field<'a>(record: &'a Map<String, Value>, key: &str) -> Result<Option<&'a str>> {
    match record.get(key) {
        None => Err(PyError::KeyError.into()),
        Some(Value::Null) => Ok(None),
        Some(Value::String(s)) => Ok(Some(s)),
        Some(_) => Err(PyError::TypeError.into()),
    }
}

/// `core.dt(value)` for a JSON value: `.replace` fails on non-strings.
fn dt_value(value: &Value) -> Result<kep_core::isotime::IstDateTime> {
    let text = value.as_str().ok_or(PyError::AttributeError)?;
    Ok(istanbul_dt(text)?)
}

/// The reference SQLite store.
pub struct Store {
    db: Connection,
}

impl Store {
    /// `Store(':memory:')`.
    pub fn in_memory() -> Result<Store> {
        Store::init(Connection::open_in_memory()?)
    }

    /// `Store(path)`.
    pub fn open(path: &Path) -> Result<Store> {
        Store::init(Connection::open(path)?)
    }

    fn init(db: Connection) -> Result<Store> {
        db.execute_batch("PRAGMA foreign_keys=ON")?;
        db.execute_batch(SCHEMA)?;
        Ok(Store { db })
    }

    /// The underlying connection, for inspection.
    pub fn connection(&self) -> &Connection {
        &self.db
    }

    fn object_row(&self, id: &str) -> Result<Option<ObjectRow>> {
        Ok(self
            .db
            .query_row(
                "SELECT revision, content_hash, record_json, source_observed_at FROM objects WHERE id=?",
                [id],
                |row| {
                    Ok(ObjectRow {
                        revision: row.get(0)?,
                        content_hash: row.get(1)?,
                        record_json: row.get(2)?,
                        source_observed_at: row.get(3)?,
                    })
                },
            )
            .optional()?)
    }

    /// `get()`: the stored record plus `_revision`, or `None`.
    pub fn get(&self, object_id: &str) -> Result<Option<Value>> {
        let Some(row) = self.object_row(object_id)? else {
            return Ok(None);
        };
        let mut record: Value =
            serde_json::from_str(&row.record_json).map_err(|_| PyError::ValueError)?;
        let map = record.as_object_mut().ok_or(PyError::TypeError)?;
        map.insert("_revision".to_owned(), json!(row.revision));
        Ok(Some(record))
    }

    /// `ingest()`: insert or update one record with its observation, outbox
    /// event and push invalidation in one transaction.
    pub fn ingest(&mut self, record: &Value) -> Result<Ingest> {
        let record = record.as_object().ok_or(PyError::AttributeError)?; // list.get
        if record.get("rights_scope").and_then(Value::as_str) != Some("open_attribution") {
            return Err(PyError::PermissionError.into()); // unapproved source use
        }
        let record: Map<String, Value> = record
            .iter()
            .filter(|(k, _)| !k.starts_with('_'))
            .map(|(k, v)| (k.clone(), v.clone()))
            .collect();
        let value = Value::Object(record);
        let raw = python_json_dumps(&value, true, false);
        let h = stable_hash(&value);
        let Value::Object(record) = value else {
            unreachable!()
        };
        let id = match record.get("id") {
            None => return Err(PyError::KeyError.into()),
            Some(Value::String(s)) => s.clone(),
            Some(_) => return Err(PyError::TypeError.into()),
        };
        let old = self.object_row(&id)?;
        let now = record.get("source_observed_at").unwrap_or(&Value::Null);
        if let Some(old) = &old {
            if old.content_hash == h {
                return Ok(Ingest::Unchanged);
            }
            let oldrecord: Value =
                serde_json::from_str(&old.record_json).map_err(|_| PyError::ValueError)?;
            let old_source = oldrecord.get("source_id").ok_or(PyError::KeyError)?;
            let new_source = record.get("source_id").ok_or(PyError::KeyError)?;
            if !py_eq(old_source, new_source) {
                // Cross-source overwrite forbidden; reconcile claims first.
                return Err(PyError::ValueError.into());
            }
            if let Some(prev) = old.source_observed_at.as_deref().filter(|p| !p.is_empty()) {
                // `not now or dt(now) < dt(prev)`, evaluated in that order.
                if !truthy(Some(now)) {
                    return Ok(Ingest::IgnoredOlder);
                }
                let new_at = dt_value(now)?;
                let prev = istanbul_dt(prev)?;
                if new_at < prev {
                    return Ok(Ingest::IgnoredOlder);
                }
                if new_at == prev {
                    // Same timestamp, incompatible contents: no silent last-write-wins.
                    return Err(PyError::ValueError.into());
                }
            }
        }
        let observed_at = match now {
            Value::Null => None,
            Value::String(s) => Some(s.clone()),
            _ => return Err(PyError::TypeError.into()),
        };
        // KeyError as the reference builds the row tuple. A null here is bound
        // as NULL and `INSERT OR IGNORE` then skips the observation row, as in
        // Python (OR IGNORE also covers NOT NULL violations).
        let source_id = text_field(&record, "source_id")?;
        let source_url = text_field(&record, "source_url")?;
        let source_record_hash = text_field(&record, "source_record_hash")?;
        let rev = old.as_ref().map_or(1, |o| o.revision + 1);
        let cancelled = record.get("lifecycle").and_then(Value::as_str) == Some("cancelled");
        let event_type = if cancelled {
            "event.cancelled"
        } else {
            "object.updated"
        };
        let payload = python_json_dumps(
            &json!({"id": id, "revision": rev, "source_record_hash": source_record_hash}),
            false,
            true,
        );
        let tx = self.db.transaction()?;
        tx.execute(
            "INSERT INTO objects VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET \
             revision=excluded.revision,content_hash=excluded.content_hash,\
             record_json=excluded.record_json,source_observed_at=excluded.source_observed_at",
            params![id, rev, h, raw, observed_at],
        )?;
        tx.execute(
            "INSERT OR IGNORE INTO observations VALUES (?,?,?,?,?,?)",
            params![
                stable_hash(&json!([id, h])),
                id,
                source_id,
                source_url,
                source_record_hash,
                raw
            ],
        )?;
        tx.execute(
            "INSERT INTO outbox VALUES (?,?,?,?,?,?)",
            params![
                stable_hash(&json!([id, rev])),
                id,
                rev,
                event_type,
                payload,
                "pending"
            ],
        )?;
        tx.execute(
            "UPDATE push_queue SET status=? WHERE object_id=? AND status='pending'",
            params![if cancelled { "cancelled" } else { "superseded" }, id],
        )?;
        tx.commit()?;
        Ok(if old.is_some() {
            Ingest::Updated
        } else {
            Ingest::Inserted
        })
    }

    /// `queue_push()`: queue a candidate, not permission to dispatch; fresh
    /// eligibility is checked at dispatch.
    pub fn queue_push(&mut self, object_id: &str, user_key: &str, consent: bool) -> Result<String> {
        if !consent {
            return Err(PyError::PermissionError.into()); // push not authorized
        }
        let r = self.get(object_id)?.ok_or(PyError::KeyError)?;
        if r.get("lifecycle").and_then(Value::as_str) == Some("cancelled") {
            return Err(PyError::ValueError.into()); // cannot queue cancelled event
        }
        let rev = &r["_revision"];
        let key = stable_hash(&json!([object_id, rev, user_key]));
        let tx = self.db.transaction()?;
        tx.execute(
            "INSERT OR IGNORE INTO push_queue VALUES (?,?,?,?,?,?)",
            params![key, object_id, rev.as_i64(), user_key, "pending", 1],
        )?;
        tx.commit()?;
        Ok(key)
    }

    /// `preview_dispatch()`: revalidate a queued candidate. Never sends a
    /// network notification.
    pub fn preview_dispatch(&self, push_id: &str, query: &Query) -> Result<Value> {
        let (object_id, status, revision): (String, String, i64) = self
            .db
            .query_row(
                "SELECT object_id, status, revision FROM push_queue WHERE push_id=?",
                [push_id],
                |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
            )
            .optional()?
            .ok_or(PyError::KeyError)?;
        let r = self.get(&object_id)?;
        let invalidated = json!({"send": false, "reason": "INVALIDATED_OR_SUPERSEDED"});
        // `p['status'] != 'pending'` short-circuits before `r['_revision']`,
        // so a missing object only raises TypeError for a pending push.
        if status != "pending" {
            return Ok(invalidated);
        }
        let r = r.ok_or(PyError::TypeError)?;
        if Some(revision) != r["_revision"].as_i64() {
            return Ok(invalidated);
        }
        if !query.proactive || !query.push_opt_in {
            return Ok(json!({"send": false, "reason": "PUSH_QUERY_REQUIRES_CURRENT_CONSENT"}));
        }
        let d = decide(&[r], query, "query_aware")?;
        Ok(json!({"send": !d.selected.is_empty(), "reason": d.action, "network_send": false}))
    }

    /// `log_decision()`: store a query and its decision once.
    pub fn log_decision(&mut self, query: &Value, decision: &Value) -> Result<String> {
        let key = stable_hash(&json!([query, decision]));
        let tx = self.db.transaction()?;
        tx.execute(
            "INSERT OR IGNORE INTO decisions VALUES (?,?,?)",
            params![
                key,
                python_json_dumps(query, false, false),
                python_json_dumps(decision, false, false)
            ],
        )?;
        tx.commit()?;
        Ok(key)
    }

    /// `counts()`: rows per table.
    pub fn counts(&self) -> Result<Value> {
        let mut out = Map::new();
        for t in TABLES {
            let n: i64 = self
                .db
                .query_row(&format!("SELECT count(*) FROM {t}"), [], |row| row.get(0))?;
            out.insert(t.to_owned(), json!(n));
        }
        Ok(Value::Object(out))
    }
}
