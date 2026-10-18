//! Parity with the Python reference (ADR-0034).
//!
//! `rust/parity/availability.json` is written by `rust/parity/export_vectors.py`
//! from `labs/core`. Every case must match exactly, except the few listed in
//! `KNOWN_GAPS`, each with its reason and the direction of the difference.

use chrono::{DateTime, FixedOffset};
use kep_canon::{canonical_json, stable_hash};
use kep_core::availability::{field_is_fresh, intervals, minute, opening_status};
use kep_core::isotime::{parse_iso, parse_reference_timestamp};
use serde_json::{Value, json};

/// Cases where Rust deliberately differs from Python. Each one is stricter
/// than Python, so a timestamp or clock time is rejected instead of trusted.
const KNOWN_GAPS: &[(&str, &str)] = &[
    ("isotime", "iso_'20261010T175000+0300'"), // basic date format
    ("isotime", "iso_'2026-W41-6T17:50:00+03:00'"), // ISO week date
    ("isotime", "iso_'2026-10-10T175000+03:00'"), // basic time format
    ("isotime", "iso_'2026-10-10T17:50:00 +03:00'"), // space before offset
    ("isotime", "iso_'2026-10-10T17:50:00+03:00:30.5'"), // fractional-second offset
    ("minute", "minute_'٠٩:٣٠'_False"),        // non-ASCII digits in int()
    ("minute", "minute_'٠٩:٣٠'_True"),
];

fn vectors() -> Value {
    let path = concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../parity/availability.json"
    );
    serde_json::from_str(&std::fs::read_to_string(path).expect("vector file")).expect("valid JSON")
}

fn at(text: &str) -> DateTime<FixedOffset> {
    parse_iso(text)
        .and_then(|t| t.aware())
        .unwrap_or_else(|| panic!("aware timestamp: {text}"))
}

fn to_outcome<T: Into<Value>>(r: Result<T, kep_core::PyError>) -> Value {
    match r {
        Ok(v) => json!({ "ok": v.into() }),
        Err(e) => json!({ "raises": e.name() }),
    }
}

/// Runs every case of `section`, returning (passed, gaps_seen, failures).
fn check(section: &str, actual: impl Fn(&Value) -> Value) {
    let data = vectors();
    let cases = data[section].as_array().expect("section");
    assert!(!cases.is_empty(), "{section} has no cases");
    let mut failures = Vec::new();
    for case in cases {
        let name = case["name"].as_str().unwrap();
        let got = actual(case);
        let gap = KNOWN_GAPS.contains(&(section, name));
        let expected = &case["expect"];
        match (got == *expected, gap) {
            (true, false) => {}
            (true, true) => failures.push(format!(
                "{name}: listed as a gap but now matches; remove it"
            )),
            (false, true) => {}
            (false, false) => failures.push(format!("{name}: expected {expected}, got {got}")),
        }
    }
    assert!(
        failures.is_empty(),
        "{section} parity failures:\n{}",
        failures.join("\n")
    );
}

#[test]
fn canonical_json_and_hash() {
    let data = vectors();
    let mut failures = Vec::new();
    for case in data["canon"].as_array().unwrap() {
        let name = case["name"].as_str().unwrap();
        let value: Value = match case.get("json") {
            Some(Value::String(literal)) => serde_json::from_str(literal).unwrap(),
            _ => case["value"].clone(),
        };
        let text = canonical_json(&value);
        if text != case["canonical"].as_str().unwrap() {
            failures.push(format!(
                "{name}: expected {}, got {text}",
                case["canonical"]
            ));
        }
        if let Some(Value::String(h)) = case.get("sha256") {
            if *h != stable_hash(&value) {
                failures.push(format!("{name}: hash differs"));
            }
        }
    }
    assert!(
        failures.is_empty(),
        "canon parity failures:\n{}",
        failures.join("\n")
    );
}

#[test]
fn iso_timestamps() {
    check("isotime", |c| {
        match parse_reference_timestamp(c["text"].as_str().unwrap()) {
            Some(t) => json!({ "ok": t.python_isoformat() }),
            None => json!({ "raises": "ValueError" }),
        }
    });
}

#[test]
fn minute_parsing() {
    check("minute", |c| {
        to_outcome(minute(&c["text"], c["end"].as_bool().unwrap()))
    });
}

#[test]
fn interval_parsing() {
    check("intervals", |c| {
        to_outcome(intervals(&c["raw"]).map(|v| {
            v.into_iter()
                .map(|(a, b)| json!([a, b]))
                .collect::<Vec<_>>()
        }))
    });
}

#[test]
fn opening_status_parity() {
    check(
        "opening_status",
        |c| json!({ "ok": opening_status(&c["hours"], &at(c["at"].as_str().unwrap())).as_str() }),
    );
}

#[test]
fn field_freshness_parity() {
    check("field_is_fresh", |c| {
        to_outcome(field_is_fresh(
            &c["record"],
            c["field"].as_str().unwrap(),
            &at(c["at"].as_str().unwrap()),
            c["max_hours"].as_f64().unwrap(),
        ))
    });
}
