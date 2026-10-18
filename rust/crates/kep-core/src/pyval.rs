//! Small helpers that reproduce Python semantics the reference relies on.

use serde_json::{Map, Value};
use std::cmp::Ordering;

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

/// A JSON number (or bool) as Python sees it: an exact `int` or a `float`.
/// Integers beyond `i128` fall back to float.
#[derive(Debug, Clone, Copy)]
pub enum PyNum {
    Int(i128),
    Float(f64),
}

/// `value` as a Python number; `None` for anything else.
pub fn py_num(value: &Value) -> Option<PyNum> {
    match value {
        Value::Bool(b) => Some(PyNum::Int(i128::from(*b))),
        Value::Number(n) => {
            let text = n.to_string();
            match text.parse::<i128>() {
                Ok(i) if !text.contains(['.', 'e', 'E']) => Some(PyNum::Int(i)),
                _ => n.as_f64().map(PyNum::Float),
            }
        }
        _ => None,
    }
}

/// 2^127 as f64: floats at or beyond it are outside `i128`.
const I128_BOUND: f64 = 170_141_183_460_469_231_731_687_303_715_884_105_728.0;

/// Exact comparison of an int with a float, as Python does (`None` for NaN).
fn cmp_int_float(i: i128, f: f64) -> Option<Ordering> {
    if f.is_nan() {
        return None;
    }
    if f >= I128_BOUND {
        return Some(Ordering::Less);
    }
    if f < -I128_BOUND {
        return Some(Ordering::Greater);
    }
    let t = f.trunc();
    Some(match i.cmp(&(t as i128)) {
        Ordering::Equal if f > t => Ordering::Less,
        Ordering::Equal if f < t => Ordering::Greater,
        other => other,
    })
}

impl PyNum {
    /// Python's numeric comparison; `None` when a NaN is involved.
    pub fn py_cmp(&self, other: &PyNum) -> Option<Ordering> {
        match (*self, *other) {
            (PyNum::Int(x), PyNum::Int(y)) => Some(x.cmp(&y)),
            (PyNum::Float(x), PyNum::Float(y)) => x.partial_cmp(&y),
            (PyNum::Int(x), PyNum::Float(y)) => cmp_int_float(x, y),
            (PyNum::Float(x), PyNum::Int(y)) => cmp_int_float(y, x).map(Ordering::reverse),
        }
    }
}

impl PartialEq for PyNum {
    fn eq(&self, other: &Self) -> bool {
        self.py_cmp(other) == Some(Ordering::Equal)
    }
}

/// Python `==` between two JSON values (`1 == 1.0 == True`, deep for lists
/// and dicts).
pub fn py_eq(a: &Value, b: &Value) -> bool {
    if let (Some(x), Some(y)) = (py_num(a), py_num(b)) {
        return x == y;
    }
    match (a, b) {
        (Value::Null, Value::Null) => true,
        (Value::String(x), Value::String(y)) => x == y,
        (Value::Array(x), Value::Array(y)) => {
            x.len() == y.len() && x.iter().zip(y).all(|(p, q)| py_eq(p, q))
        }
        (Value::Object(x), Value::Object(y)) => {
            x.len() == y.len() && x.iter().all(|(k, v)| y.get(k).is_some_and(|w| py_eq(v, w)))
        }
        _ => false,
    }
}
