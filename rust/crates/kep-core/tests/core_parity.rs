//! Parity of the `core.py` port with the Python reference (ADR-0034).
//!
//! `rust/parity/core.json` is written by `rust/parity/export_vectors.py`.
//! Values are compared through canonical JSON, so `1` and `1.0` still differ
//! but key order does not; the CLI cases also check the exact pretty output.

use kep_canon::{canonical_json, python_json_pretty};
use kep_core::decision::{check_model_selection, reconcile_claims, temporal_state};
use kep_core::distance::{haversine_km, round4};
use kep_core::isotime::{isoformat_tz, istanbul_dt};
use kep_core::text::fold;
use kep_core::{PyError, Query, catalog, decide, load_catalog};
use serde_json::{Value, json};
use std::path::PathBuf;
use std::sync::OnceLock;

fn lab_root() -> PathBuf {
    PathBuf::from(concat!(env!("CARGO_MANIFEST_DIR"), "/../../../labs/core"))
}

fn vectors() -> &'static Value {
    static V: OnceLock<Value> = OnceLock::new();
    V.get_or_init(|| {
        let path = concat!(env!("CARGO_MANIFEST_DIR"), "/../../parity/core.json");
        serde_json::from_str(&std::fs::read_to_string(path).expect("vector file"))
            .expect("valid JSON")
    })
}

fn lab_catalog() -> &'static Vec<Value> {
    static C: OnceLock<Vec<Value>> = OnceLock::new();
    C.get_or_init(|| load_catalog(&lab_root()).expect("lab catalog"))
}

fn outcome(r: Result<Value, PyError>) -> Value {
    match r {
        Ok(v) => json!({ "ok": v }),
        Err(e) => json!({ "raises": e.name() }),
    }
}

fn check(section: &str, actual: impl Fn(&Value) -> Value) {
    let cases = vectors()[section].as_array().expect("section");
    assert!(!cases.is_empty(), "{section} has no cases");
    let failures: Vec<String> = cases
        .iter()
        .filter_map(|case| {
            let got = actual(case);
            let expected = &case["expect"];
            (canonical_json(&got) != canonical_json(expected))
                .then(|| format!("{}: expected {expected}, got {got}", case["name"]))
        })
        .collect();
    assert!(
        failures.is_empty(),
        "{section}: {} of {} differ:\n{}",
        failures.len(),
        cases.len(),
        failures.join("\n")
    );
}

#[test]
fn fold_matches() {
    check("fold", |c| json!(fold(c["text"].as_str().unwrap())));
}

#[test]
fn haversine_matches_after_rounding() {
    // georust's evaluation order can differ from Python's in the last bit;
    // KEP reports round(d, 4), which must match exactly.
    for case in vectors()["haversine"].as_array().unwrap() {
        let a: Vec<f64> = case["args"]
            .as_array()
            .unwrap()
            .iter()
            .map(|v| v.as_f64().unwrap())
            .collect();
        let got = haversine_km(a[0], a[1], a[2], a[3]);
        let expected = &case["expect"];
        match got {
            Err(e) => assert_eq!(expected["raises"], e.name(), "{}", case["name"]),
            Ok(d) => {
                let py = expected["ok"].as_f64().unwrap();
                assert_eq!(
                    round4(d),
                    expected["rounded"].as_f64().unwrap(),
                    "{}",
                    case["name"]
                );
                assert!(
                    (d - py).abs() <= 1e-12 * py.abs().max(1.0),
                    "{}: {d} vs {py}",
                    case["name"]
                );
            }
        }
    }
}

#[test]
fn dt_matches() {
    check("dt", |c| {
        outcome(istanbul_dt(c["text"].as_str().unwrap()).map(|d| json!(isoformat_tz(&d))))
    });
}

#[test]
fn catalog_matches() {
    let expected = &vectors()["catalog"];
    let got = Value::Array(lab_catalog().clone());
    assert_eq!(canonical_json(&got), canonical_json(expected));
    // Row key order follows the Python dicts too.
    for (g, e) in lab_catalog().iter().zip(expected.as_array().unwrap()) {
        let gk: Vec<&String> = g.as_object().unwrap().keys().collect();
        let ek: Vec<&String> = e.as_object().unwrap().keys().collect();
        assert_eq!(gk, ek, "key order of {}", g["id"]);
    }
}

#[test]
fn normalize_errors_match() {
    check("normalize_errors", |c| {
        outcome(catalog::normalize_events(&c["envelope"]).map(Value::Array))
    });
}

#[test]
fn query_validation_matches() {
    check("query", |c| {
        outcome(Query::from_json(&c["query"]).map(|_| json!(true)))
    });
}

#[test]
fn temporal_state_matches() {
    check("temporal_state", |c| {
        let r = lab_catalog()
            .iter()
            .find(|r| r["id"] == c["id"])
            .expect("record");
        let at = istanbul_dt(c["at"].as_str().unwrap()).unwrap();
        outcome(temporal_state(r, &at).map(Value::from))
    });
}

fn run_decide(c: &Value) -> Value {
    let records: Vec<Value> = match &c["catalog"] {
        Value::String(s) if s == "lab" => lab_catalog().clone(),
        Value::Array(a) => a.clone(),
        other => panic!("unexpected catalog {other}"),
    };
    outcome(
        Query::from_json(&c["query"])
            .and_then(|q| decide(&records, &q, c["policy"].as_str().unwrap()))
            .map(|d| d.to_json()),
    )
}

#[test]
fn decide_matches() {
    check("decide", run_decide);
}

#[test]
fn reconcile_matches() {
    check("reconcile", |c| {
        outcome(reconcile_claims(c["claims"].as_array().unwrap()))
    });
}

#[test]
fn model_selection_matches() {
    let section = &vectors()["model_selection"];
    let q = Query::from_json(&json!({
        "city": "İstanbul", "lat": 41.02563232, "lon": 28.97415319, "radius_km": 3, "limit": 3
    }))
    .unwrap();
    let d = decide(lab_catalog(), &q, "query_aware").unwrap();
    assert_eq!(
        canonical_json(&d.to_json()),
        canonical_json(&section["decision"])
    );
    for case in section["cases"].as_array().unwrap() {
        let proposed: Vec<String> = case["proposed"]
            .as_array()
            .unwrap()
            .iter()
            .map(|v| v.as_str().unwrap().to_owned())
            .collect();
        let got = check_model_selection(&d, &proposed);
        assert_eq!(
            canonical_json(&got),
            canonical_json(&case["expect"]),
            "{}",
            case["name"]
        );
    }
}

#[test]
fn query_cli_output_is_byte_identical() {
    for case in vectors()["cli"].as_array().unwrap() {
        let q = Query::from_json(&case["query"]).unwrap();
        let d = decide(lab_catalog(), &q, "query_aware").unwrap();
        assert_eq!(
            python_json_pretty(&d.to_json(), 2),
            case["stdout"].as_str().unwrap(),
            "{}",
            case["name"]
        );
    }
}
