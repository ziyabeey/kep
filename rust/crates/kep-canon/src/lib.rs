//! Canonical JSON, byte-identical to the Python reference:
//!
//! ```python
//! json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
//! ```
//!
//! KEP stores SHA-256 hashes of this text (`source_record_hash`, field-proof
//! `value_hash`), so any byte difference would break provenance. Integers and
//! floats are kept apart (`1` and `1.0` hash differently), floats use Python's
//! `repr`, keys sort by code point, and non-ASCII text is written as is.

use serde_json::{Number, Value};
use sha2::{Digest, Sha256};
use std::fmt::Write as _;

/// Python-compatible canonical JSON text for `value`.
pub fn canonical_json(value: &Value) -> String {
    let mut out = String::new();
    write_value(&mut out, value);
    out
}

/// `sha256(canonical_json(value))` as lowercase hex; Python's `stable_hash`.
pub fn stable_hash(value: &Value) -> String {
    sha256_hex(canonical_json(value).as_bytes())
}

/// Lowercase hex SHA-256 of raw bytes.
pub fn sha256_hex(bytes: &[u8]) -> String {
    let digest = Sha256::digest(bytes);
    let mut hex = String::with_capacity(64);
    for byte in digest {
        let _ = write!(hex, "{byte:02x}");
    }
    hex
}

fn write_value(out: &mut String, value: &Value) {
    match value {
        Value::Null => out.push_str("null"),
        Value::Bool(true) => out.push_str("true"),
        Value::Bool(false) => out.push_str("false"),
        Value::Number(n) => write_number(out, n),
        Value::String(s) => write_string(out, s),
        Value::Array(items) => {
            out.push('[');
            for (i, item) in items.iter().enumerate() {
                if i > 0 {
                    out.push(',');
                }
                write_value(out, item);
            }
            out.push(']');
        }
        Value::Object(map) => {
            // Rust's str ordering is UTF-8 byte order, which equals code point order.
            let mut keys: Vec<&String> = map.keys().collect();
            keys.sort();
            out.push('{');
            for (i, key) in keys.into_iter().enumerate() {
                if i > 0 {
                    out.push(',');
                }
                write_string(out, key);
                out.push(':');
                write_value(out, &map[key]);
            }
            out.push('}');
        }
    }
}

fn write_number(out: &mut String, n: &Number) {
    // With `arbitrary_precision` this is the literal as parsed (or as produced
    // by `Number::from_f64`), so Python's int/float split can be recovered.
    let literal = n.to_string();
    if literal.contains(['.', 'e', 'E']) {
        // Python's json.loads: float(literal), so 1e400 becomes inf.
        let value: f64 = literal.parse().unwrap_or(f64::NAN);
        out.push_str(&python_json_float(value));
    } else if literal.trim_start_matches('-').bytes().all(|b| b == b'0') {
        out.push('0'); // int("-0") == 0
    } else {
        out.push_str(&literal); // JSON integers are already canonical (no leading zeros)
    }
}

/// Float text as Python's `json.dumps` writes it (`allow_nan=True`).
pub fn python_json_float(value: f64) -> String {
    if value.is_nan() {
        "NaN".to_owned()
    } else if value == f64::INFINITY {
        "Infinity".to_owned()
    } else if value == f64::NEG_INFINITY {
        "-Infinity".to_owned()
    } else {
        python_float_repr(value)
    }
}

/// Python's `repr(float)` for finite values: shortest round-trip digits,
/// fixed notation when the decimal exponent is in -4..16, otherwise
/// scientific with a signed exponent of at least two digits.
pub fn python_float_repr(value: f64) -> String {
    debug_assert!(value.is_finite());
    // Rust's `{:e}` already yields the shortest round-trip digits, e.g. "-1.5e-7".
    let sci = format!("{value:e}");
    let (mantissa, exp) = sci.split_once('e').expect("{:e} always has an exponent");
    let exp: i32 = exp.parse().expect("integer exponent");
    let (sign, mantissa) = match mantissa.strip_prefix('-') {
        Some(rest) => ("-", rest),
        None => ("", mantissa),
    };
    let digits: String = mantissa.chars().filter(|c| *c != '.').collect();
    let mut out = String::from(sign);
    if (-4..16).contains(&exp) {
        let point = exp + 1; // digits before the decimal point
        if point <= 0 {
            out.push_str("0.");
            out.extend(std::iter::repeat_n('0', (-point) as usize));
            out.push_str(&digits);
        } else if point as usize >= digits.len() {
            out.push_str(&digits);
            out.extend(std::iter::repeat_n('0', point as usize - digits.len()));
            out.push_str(".0");
        } else {
            let (int_part, frac) = digits.split_at(point as usize);
            out.push_str(int_part);
            out.push('.');
            out.push_str(frac);
        }
    } else {
        out.push_str(&digits[..1]);
        if digits.len() > 1 {
            out.push('.');
            out.push_str(&digits[1..]);
        }
        let _ = write!(out, "e{}{:02}", if exp < 0 { '-' } else { '+' }, exp.abs());
    }
    out
}

fn write_string(out: &mut String, s: &str) {
    out.push('"');
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            '\u{08}' => out.push_str("\\b"),
            '\u{0c}' => out.push_str("\\f"),
            c if (c as u32) < 0x20 => {
                let _ = write!(out, "\\u{:04x}", c as u32);
            }
            c => out.push(c),
        }
    }
    out.push('"');
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn float_repr_matches_python_samples() {
        for (value, text) in [
            (0.0, "0.0"),
            (-0.0, "-0.0"),
            (1.0, "1.0"),
            (0.1, "0.1"),
            (0.0001, "0.0001"),
            (0.00001, "1e-05"),
            (1e15, "1000000000000000.0"),
            (1e16, "1e+16"),
            (1.5e300, "1.5e+300"),
            (5e-324, "5e-324"),
            (123456.789, "123456.789"),
        ] {
            assert_eq!(python_float_repr(value), text, "{value:?}");
        }
    }
}
