//! Parity of the `radar.py` policy gate port (ADR-0034 phase 2).
//!
//! `rust/parity/radar.json` is written by `rust/parity/export_vectors.py`.
//! The transport is scripted from the vectors; nothing reaches the network.

use kep_canon::canonical_json;
use kep_core::PyError;
use kep_core::isotime::{IsoDateTime, parse_iso};
use kep_core::radar::{
    FetchResponse, PollState, Source, TransportError, parse_registry, poll, public_https,
};
use serde_json::{Value, json};
use std::sync::OnceLock;

fn vectors() -> &'static Value {
    static V: OnceLock<Value> = OnceLock::new();
    V.get_or_init(|| {
        let path = concat!(env!("CARGO_MANIFEST_DIR"), "/../../parity/radar.json");
        serde_json::from_str(&std::fs::read_to_string(path).expect("vector file"))
            .expect("valid JSON")
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

fn source_json(s: &Source) -> Value {
    json!({
        "id": s.id,
        "url": s.url,
        "city": s.city,
        "format": s.format,
        "status": s.status,
        "approved_uses": s.approved_uses,
        "license": s.license,
        "rights_evidence_url": s.rights_evidence_url,
        "rights_reviewed_at": s.rights_reviewed_at,
        "attribution": s.attribution,
        "min_poll_minutes": s.min_poll_minutes,
        "max_poll_minutes": s.max_poll_minutes,
        "daily_request_cap": s.daily_request_cap,
        "max_response_bytes": s.max_response_bytes,
        "review_note": s.review_note,
        "allows_research": s.allows("research_ingest"),
        "allows_display": s.allows("consumer_display"),
    })
}

fn unhex(s: &str) -> Vec<u8> {
    (0..s.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(&s[i..i + 2], 16).expect("hex"))
        .collect()
}

fn pairs(v: &Value) -> Vec<(String, String)> {
    v.as_array()
        .expect("pairs")
        .iter()
        .map(|p| {
            (
                p[0].as_str().expect("key").to_owned(),
                p[1].as_str().expect("value").to_owned(),
            )
        })
        .collect()
}

#[test]
fn public_https_matches() {
    check("public_https", |c| {
        outcome(public_https(c["url"].as_str().unwrap()).map(Value::String))
    });
}

#[test]
fn source_matches() {
    check("source", |c| {
        outcome(Source::parse(&c["raw"]).map(|s| source_json(&s)))
    });
}

#[test]
fn registry_matches() {
    check("registry", |c| {
        outcome(
            parse_registry(&c["doc"]).map(|v| json!(v.iter().map(|s| &s.id).collect::<Vec<_>>())),
        )
    });
}

#[test]
fn poll_matches() {
    check("poll", |c| {
        let source = Source::parse(&c["source"]).expect("valid source");
        let purpose = c["purpose"].as_str().unwrap();
        let mut state = PollState::from_json(&c["state"]).expect("valid state");
        let mut out = Vec::new();
        for step in c["steps"].as_array().unwrap() {
            let Some(IsoDateTime::Aware(now)) = parse_iso(step["now"].as_str().unwrap()) else {
                panic!("{}: step time must be aware", c["name"]);
            };
            let mut calls: Vec<Value> = Vec::new();
            let mut transport = |url: &str, headers: &[(String, String)], max: i64| {
                calls.push(json!([
                    url,
                    headers
                        .iter()
                        .map(|(k, v)| json!([k, v]))
                        .collect::<Vec<_>>(),
                    max
                ]));
                if let Some(name) = step.get("raise") {
                    return Err(match name.as_str().unwrap() {
                        "ValueError" => TransportError::Other(PyError::ValueError),
                        other => TransportError::Network(other.to_owned()),
                    });
                }
                let r = &step["response"];
                Ok(FetchResponse {
                    status: r["status"].as_i64().unwrap(),
                    body: unhex(r["body_hex"].as_str().unwrap()),
                    headers: pairs(&r["headers"]),
                })
            };
            let result = poll(&source, &now, &state, &mut transport, purpose);
            let stop = result.is_err();
            let mut entry = outcome(result.as_ref().map(|r| r.to_json()).map_err(|e| *e));
            entry["calls"] = json!(calls);
            out.push(entry);
            if stop {
                break;
            }
            state = result.unwrap().state;
        }
        json!(out)
    });
}
