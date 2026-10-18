//! Catalog normalization from `core.py` (`normalize_events`, `normalize_places`,
//! `load_catalog`). Records stay JSON objects, as Python keeps them as dicts.

use crate::isotime::{isoformat_tz, istanbul_dt};
use crate::pyval::{PyError, pyindex, pystr, python_str};
use crate::text::{collapse_whitespace, py_strip};
use kep_canon::stable_hash;
use serde_json::{Map, Value, json};
use std::collections::HashSet;
use std::path::Path;

/// One catalog record (a Python dict).
pub type Record = Map<String, Value>;

const AMBIGUOUS_VENUES: [&str; 2] = ["İlçelerde Etkinlik Alanları", "İlçe Çok Amaçlı Salonlar"];

/// `categories.get(raw['Tur'], 'other')`; a list or dict key is unhashable.
fn category(tur: &Value) -> Result<&'static str, PyError> {
    Ok(match tur {
        Value::Array(_) | Value::Object(_) => return Err(PyError::TypeError),
        Value::String(s) if s == "SİNEMA" => "cinema",
        Value::String(s) if s == "KONSER" => "music",
        Value::String(s) if s == "SERGİ" => "exhibition",
        _ => "other",
    })
}

/// İzmir open-data events into catalog rows. Errors as the reference raises.
pub fn normalize_events(envelope: &Value) -> Result<Vec<Value>, PyError> {
    let env = envelope.as_object().ok_or(PyError::TypeError)?;
    let meta = pyindex(env, "meta")?
        .as_object()
        .ok_or(PyError::TypeError)?;
    let records = pyindex(env, "records")?
        .as_array()
        .ok_or(PyError::TypeError)?;
    let mut seen: HashSet<String> = HashSet::new();
    let mut out = Vec::with_capacity(records.len());
    for raw_value in records {
        let raw = raw_value.as_object().ok_or(PyError::TypeError)?;
        let key = format!("izmir_event:{}", python_str(pyindex(raw, "Id")?));
        if !seen.insert(key.clone()) {
            return Err(PyError::ValueError); // duplicate source ID
        }
        let start = istanbul_dt(pystr(pyindex(raw, "EtkinlikBaslamaTarihi")?)?)?;
        let end = istanbul_dt(pystr(pyindex(raw, "EtkinlikBitisTarihi")?)?)?;
        let mut flags: Vec<&str> = Vec::new();
        if end < start {
            return Err(PyError::ValueError); // backwards event interval
        }
        let equal = end == start;
        if equal {
            flags.push("END_EQUALS_START_DURATION_UNKNOWN");
        }
        let multi = end.date_naive() > start.date_naive();
        let tur = pyindex(raw, "Tur")?;
        let kind = if tur.as_str() == Some("SERGİ") && multi {
            "exhibition_range"
        } else if multi {
            "program_range"
        } else {
            "single_occurrence"
        };
        if kind == "program_range" {
            flags.push("SESSION_TIMES_NOT_ENUMERATED");
        }
        if kind == "exhibition_range" {
            flags.push("DAILY_OPENING_HOURS_UNKNOWN");
        }
        let venue = py_strip(pystr(pyindex(raw, "EtkinlikMerkezi")?)?).to_owned();
        let ambiguous = AMBIGUOUS_VENUES.contains(&venue.as_str());
        if ambiguous {
            flags.push("VENUE_UNRESOLVED");
        }
        let free = raw.get("UcretsizMi").cloned().unwrap_or(Value::Null);
        if !free.is_boolean() {
            flags.push("FREE_FLAG_UNKNOWN");
        }
        // A false free flag does NOT encode a paid amount.
        let price = if free == Value::Bool(true) {
            json!(0)
        } else {
            Value::Null
        };
        if price.is_null() {
            flags.push("PRICE_AMOUNT_UNKNOWN");
        }
        let m = |k: &str| pyindex(meta, k).cloned();
        let row = json!({
            "id": key,
            "kind": "event",
            "event_kind": kind,
            "name": collapse_whitespace(pystr(pyindex(raw, "Adi")?).map_err(|_| PyError::AttributeError)?),
            "city": m("source_city")?,
            "category": category(tur)?,
            "starts_at": isoformat_tz(&start),
            "ends_at": if equal { Value::Null } else { Value::String(isoformat_tz(&end)) },
            "declared_end": isoformat_tz(&end),
            "time_zone": "Europe/Istanbul",
            "lifecycle": "scheduled_claim",
            "evidence_status": "source_recorded",
            "origin_live_verified": m("origin_live_verified")?,
            "source_observed_at": m("source_observed_at")?,
            "acquired_date": m("acquired_date")?,
            "source_id": m("source_id")?,
            "source_url": m("source_url")?,
            "source_item_id": python_str(pyindex(raw, "Id")?),
            "source_record_hash": stable_hash(raw_value),
            "publisher_root": "izmir_municipality",
            "rights_scope": "open_attribution",
            "license": m("license")?,
            "venue": venue,
            "venue_precision": if ambiguous { "unresolved" } else { "named_only" },
            "lat": null,
            "lon": null,
            "price": price,
            "currency": "TRY",
            "source_claim_free": free,
            "opening_hours": null,
            "crowd": null,
            "sales_link": raw.get("BiletSatisLinki").cloned().unwrap_or(Value::Null),
            "source_slug": pyindex(raw, "EtkinlikUrl")?.clone(),
            "flags": flags,
            "synthetic": false,
        });
        out.push(row);
    }
    Ok(out)
}

/// Wikimedia/Wikidata places into catalog rows.
pub fn normalize_places(envelope: &Value) -> Result<Vec<Value>, PyError> {
    let env = envelope.as_object().ok_or(PyError::TypeError)?;
    let records = pyindex(env, "records")?
        .as_array()
        .ok_or(PyError::TypeError)?;
    records
        .iter()
        .map(|p| {
            let mut row = p.as_object().ok_or(PyError::TypeError)?.clone();
            let updates = json!({
                "kind": "place",
                "rights_scope": "open_attribution",
                "publisher_root": "wikimedia",
                "evidence_status": "source_recorded",
                "lifecycle": "listed_claim",
                "price": null,
                "currency": "TRY",
                "synthetic": false,
                "flags": ["PRICE_AMOUNT_UNKNOWN", "OPENING_HOURS_UNKNOWN", "CROWD_UNKNOWN"],
                "source_record_hash": stable_hash(p),
            });
            for (k, v) in updates.as_object().expect("object literal") {
                row.insert(k.clone(), v.clone()); // existing keys keep their position, like dict.update
            }
            Ok(Value::Object(row))
        })
        .collect()
}

/// Why the lab catalog could not be loaded.
#[derive(Debug)]
pub enum CatalogError {
    Io(std::io::Error),
    Json(serde_json::Error),
    Invalid(PyError),
}

impl std::fmt::Display for CatalogError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            CatalogError::Io(e) => write!(f, "{e}"),
            CatalogError::Json(e) => write!(f, "{e}"),
            CatalogError::Invalid(e) => write!(f, "invalid catalog data ({})", e.name()),
        }
    }
}

impl std::error::Error for CatalogError {}

fn read_json(path: &Path) -> Result<Value, CatalogError> {
    let text = std::fs::read_to_string(path).map_err(CatalogError::Io)?;
    serde_json::from_str(&text).map_err(CatalogError::Json)
}

/// `load_catalog()`: the lab's İzmir events followed by İstanbul places.
/// `lab_root` is the `labs/core` directory.
pub fn load_catalog(lab_root: &Path) -> Result<Vec<Value>, CatalogError> {
    let raw = lab_root.join("data/raw");
    let mut rows = normalize_events(&read_json(&raw.join("izmir_events_excerpt.json"))?)
        .map_err(CatalogError::Invalid)?;
    rows.extend(
        normalize_places(&read_json(&raw.join("istanbul_places_excerpt.json"))?)
            .map_err(CatalogError::Invalid)?,
    );
    Ok(rows)
}
