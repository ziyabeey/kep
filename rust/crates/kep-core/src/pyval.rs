//! Small helpers that reproduce Python semantics the reference relies on.

use serde_json::{Map, Value};

/// A Python exception the reference raises (and does not catch) for an input.
/// Parity requires reporting the same class, not hiding it.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PyError {
    ValueError,
    TypeError,
    AttributeError,
    KeyError,
}

impl PyError {
    pub fn name(self) -> &'static str {
        match self {
            PyError::ValueError => "ValueError",
            PyError::TypeError => "TypeError",
            PyError::AttributeError => "AttributeError",
            PyError::KeyError => "KeyError",
        }
    }
}

/// Python truthiness of a JSON value.
pub fn truthy(value: Option<&Value>) -> bool {
    match value {
        None | Some(Value::Null) | Some(Value::Bool(false)) => false,
        Some(Value::Bool(true)) => true,
        Some(Value::Number(n)) => n.as_f64().is_some_and(|f| f != 0.0),
        Some(Value::String(s)) => !s.is_empty(),
        Some(Value::Array(a)) => !a.is_empty(),
        Some(Value::Object(o)) => !o.is_empty(),
    }
}

/// Python's `str.isspace` for one character (adds the \x1c-\x1f separators
/// that Rust's `char::is_whitespace` leaves out).
pub fn py_isspace(c: char) -> bool {
    c.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&c)
}

/// `d.get(key)` as Python sees it: a missing key and JSON null are both `None`.
pub fn pyget<'a>(map: &'a Map<String, Value>, key: &str) -> Option<&'a Value> {
    map.get(key).filter(|v| !v.is_null())
}

/// `d[key]`: KeyError when missing; JSON null is a present `None`.
pub fn pyindex<'a>(map: &'a Map<String, Value>, key: &str) -> Result<&'a Value, PyError> {
    map.get(key).ok_or(PyError::KeyError)
}

/// A value used where Python needs a `str` method (`.replace`, `.strip`).
pub fn pystr(value: &Value) -> Result<&str, PyError> {
    value.as_str().ok_or(PyError::AttributeError)
}

/// A value passed to `math.isfinite` and arithmetic: numbers and bools
/// (Python bools are ints); anything else is a TypeError.
pub fn pyfloat(value: &Value) -> Result<f64, PyError> {
    match value {
        Value::Number(n) => n.as_f64().ok_or(PyError::TypeError),
        Value::Bool(b) => Ok(if *b { 1.0 } else { 0.0 }),
        _ => Err(PyError::TypeError),
    }
}

/// True for a JSON number that Python would load as `int` or `float` (not bool).
pub fn is_number(value: &Value) -> bool {
    matches!(value, Value::Number(_))
}

/// Python's `str(value)` for JSON scalars (used in ids and f-strings).
pub fn python_str(value: &Value) -> String {
    match value {
        Value::Null => "None".to_owned(),
        Value::Bool(true) => "True".to_owned(),
        Value::Bool(false) => "False".to_owned(),
        Value::String(s) => s.clone(),
        Value::Number(_) => kep_canon::canonical_json(value),
        other => kep_canon::canonical_json(other),
    }
}

/// `list(dict.fromkeys(items))`: drop repeats, keep first-seen order.
pub fn dedupe<T: PartialEq + Clone>(items: &[T]) -> Vec<T> {
    let mut out: Vec<T> = Vec::with_capacity(items.len());
    for item in items {
        if !out.contains(item) {
            out.push(item.clone());
        }
    }
    out
}
