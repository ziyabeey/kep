//! Small helpers that reproduce Python semantics the reference relies on.

use serde_json::Value;

/// A Python exception the reference raises (and does not catch) for an input.
/// Parity requires reporting the same class, not hiding it.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PyError {
    ValueError,
    TypeError,
    AttributeError,
}

impl PyError {
    pub fn name(self) -> &'static str {
        match self {
            PyError::ValueError => "ValueError",
            PyError::TypeError => "TypeError",
            PyError::AttributeError => "AttributeError",
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

/// Python's `int(text)` for short decimal strings: surrounding whitespace and
/// one sign are allowed. Only ASCII digits are accepted; Python also accepts
/// other Unicode decimal digits (a documented parity gap, see ADR-0034).
pub fn py_int(text: &str) -> Option<i64> {
    let t = text.trim_matches(py_isspace);
    let (negative, digits) = match t.as_bytes().first() {
        Some(b'-') => (true, &t[1..]),
        Some(b'+') => (false, &t[1..]),
        _ => (false, t),
    };
    if digits.is_empty() || !digits.bytes().all(|b| b.is_ascii_digit()) {
        return None;
    }
    let n: i64 = digits.parse().ok()?;
    Some(if negative { -n } else { n })
}
