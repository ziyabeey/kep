//! Parity of the `model_boundary.py` and `scheduler.py` ports (ADR-0034 phase 2).
//!
//! `rust/parity/boundary.json` is written by `rust/parity/export_vectors.py`.

use kep_canon::canonical_json;
use kep_core::model_boundary::{context_for_model, validate_structured_reply};
use kep_core::scheduler::{SourceClock, due_sources};
use kep_core::{PyError, Query, decide, load_catalog};
use serde_json::{Value, json};
use std::path::PathBuf;
use std::sync::OnceLock;

fn vectors() -> &'static Value {
    static V: OnceLock<Value> = OnceLock::new();
    V.get_or_init(|| {
        let path = concat!(env!("CARGO_MANIFEST_DIR"), "/../../parity/boundary.json");
        serde_json::from_str(&std::fs::read_to_string(path).expect("vector file"))
            .expect("valid JSON")
    })
}

fn lab_catalog() -> &'static Vec<Value> {
    static C: OnceLock<Vec<Value>> = OnceLock::new();
    C.get_or_init(|| {
        let root = PathBuf::from(concat!(env!("CARGO_MANIFEST_DIR"), "/../../../labs/core"));
        load_catalog(&root).expect("lab catalog")
    })
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
fn context_matches() {
    check("context", |c| {
        outcome(
            Query::from_json(&c["query"])
                .and_then(|q| decide(lab_catalog(), &q, "query_aware"))
                .and_then(|d| context_for_model(&d)),
        )
    });
    // Key order is part of what a provider sees.
    for c in vectors()["context"].as_array().unwrap() {
        let q = Query::from_json(&c["query"]).unwrap();
        let got = context_for_model(&decide(lab_catalog(), &q, "query_aware").unwrap()).unwrap();
        let keys = |v: &Value| v.as_object().unwrap().keys().cloned().collect::<Vec<_>>();
        assert_eq!(keys(&got), keys(&c["expect"]["ok"]), "{}", c["name"]);
    }
}

#[test]
fn reply_matches() {
    check("reply", |c| {
        outcome(validate_structured_reply(&c["context"], &c["reply"]))
    });
}

#[test]
fn due_sources_match() {
    check("due_sources", |c| {
        let sources: Result<Vec<SourceClock>, PyError> = c["sources"]
            .as_array()
            .unwrap()
            .iter()
            .map(SourceClock::from_json)
            .collect();
        outcome(
            sources
                .and_then(|s| due_sources(&s, c["budget"].as_i64().unwrap()).map(|ids| json!(ids))),
        )
    });
}
