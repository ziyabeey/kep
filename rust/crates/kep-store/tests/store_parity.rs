//! Parity of the `store.py` port with the Python reference (ADR-0034 phase 2).
//!
//! `rust/parity/store.json` is written by `rust/parity/export_vectors.py`.
//! Each scenario replays the same operations on a fresh in-memory store and
//! compares every result and the final content of every table, so the
//! stored JSON text must match Python's byte for byte.

use kep_canon::canonical_json;
use kep_core::Query;
use kep_store::{Store, StoreError, TABLES};
use rusqlite::types::ValueRef;
use serde_json::{Value, json};

fn vectors() -> Value {
    let path = concat!(env!("CARGO_MANIFEST_DIR"), "/../../parity/store.json");
    serde_json::from_str(&std::fs::read_to_string(path).expect("vector file")).expect("valid JSON")
}

fn outcome(r: Result<Value, StoreError>) -> Value {
    match r {
        Ok(v) => json!({ "ok": v }),
        Err(e) => json!({ "raises": e.name() }),
    }
}

fn run(store: &mut Store, op: &Value) -> Value {
    let s = |k: &str| op[k].as_str().expect("string field");
    outcome(match s("op") {
        "ingest" => store.ingest(&op["record"]).map(|r| json!(r.as_str())),
        "get" => store.get(s("id")).map(|r| r.unwrap_or(Value::Null)),
        "queue_push" => store
            .queue_push(
                s("object_id"),
                s("user_key"),
                op["consent"].as_bool().unwrap(),
            )
            .map(Value::from),
        "preview" => Query::from_json(&op["query"])
            .map_err(StoreError::Py)
            .and_then(|q| store.preview_dispatch(s("push_id"), &q)),
        "log" => store
            .log_decision(&op["query"], &op["decision"])
            .map(Value::from),
        "counts" => store.counts(),
        other => panic!("unknown op {other}"),
    })
}

fn dump(store: &Store) -> Value {
    let db = store.connection();
    let mut out = serde_json::Map::new();
    for t in TABLES {
        let mut stmt = db
            .prepare(&format!("SELECT * FROM {t} ORDER BY rowid"))
            .unwrap();
        let n = stmt.column_count();
        let rows: Vec<Value> = stmt
            .query_map([], |row| {
                Ok(Value::Array(
                    (0..n)
                        .map(|i| match row.get_ref(i).unwrap() {
                            ValueRef::Null => Value::Null,
                            ValueRef::Integer(v) => json!(v),
                            ValueRef::Text(t) => json!(std::str::from_utf8(t).unwrap()),
                            other => panic!("unexpected column type {other:?}"),
                        })
                        .collect(),
                ))
            })
            .unwrap()
            .map(Result::unwrap)
            .collect();
        out.insert(t.to_owned(), Value::Array(rows));
    }
    Value::Object(out)
}

#[test]
fn scenarios_match() {
    let v = vectors();
    let scenarios = v["scenarios"].as_array().unwrap();
    assert!(!scenarios.is_empty());
    let mut failures = Vec::new();
    for sc in scenarios {
        let mut store = Store::in_memory().unwrap();
        let results: Vec<Value> = sc["ops"]
            .as_array()
            .unwrap()
            .iter()
            .map(|op| run(&mut store, op))
            .collect();
        let got = json!({"results": results, "tables": dump(&store)});
        let expected = &sc["expect"];
        // Byte-exact for stored text: compare the tables as plain JSON values.
        if canonical_json(&got) != canonical_json(expected) {
            failures.push(format!(
                "{}:\n expected {expected}\n got      {got}",
                sc["name"]
            ));
        }
    }
    assert!(
        failures.is_empty(),
        "{} of {} scenarios differ:\n{}",
        failures.len(),
        scenarios.len(),
        failures.join("\n")
    );
}
