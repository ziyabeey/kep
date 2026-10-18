//! Port of `labs/core/kepcore/availability.py`.
//!
//! Supported: complete ISO-weekday weekly intervals, IANA zone, date overrides.
//! Intervals are [open, close), and an end earlier than start crosses midnight.
//! A date override replaces the whole day's regular hours, including carry-over.
//! Unsupported/malformed input is UNKNOWN, never an implicit open flag.

use crate::isotime::parse_reference_timestamp;
use crate::pyval::{PyError, py_int, truthy};
use chrono::{DateTime, Datelike, Days, FixedOffset, Timelike};
use chrono_tz::Tz;
use kep_canon::stable_hash;
use serde_json::{Map, Value};
use std::collections::HashMap;

/// Result of [`opening_status`]; the strings match the Python reference.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum OpeningStatus {
    Open,
    Closed,
    Unknown,
}

impl OpeningStatus {
    pub fn as_str(self) -> &'static str {
        match self {
            OpeningStatus::Open => "OPEN",
            OpeningStatus::Closed => "CLOSED",
            OpeningStatus::Unknown => "UNKNOWN",
        }
    }
}

/// `HH:MM` to minutes after midnight; `24:00` only as an interval end.
pub fn minute(text: &Value, end: bool) -> Result<i64, PyError> {
    let Value::String(text) = text else {
        return Err(PyError::ValueError);
    };
    let chars: Vec<char> = text.chars().collect();
    if chars.len() != 5 || chars[2] != ':' {
        return Err(PyError::ValueError);
    }
    let h = py_int(&chars[..2].iter().collect::<String>()).ok_or(PyError::ValueError)?;
    let m = py_int(&chars[3..].iter().collect::<String>()).ok_or(PyError::ValueError)?;
    if end && h == 24 && m == 0 {
        return Ok(1440);
    }
    if !((0..=23).contains(&h) && (0..=59).contains(&m)) {
        return Err(PyError::ValueError);
    }
    Ok(h * 60 + m)
}

/// A list of `[open, close]` pairs; `[]` explicitly means closed.
pub fn intervals(raw: &Value) -> Result<Vec<(i64, i64)>, PyError> {
    let Value::Array(pairs) = raw else {
        return Err(PyError::ValueError);
    };
    pairs
        .iter()
        .map(|pair| match pair {
            Value::Array(p) if p.len() == 2 => {
                let (a, b) = (minute(&p[0], false)?, minute(&p[1], true)?);
                if a == b {
                    Err(PyError::ValueError) // ambiguous; use 00:00-24:00
                } else {
                    Ok((a, b))
                }
            }
            _ => Err(PyError::ValueError),
        })
        .collect()
}

fn parse_days(map: &Map<String, Value>) -> Option<HashMap<&str, Vec<(i64, i64)>>> {
    map.iter()
        .map(|(k, v)| intervals(v).ok().map(|iv| (k.as_str(), iv)))
        .collect()
}

/// Whether a place is open at `at`, given its declared hours.
pub fn opening_status(hours: &Value, at: &DateTime<FixedOffset>) -> OpeningStatus {
    status_inner(hours, at).unwrap_or(OpeningStatus::Unknown)
}

fn status_inner(hours: &Value, at: &DateTime<FixedOffset>) -> Option<OpeningStatus> {
    let hours = hours.as_object()?;
    let zone: Tz = hours.get("timezone")?.as_str()?.parse().ok()?;
    let here = at.with_timezone(&zone);
    let weekly = hours.get("weekly")?.as_object()?;
    let empty = Map::new();
    let overrides = match hours.get("exceptions") {
        None => &empty,
        Some(v) => v.as_object()?,
    };
    // Require explicit status for all days, not missing = closed.
    if !(1..=7).all(|i| weekly.contains_key(&i.to_string())) {
        return None;
    }
    let parsed = parse_days(weekly)?;
    let exceptions = parse_days(overrides)?;
    let d = here.date_naive();
    let prev = d.checked_sub_days(Days::new(1))?;
    let m = f64::from(here.hour() * 60 + here.minute()) + f64::from(here.second()) / 60.0;
    let iso = |date: chrono::NaiveDate| date.format("%Y-%m-%d").to_string();
    let weekday = |date: chrono::NaiveDate| date.weekday().number_from_monday().to_string();

    let today_key = iso(d);
    let today = match exceptions.get(today_key.as_str()) {
        Some(iv) => iv,
        None => parsed.get(weekday(d).as_str())?,
    };
    for &(a, b) in today {
        let (af, bf) = (a as f64, b as f64);
        if (a < b && af <= m && m < bf) || (b < a && m >= af) {
            return Some(OpeningStatus::Open);
        }
    }
    if !exceptions.contains_key(today_key.as_str()) {
        let yesterday = match exceptions.get(iso(prev).as_str()) {
            Some(iv) => iv,
            None => parsed.get(weekday(prev).as_str())?,
        };
        if yesterday.iter().any(|&(a, b)| b < a && m < b as f64) {
            return Some(OpeningStatus::Open);
        }
    }
    Some(OpeningStatus::Closed)
}

/// Whether `record[field]` was checked live within `max_hours` before `at`.
///
/// Explicit field evidence overrides the broad record timestamp and must be
/// bound to the current value by hash. Acquisition time is never substituted
/// for observation time. `Err` reproduces an exception the reference raises
/// (for example a missing or non-string `observed_at` on a live record).
pub fn field_is_fresh(
    record: &Value,
    field: &str,
    at: &DateTime<FixedOffset>,
    max_hours: f64,
) -> Result<bool, PyError> {
    let record = record.as_object().ok_or(PyError::AttributeError)?;
    let empty = Map::new();
    let proofs = match record.get("field_evidence") {
        None => &empty,
        Some(Value::Object(m)) => m,
        Some(_) => return Ok(false),
    };
    let explicit = proofs.get(field).filter(|p| !p.is_null());
    let synthesized;
    let proof = match explicit {
        Some(p) => {
            let expected = stable_hash(record.get(field).unwrap_or(&Value::Null));
            let bound = p
                .as_object()
                .and_then(|o| o.get("value_hash"))
                .and_then(Value::as_str)
                .is_some_and(|h| h == expected);
            if !bound {
                return Ok(false);
            }
            p
        }
        None => {
            let mut m = Map::new();
            let get = |k: &str| record.get(k).cloned().unwrap_or(Value::Null);
            m.insert("origin_live_verified".into(), get("origin_live_verified"));
            m.insert("observed_at".into(), get("source_observed_at"));
            synthesized = Value::Object(m);
            &synthesized
        }
    };
    let Some(proof) = proof.as_object() else {
        return Ok(false);
    };
    if !truthy(proof.get("origin_live_verified")) {
        return Ok(false);
    }
    match proof.get("status") {
        Some(Value::Array(_) | Value::Object(_)) => return Err(PyError::TypeError), // unhashable
        Some(Value::String(s)) if matches!(s.as_str(), "disputed" | "unknown" | "retracted") => {
            return Ok(false);
        }
        _ => {}
    }
    let Some(observed) = proof.get("observed_at") else {
        return Ok(false); // KeyError, caught by the reference
    };
    let Value::String(observed) = observed else {
        return Err(PyError::AttributeError); // `.replace` on a non-string
    };
    let Some(stamp) = parse_reference_timestamp(observed).and_then(|t| t.aware()) else {
        return Ok(false);
    };
    let Some(micros) = (*at - stamp).num_microseconds() else {
        return Ok(false);
    };
    let age = micros as f64 / 1e6 / 3600.0;
    if !(age.is_finite() && 0.0 <= age && age <= max_hours) {
        return Ok(false);
    }
    let until = proof.get("valid_until");
    if truthy(until) {
        let Some(Value::String(until)) = until else {
            return Err(PyError::AttributeError);
        };
        match parse_reference_timestamp(until).and_then(|t| t.aware()) {
            Some(deadline) if *at < deadline => {}
            _ => return Ok(false),
        }
    }
    Ok(true)
}
