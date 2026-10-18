//! Bounded refresh scheduling (`scheduler.py`). No claim of learned latency
//! improvement.

use crate::pyval::PyError;
use serde_json::Value;
use std::cmp::Ordering;

/// How long since a source was checked, and the limits on checking it again.
#[derive(Debug, Clone, PartialEq)]
pub struct SourceClock {
    pub source_id: String,
    pub elapsed_hours: f64,
    pub min_interval_hours: f64,
    pub max_interval_hours: f64,
    pub observed_change_rate: f64,
    pub priority: f64,
    pub approved: bool,
    pub calls_today: f64,
    pub daily_cap: f64,
    pub retry_after_hours: f64,
}

const FIELDS: [&str; 10] = [
    "source_id",
    "elapsed_hours",
    "min_interval_hours",
    "max_interval_hours",
    "observed_change_rate",
    "priority",
    "approved",
    "calls_today",
    "daily_cap",
    "retry_after_hours",
];

impl SourceClock {
    /// `SourceClock(**object)`: TypeError for unknown, missing or ill-typed
    /// fields (the reference does not type-check; numbers here are JSON
    /// numbers, not bools); ValueError for what `__post_init__` rejects.
    pub fn from_json(value: &Value) -> Result<SourceClock, PyError> {
        let obj = value.as_object().ok_or(PyError::TypeError)?;
        if obj.keys().any(|k| !FIELDS.contains(&k.as_str())) {
            return Err(PyError::TypeError);
        }
        let num = |k: &str, default: Option<f64>| -> Result<f64, PyError> {
            match obj.get(k) {
                None => default.ok_or(PyError::TypeError),
                Some(Value::Number(n)) => n.as_f64().ok_or(PyError::TypeError),
                Some(_) => Err(PyError::TypeError),
            }
        };
        let Some(Value::String(source_id)) = obj.get("source_id") else {
            return Err(PyError::TypeError);
        };
        let clock = SourceClock {
            source_id: source_id.clone(),
            elapsed_hours: num("elapsed_hours", None)?,
            min_interval_hours: num("min_interval_hours", None)?,
            max_interval_hours: num("max_interval_hours", None)?,
            observed_change_rate: num("observed_change_rate", Some(0.0))?,
            priority: num("priority", Some(1.0))?,
            approved: match obj.get("approved") {
                None => true,
                Some(Value::Bool(b)) => *b,
                Some(_) => return Err(PyError::TypeError),
            },
            calls_today: num("calls_today", Some(0.0))?,
            daily_cap: num("daily_cap", Some(24.0))?,
            retry_after_hours: num("retry_after_hours", Some(0.0))?,
        };
        if clock.min_interval_hours <= 0.0 || clock.max_interval_hours < clock.min_interval_hours {
            return Err(PyError::ValueError); // invalid intervals
        }
        if clock.elapsed_hours < 0.0 || clock.observed_change_rate < 0.0 {
            return Err(PyError::ValueError); // invalid observations
        }
        Ok(clock)
    }
}

fn cmp_f64(a: f64, b: f64) -> Ordering {
    a.partial_cmp(&b).unwrap_or(Ordering::Equal) // -0.0 == 0.0, as in Python
}

/// `due_sources()`: which sources to check now, at most `budget` of them.
/// An overdue heartbeat outranks popularity; rights, caps and retry limits
/// still apply.
pub fn due_sources(sources: &[SourceClock], budget: i64) -> Result<Vec<String>, PyError> {
    if budget < 0 {
        return Err(PyError::ValueError);
    }
    // (overdue, elapsed / max, score, id)
    let mut candidates: Vec<(bool, f64, f64, &str)> = Vec::new();
    for s in sources {
        if !s.approved || s.calls_today >= s.daily_cap || s.retry_after_hours > 0.0 {
            continue;
        }
        if s.elapsed_hours < s.min_interval_hours {
            continue;
        }
        let overdue = s.elapsed_hours >= s.max_interval_hours;
        let score = s.priority * (1.0 + s.observed_change_rate) * s.elapsed_hours;
        candidates.push((
            overdue,
            s.elapsed_hours / s.max_interval_hours,
            score,
            &s.source_id,
        ));
    }
    candidates.sort_by(|a, b| {
        let ratio = |c: &(bool, f64, f64, &str)| if c.0 { -c.1 } else { 0.0 };
        b.0.cmp(&a.0)
            .then_with(|| cmp_f64(ratio(a), ratio(b)))
            .then_with(|| cmp_f64(-a.2, -b.2))
            .then_with(|| a.3.cmp(b.3))
    });
    Ok(candidates
        .into_iter()
        .take(budget as usize)
        .map(|c| c.3.to_owned())
        .collect())
}
