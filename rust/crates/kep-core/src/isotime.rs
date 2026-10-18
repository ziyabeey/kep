//! ISO 8601 timestamps as the reference reads them:
//! `datetime.fromisoformat(text.replace('Z', '+00:00'))` on Python 3.11+.
//!
//! Supported (a strict subset of what Python accepts):
//! `YYYY-MM-DD`, optionally followed by any one separator character and
//! `HH[:MM[:SS[(.|,)fraction]]]`, optionally followed by `Z` or an offset
//! `±HH`, `±HHMM`, `±HH:MM` or `±HH:MM:SS`. Fractions keep 6 digits (truncated).
//!
//! Python also accepts basic (`20261010T175000`) and week (`2026-W41-6`) dates
//! and a few other spellings. Rust rejects those, which makes freshness checks
//! fail closed (not fresh) rather than open. The parity vectors list each case.
//! An empty fraction (`17:50:00.`) is rejected; Python 3.11 accepts it but 3.13 does not.

use chrono::{DateTime, FixedOffset, NaiveDate, NaiveDateTime, NaiveTime, TimeZone};

/// A parsed timestamp; Python returns a naive datetime when no offset is given.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum IsoDateTime {
    Aware(DateTime<FixedOffset>),
    Naive(NaiveDateTime),
}

impl IsoDateTime {
    pub fn aware(self) -> Option<DateTime<FixedOffset>> {
        match self {
            IsoDateTime::Aware(dt) => Some(dt),
            IsoDateTime::Naive(_) => None,
        }
    }

    /// Same text as Python's `datetime.isoformat()`.
    pub fn python_isoformat(&self) -> String {
        let (naive, offset) = match self {
            IsoDateTime::Aware(dt) => (dt.naive_local(), Some(dt.offset().local_minus_utc())),
            IsoDateTime::Naive(n) => (*n, None),
        };
        let mut out = naive.format("%Y-%m-%dT%H:%M:%S").to_string();
        let micros = naive.and_utc().timestamp_subsec_micros();
        if micros != 0 {
            out.push_str(&format!(".{micros:06}"));
        }
        if let Some(secs) = offset {
            let sign = if secs < 0 { '-' } else { '+' };
            let a = secs.abs();
            out.push_str(&format!("{sign}{:02}:{:02}", a / 3600, (a % 3600) / 60));
            if a % 60 != 0 {
                out.push_str(&format!(":{:02}", a % 60));
            }
        }
        out
    }
}

/// Parse `text` after applying the reference's `replace('Z', '+00:00')`.
pub fn parse_reference_timestamp(text: &str) -> Option<IsoDateTime> {
    parse_iso(&text.replace('Z', "+00:00"))
}

/// Parse the supported ISO 8601 subset; `None` where Python raises ValueError
/// (or where Python accepts a form this subset leaves out).
pub fn parse_iso(text: &str) -> Option<IsoDateTime> {
    let chars: Vec<char> = text.chars().collect();
    if chars.len() < 10 {
        return None;
    }
    let date_text: String = chars[..10].iter().collect();
    let date = parse_date(&date_text)?;
    if chars.len() == 10 {
        return Some(IsoDateTime::Naive(date.and_hms_opt(0, 0, 0)?));
    }
    // Python accepts any single separator character between date and time.
    let rest: String = chars[11..].iter().collect();
    let tz_at = rest.find(['+', '-', 'Z']);
    let (time_text, tz_text) = match tz_at {
        Some(i) => (&rest[..i], Some(&rest[i..])),
        None => (&rest[..], None),
    };
    let time = parse_time(time_text)?;
    let naive = NaiveDateTime::new(date, time);
    match tz_text {
        None => Some(IsoDateTime::Naive(naive)),
        Some(tz) => {
            let offset = parse_offset(tz)?;
            let dt = offset.from_local_datetime(&naive).single()?;
            Some(IsoDateTime::Aware(dt))
        }
    }
}

fn digits(s: &str, n: usize) -> Option<u32> {
    if s.len() == n && s.bytes().all(|b| b.is_ascii_digit()) {
        s.parse().ok()
    } else {
        None
    }
}

fn parse_date(s: &str) -> Option<NaiveDate> {
    let b = s.as_bytes();
    if b.len() != 10 || b[4] != b'-' || b[7] != b'-' {
        return None;
    }
    let year = digits(&s[0..4], 4)?;
    let month = digits(&s[5..7], 2)?;
    let day = digits(&s[8..10], 2)?;
    NaiveDate::from_ymd_opt(year as i32, month, day).filter(|_| year >= 1)
}

fn parse_time(s: &str) -> Option<NaiveTime> {
    let (clock, fraction) = match s.find(['.', ',']) {
        Some(i) => (&s[..i], Some(&s[i + 1..])),
        None => (s, None),
    };
    let parts: Vec<&str> = clock.split(':').collect();
    if parts.is_empty() || parts.len() > 3 {
        return None;
    }
    let hour = digits(parts[0], 2)?;
    let minute = parts.get(1).map_or(Some(0), |p| digits(p, 2))?;
    let second = parts.get(2).map_or(Some(0), |p| digits(p, 2))?;
    let micros = match fraction {
        None => 0,
        Some(f) => {
            if parts.len() != 3 || f.is_empty() || !f.bytes().all(|b| b.is_ascii_digit()) {
                return None;
            }
            let six: String = f.chars().chain(std::iter::repeat('0')).take(6).collect();
            six.parse().ok()?
        }
    };
    NaiveTime::from_hms_micro_opt(hour, minute, second, micros)
}

fn parse_offset(s: &str) -> Option<FixedOffset> {
    if s == "Z" {
        return FixedOffset::east_opt(0);
    }
    let (sign, body) = match s.as_bytes().first()? {
        b'+' => (1, &s[1..]),
        b'-' => (-1, &s[1..]),
        _ => return None,
    };
    let (h, m, sec) = match body.len() {
        2 => (digits(body, 2)?, 0, 0),
        4 if !body.contains(':') => (digits(&body[..2], 2)?, digits(&body[2..], 2)?, 0),
        5 if body.as_bytes()[2] == b':' => (digits(&body[..2], 2)?, digits(&body[3..], 2)?, 0),
        8 if body.as_bytes()[2] == b':' && body.as_bytes()[5] == b':' => (
            digits(&body[..2], 2)?,
            digits(&body[3..5], 2)?,
            digits(&body[6..], 2)?,
        ),
        _ => return None,
    };
    // Python does not range-check offset minutes/seconds (+03:60 is +04:00).
    let total = (h * 3600 + m * 60 + sec) as i32;
    if total >= 86_400 {
        return None;
    }
    FixedOffset::east_opt(sign * total)
}
