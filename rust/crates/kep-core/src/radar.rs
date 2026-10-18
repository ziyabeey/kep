//! KEP-SRC-001 policy gate from `radar.py`: the bounded source registry and a
//! single controlled poll. The HTTPS client itself stays in Python; here the
//! caller passes the transport, so nothing reaches the network unless the
//! caller wires one in.
//!
//! Differences from the reference, all failing closed:
//! - A bracketed host (`https://[...]/`) is rejected. Python rejects most of
//!   these too, but 3.12+ accepts an IPvFuture form such as `[v1.fe]`.
//! - Registry fields must have their declared JSON types (`TypeError`).
//! - A response body must be UTF-8 (a UTF-8 BOM is allowed). Python would also
//!   decode UTF-16/32 bodies and accept `NaN` or lone surrogates in the JSON;
//!   Rust pauses those for schema review instead.

use crate::isotime::{IsoDateTime, istanbul_dt, parse_iso};
use crate::pyval::{PyError, PyNum, py_eq, py_isspace, py_num};
use crate::text::py_strip;
use chrono::{DateTime, FixedOffset, Utc};
use kep_canon::sha256_hex;
use serde_json::{Map, Value, json};
use unicode_normalization::UnicodeNormalization;

const REGISTERED_USES: [&str; 2] = ["research_ingest", "consumer_display"];
const VALID_STATUSES: [&str; 4] = ["pending", "approved", "paused", "blocked"];
const VALID_FORMATS: [&str; 2] = ["izmir_event_json", "website_review_required"];
const EVENT_FIELDS: [&str; 9] = [
    "Id",
    "Tur",
    "Adi",
    "EtkinlikBaslamaTarihi",
    "EtkinlikBitisTarihi",
    "EtkinlikMerkezi",
    "UcretsizMi",
    "EtkinlikUrl",
    "BiletSatisLinki",
];
const USER_AGENT: &str = "KEPResearch/0.4 (+https://github.com/ziyabeey/kep)";

/// Strict dotted-quad IPv4, as `ipaddress.ip_address` parses it.
fn is_ipv4(host: &str) -> bool {
    let parts: Vec<&str> = host.split('.').collect();
    parts.len() == 4
        && parts.iter().all(|p| {
            !p.is_empty()
                && p.len() <= 3
                && p.bytes().all(|b| b.is_ascii_digit())
                && !(p.len() > 1 && p.starts_with('0'))
                && p.parse::<u16>().is_ok_and(|v| v <= 255)
        })
}

/// `_public_https()`: the lowercased host of a plain public HTTPS URL, or
/// ValueError. This syntactic check alone is NOT an egress firewall.
pub fn public_https(url: &str) -> Result<String, PyError> {
    let bad = || PyError::ValueError;
    if url.is_empty() || url.chars().any(|c| py_isspace(c) || (c as u32) < 32) {
        return Err(bad());
    }
    if url.contains('\\') {
        return Err(bad());
    }
    // urlsplit: a scheme is the text before the first ':' when it starts
    // with an ASCII letter and uses only scheme characters; it must be https.
    let (scheme, rest) = url.split_once(':').ok_or_else(bad)?;
    if !scheme.eq_ignore_ascii_case("https") {
        return Err(bad());
    }
    let after = rest.strip_prefix("//").ok_or_else(bad)?;
    let end = after.find(['/', '?', '#']).unwrap_or(after.len());
    let (netloc, tail) = after.split_at(end);
    if netloc.contains(['[', ']']) {
        return Err(bad());
    }
    if let Some((_, fragment)) = tail.split_once('#') {
        if !fragment.is_empty() {
            return Err(bad());
        }
    }
    if !netloc.is_ascii() {
        // Characters such as U+2100 expand to 'a/c' under NFKC.
        let n: String = netloc.chars().filter(|c| !"@:#?".contains(*c)).collect();
        let normalized: String = n.nfkc().collect();
        if normalized != n && normalized.contains(['/', '?', '#', '@', ':']) {
            return Err(bad());
        }
    }
    let (hostinfo, userinfo) = match netloc.rsplit_once('@') {
        Some((user, host)) => (host, Some(user)),
        None => (netloc, None),
    };
    if let Some(userinfo) = userinfo {
        let (username, password) = match userinfo.split_once(':') {
            Some((u, p)) => (u, p),
            None => (userinfo, ""),
        };
        if !username.is_empty() || !password.is_empty() {
            return Err(bad());
        }
    }
    let (hostname, port) = match hostinfo.split_once(':') {
        Some((h, p)) => (h, p),
        None => (hostinfo, ""),
    };
    if !port.is_empty() {
        if !port.bytes().all(|b| b.is_ascii_digit()) {
            return Err(bad());
        }
        let digits = port.trim_start_matches('0');
        if digits.len() > 5 || digits.parse::<u32>().unwrap_or(0) > 65535 {
            return Err(bad()); // out of range
        }
        if digits != "443" {
            return Err(bad());
        }
    }
    let lowered = hostname.to_lowercase();
    let host = lowered.trim_end_matches('.');
    if host.is_empty() {
        return Err(bad());
    }
    if host == "localhost"
        || [".localhost", ".local", ".internal"]
            .iter()
            .any(|s| host.ends_with(s))
        || !host.contains('.')
    {
        return Err(bad()); // local origins are forbidden
    }
    if is_ipv4(host) {
        return Err(bad()); // IP literal origins are forbidden
    }
    Ok(host.to_owned())
}

/// A registry entry (`radar.Source`).
#[derive(Debug, Clone, PartialEq)]
pub struct Source {
    pub id: String,
    pub url: String,
    pub city: String,
    pub format: String,
    pub status: String,
    pub approved_uses: Vec<String>,
    pub license: String,
    pub rights_evidence_url: String,
    pub rights_reviewed_at: String,
    pub attribution: String,
    pub min_poll_minutes: i64,
    pub max_poll_minutes: i64,
    pub daily_request_cap: i64,
    pub max_response_bytes: i64,
    pub review_note: String,
}

const SOURCE_FIELDS: [&str; 15] = [
    "id",
    "url",
    "city",
    "format",
    "status",
    "approved_uses",
    "license",
    "rights_evidence_url",
    "rights_reviewed_at",
    "attribution",
    "min_poll_minutes",
    "max_poll_minutes",
    "daily_request_cap",
    "max_response_bytes",
    "review_note",
];

impl Source {
    /// `Source.parse()`: ValueError for unknown fields, bad `approved_uses`
    /// or failed validation; TypeError for missing or ill-typed fields.
    pub fn parse(raw: &Value) -> Result<Source, PyError> {
        let Some(obj) = raw.as_object() else {
            return Err(PyError::ValueError); // unsupported source fields
        };
        if obj.keys().any(|k| !SOURCE_FIELDS.contains(&k.as_str())) {
            return Err(PyError::ValueError);
        }
        let approved_uses = match obj.get("approved_uses") {
            None => vec![],
            Some(Value::Array(a)) => a
                .iter()
                .map(|x| x.as_str().map(str::to_owned))
                .collect::<Option<Vec<_>>>()
                .ok_or(PyError::ValueError)?,
            Some(_) => return Err(PyError::ValueError),
        };
        let required = |k: &str| match obj.get(k) {
            Some(Value::String(s)) => Ok(s.clone()),
            _ => Err(PyError::TypeError),
        };
        let text = |k: &str| match obj.get(k) {
            None => Ok(String::new()),
            Some(Value::String(s)) => Ok(s.clone()),
            Some(_) => Err(PyError::TypeError),
        };
        let int = |k: &str, default: i64| match obj.get(k) {
            None => Ok(default),
            Some(Value::Number(n)) => n.as_i64().ok_or(PyError::TypeError),
            Some(_) => Err(PyError::TypeError),
        };
        let source = Source {
            id: required("id")?,
            url: required("url")?,
            city: required("city")?,
            format: required("format")?,
            status: required("status")?,
            approved_uses,
            license: text("license")?,
            rights_evidence_url: text("rights_evidence_url")?,
            rights_reviewed_at: text("rights_reviewed_at")?,
            attribution: text("attribution")?,
            min_poll_minutes: int("min_poll_minutes", 360)?,
            max_poll_minutes: int("max_poll_minutes", 1440)?,
            daily_request_cap: int("daily_request_cap", 4)?,
            max_response_bytes: int("max_response_bytes", 2_000_000)?,
            review_note: text("review_note")?,
        };
        source.validate()?;
        Ok(source)
    }

    /// `Source.validate()`, in the reference's order.
    pub fn validate(&self) -> Result<(), PyError> {
        let bad = Err(PyError::ValueError);
        if self.id.is_empty()
            || !self
                .id
                .chars()
                .all(|c| c.is_ascii_alphanumeric() || c == '_')
        {
            return bad;
        }
        public_https(&self.url)?;
        if py_strip(&self.city).is_empty()
            || !VALID_FORMATS.contains(&self.format.as_str())
            || !VALID_STATUSES.contains(&self.status.as_str())
        {
            return bad;
        }
        let uses = &self.approved_uses;
        let unique = uses.iter().enumerate().all(|(i, u)| !uses[..i].contains(u));
        if !uses.iter().all(|u| REGISTERED_USES.contains(&u.as_str())) || !unique {
            return bad;
        }
        if self.status != "approved" && !uses.is_empty() {
            return bad; // a pending/blocked source cannot grant data rights
        }
        if self.status == "approved" {
            if uses.is_empty()
                || self.license.is_empty()
                || self.rights_evidence_url.is_empty()
                || self.rights_reviewed_at.is_empty()
            {
                return bad; // an approved source needs documented rights review
            }
            public_https(&self.rights_evidence_url)?;
            parse_iso(&self.rights_reviewed_at).ok_or(PyError::ValueError)?;
        } else if self.format != "website_review_required" && self.review_note.is_empty() {
            return bad;
        }
        if !(1 <= self.min_poll_minutes
            && self.min_poll_minutes <= self.max_poll_minutes
            && self.max_poll_minutes <= 43200)
        {
            return bad;
        }
        if !(1..=10000).contains(&self.daily_request_cap) {
            return bad;
        }
        if !(1024..=5_000_000).contains(&self.max_response_bytes) {
            return bad;
        }
        Ok(())
    }

    /// `Source.allows()`.
    pub fn allows(&self, purpose: &str) -> bool {
        self.status == "approved" && self.approved_uses.iter().any(|u| u == purpose)
    }
}

/// The registry document behind `load_sources()`, already parsed as JSON.
pub fn parse_registry(data: &Value) -> Result<Vec<Source>, PyError> {
    let obj = data.as_object().ok_or(PyError::ValueError)?;
    let keys_ok = obj.len() == 2 && obj.contains_key("version") && obj.contains_key("sources");
    if !keys_ok || !py_eq(&obj["version"], &json!(1)) {
        return Err(PyError::ValueError); // unsupported registry version
    }
    let raw_sources = obj["sources"].as_array().ok_or(PyError::ValueError)?;
    let mut out: Vec<Source> = Vec::with_capacity(raw_sources.len());
    for raw in raw_sources {
        let source = Source::parse(raw)?;
        if out.iter().any(|s| s.id == source.id) {
            return Err(PyError::ValueError); // duplicate source ID
        }
        out.push(source);
    }
    Ok(out)
}

/// `load_sources(path)`; invalid JSON is reported as ValueError.
pub fn load_sources(path: &std::path::Path) -> Result<Vec<Source>, PyError> {
    let text = std::fs::read_to_string(path).map_err(|_| PyError::ValueError)?;
    let data: Value = serde_json::from_str(&text).map_err(|_| PyError::ValueError)?;
    parse_registry(&data)
}

/// Per-source poll bookkeeping (`radar.PollState`).
#[derive(Debug, Clone, PartialEq, Default)]
pub struct PollState {
    pub last_attempt_at: Option<String>,
    pub last_day: Option<String>,
    pub requests_today: i64,
    pub etag: Option<String>,
    pub last_modified: Option<String>,
    pub last_body_sha256: Option<String>,
    pub paused_reason: Option<String>,
}

const STATE_FIELDS: [&str; 7] = [
    "last_attempt_at",
    "last_day",
    "requests_today",
    "etag",
    "last_modified",
    "last_body_sha256",
    "paused_reason",
];

impl PollState {
    /// `PollState(**object)`; TypeError for unknown or ill-typed fields.
    pub fn from_json(value: &Value) -> Result<PollState, PyError> {
        let obj = value.as_object().ok_or(PyError::TypeError)?;
        if obj.keys().any(|k| !STATE_FIELDS.contains(&k.as_str())) {
            return Err(PyError::TypeError);
        }
        let opt = |k: &str| match obj.get(k) {
            None | Some(Value::Null) => Ok(None),
            Some(Value::String(s)) => Ok(Some(s.clone())),
            Some(_) => Err(PyError::TypeError),
        };
        Ok(PollState {
            last_attempt_at: opt("last_attempt_at")?,
            last_day: opt("last_day")?,
            requests_today: match obj.get("requests_today") {
                None => 0,
                Some(Value::Number(n)) => n.as_i64().ok_or(PyError::TypeError)?,
                Some(_) => return Err(PyError::TypeError),
            },
            etag: opt("etag")?,
            last_modified: opt("last_modified")?,
            last_body_sha256: opt("last_body_sha256")?,
            paused_reason: opt("paused_reason")?,
        })
    }

    /// `dataclasses.asdict(state)`.
    pub fn to_json(&self) -> Value {
        json!({
            "last_attempt_at": self.last_attempt_at,
            "last_day": self.last_day,
            "requests_today": self.requests_today,
            "etag": self.etag,
            "last_modified": self.last_modified,
            "last_body_sha256": self.last_body_sha256,
            "paused_reason": self.paused_reason,
        })
    }
}

/// What a transport returned (`radar.FetchResponse`). Headers keep their
/// order; repeated names behave as a Python dict built from them.
#[derive(Debug, Clone, PartialEq, Default)]
pub struct FetchResponse {
    pub status: i64,
    pub body: Vec<u8>,
    pub headers: Vec<(String, String)>,
}

/// A transport failure.
#[derive(Debug, Clone, PartialEq)]
pub enum TransportError {
    /// An `OSError` (or `TimeoutError`) by class name: one attempt is used up
    /// and the poll reports `error`.
    Network(String),
    /// Anything else propagates, as in the reference.
    Other(PyError),
}

/// The transport the caller wires in: `(url, request headers, max bytes)`.
pub type Transport<'a> =
    dyn FnMut(&str, &[(String, String)], i64) -> Result<FetchResponse, TransportError> + 'a;

/// Outcome of [`poll`] (`radar.PollResult`).
#[derive(Debug, Clone, PartialEq)]
pub struct PollResult {
    pub status: &'static str,
    pub state: PollState,
    pub envelope: Option<Value>,
    pub reason: Option<String>,
}

impl PollResult {
    fn new(status: &'static str, state: PollState, reason: Option<String>) -> PollResult {
        PollResult {
            status,
            state,
            envelope: None,
            reason,
        }
    }

    /// `dataclasses.asdict(result)`.
    pub fn to_json(&self) -> Value {
        json!({
            "status": self.status,
            "state": self.state.to_json(),
            "envelope": self.envelope,
            "reason": self.reason,
        })
    }
}

/// `{str(k).lower(): str(v) for k, v in dict(pairs).items()}`: a key keeps its
/// first position and takes its last value.
fn lowered_headers(pairs: &[(String, String)]) -> Vec<(String, String)> {
    let mut out: Vec<(String, String)> = Vec::new();
    for (k, v) in pairs {
        let k = k.to_lowercase();
        match out.iter_mut().find(|(have, _)| *have == k) {
            Some(slot) => slot.1 = v.clone(),
            None => out.push((k, v.clone())),
        }
    }
    out
}

fn header<'a>(headers: &'a [(String, String)], name: &str) -> Option<&'a str> {
    headers
        .iter()
        .find(|(k, _)| k == name)
        .map(|(_, v)| v.as_str())
}

/// `_select_izmir_events()`: the selected fields of each event, or the name
/// of the exception the reference raises (all caught by [`poll`]).
fn select_izmir_events(body: &[u8]) -> Result<Vec<Value>, &'static str> {
    let body = body.strip_prefix(b"\xef\xbb\xbf").unwrap_or(body);
    let text = std::str::from_utf8(body).map_err(|_| "UnicodeDecodeError")?;
    let raw: Value = serde_json::from_str(text).map_err(|_| "JSONDecodeError")?;
    let items = raw.as_array().ok_or("ValueError")?;
    if items.len() > 20_000 || items.is_empty() {
        return Err("ValueError"); // unexpected shape or size, or suspicious empty feed
    }
    let mut records = Vec::with_capacity(items.len());
    let mut seen: Vec<PyNum> = Vec::new();
    for item in items {
        let item = item.as_object().ok_or("ValueError")?;
        if EVENT_FIELDS[..6].iter().any(|k| !item.contains_key(*k)) {
            return Err("ValueError"); // missing required event field
        }
        let id = match &item["Id"] {
            Value::Number(_) => match py_num(&item["Id"]) {
                Some(n @ PyNum::Int(_)) => n,
                _ => return Err("ValueError"), // a float
            },
            _ => return Err("ValueError"),
        };
        if seen.contains(&id) {
            return Err("ValueError"); // duplicate event ID
        }
        seen.push(id);
        let strings = [
            "Tur",
            "Adi",
            "EtkinlikBaslamaTarihi",
            "EtkinlikBitisTarihi",
            "EtkinlikMerkezi",
        ];
        if strings
            .iter()
            .any(|k| item[*k].as_str().is_none_or(|s| py_strip(s).is_empty()))
        {
            return Err("ValueError"); // invalid required event string
        }
        let start = istanbul_dt(item["EtkinlikBaslamaTarihi"].as_str().expect("checked"));
        let end = istanbul_dt(item["EtkinlikBitisTarihi"].as_str().expect("checked"));
        let (Ok(start), Ok(end)) = (start, end) else {
            return Err("ValueError");
        };
        if end < start {
            return Err("ValueError"); // reversed event interval
        }
        if item
            .get("UcretsizMi")
            .is_some_and(|v| !v.is_null() && !v.is_boolean())
        {
            return Err("ValueError"); // invalid free flag
        }
        for k in ["EtkinlikUrl", "BiletSatisLinki"] {
            if item.get(k).is_some_and(|v| !v.is_null() && !v.is_string()) {
                return Err("ValueError"); // invalid optional event link
            }
        }
        let mut record = Map::new();
        for k in EVENT_FIELDS {
            record.insert(k.to_owned(), item.get(k).cloned().unwrap_or(Value::Null));
        }
        records.push(Value::Object(record));
    }
    Ok(records)
}

/// `poll()`: one controlled fetch. Nothing is published or stored.
pub fn poll(
    source: &Source,
    now: &DateTime<FixedOffset>,
    state: &PollState,
    transport: &mut Transport<'_>,
    purpose: &str,
) -> Result<PollResult, PyError> {
    if !source.allows(purpose) {
        return Ok(PollResult::new(
            "denied",
            state.clone(),
            Some("SOURCE_RIGHTS_NOT_APPROVED".into()),
        ));
    }
    if source.format != "izmir_event_json" {
        return Ok(PollResult::new(
            "denied",
            state.clone(),
            Some("ADAPTER_NOT_APPROVED".into()),
        ));
    }
    let instant = now.with_timezone(&Utc).fixed_offset();
    let today = instant.date_naive().format("%Y-%m-%d").to_string();
    let count = if state.last_day.as_deref() == Some(today.as_str()) {
        state.requests_today
    } else {
        0
    };
    if let Some(reason) = state.paused_reason.as_ref().filter(|r| !r.is_empty()) {
        return Ok(PollResult::new(
            "paused",
            state.clone(),
            Some(reason.clone()),
        ));
    }
    if let Some(last) = &state.last_attempt_at {
        let Some(IsoDateTime::Aware(last)) = parse_iso(last) else {
            return Err(PyError::ValueError); // invalid stored timestamp
        };
        let micros = (instant - last)
            .num_microseconds()
            .ok_or(PyError::ValueError)?;
        let elapsed = micros as f64 / 1e6 / 60.0;
        if elapsed < 0.0 {
            return Ok(PollResult::new(
                "denied",
                state.clone(),
                Some("CLOCK_MOVED_BACKWARDS".into()),
            ));
        }
        if elapsed < source.min_poll_minutes as f64 {
            return Ok(PollResult::new(
                "skipped",
                state.clone(),
                Some("MIN_INTERVAL_NOT_ELAPSED".into()),
            ));
        }
    }
    if count >= source.daily_request_cap {
        return Ok(PollResult::new(
            "skipped",
            state.clone(),
            Some("DAILY_QUOTA_REACHED".into()),
        ));
    }
    let mut request_headers = vec![
        ("User-Agent".to_owned(), USER_AGENT.to_owned()),
        ("Accept".to_owned(), "application/json".to_owned()),
    ];
    if let Some(etag) = state.etag.as_ref().filter(|e| !e.is_empty()) {
        request_headers.push(("If-None-Match".to_owned(), etag.clone()));
    }
    if let Some(lm) = state.last_modified.as_ref().filter(|e| !e.is_empty()) {
        request_headers.push(("If-Modified-Since".to_owned(), lm.clone()));
    }
    let captured_at = IsoDateTime::Aware(instant).python_isoformat();
    let mut new_state = PollState {
        last_attempt_at: Some(captured_at.clone()),
        last_day: Some(today.clone()),
        requests_today: count + 1,
        ..state.clone()
    };
    let result = match transport(&source.url, &request_headers, source.max_response_bytes) {
        Ok(r) => r,
        // A failed request still uses one attempt; no retry storm, no partial update.
        Err(TransportError::Network(name)) => {
            return Ok(PollResult::new(
                "error",
                new_state,
                Some(format!("NETWORK_ERROR:{name}")),
            ));
        }
        Err(TransportError::Other(e)) => return Err(e),
    };
    let headers = lowered_headers(&result.headers);
    if [401, 403, 429].contains(&result.status) {
        let reason = format!("HTTP_{}_REVIEW_REQUIRED", result.status);
        new_state.paused_reason = Some(reason.clone());
        return Ok(PollResult::new("paused", new_state, Some(reason)));
    }
    if result.status == 304 {
        return Ok(PollResult::new("not_modified", new_state, None));
    }
    if result.status != 200 {
        return Ok(PollResult::new(
            "error",
            new_state,
            Some(format!("HTTP_{}", result.status)),
        ));
    }
    if result.body.len() as i64 > source.max_response_bytes {
        new_state.paused_reason = Some("RESPONSE_TOO_LARGE".into());
        return Ok(PollResult::new(
            "paused",
            new_state,
            Some("RESPONSE_TOO_LARGE".into()),
        ));
    }
    let records = match select_izmir_events(&result.body) {
        Ok(r) => r,
        Err(name) => {
            new_state.paused_reason = Some("SCHEMA_REVIEW_REQUIRED".into());
            return Ok(PollResult::new(
                "paused",
                new_state,
                Some(format!("SCHEMA_REVIEW_REQUIRED:{name}")),
            ));
        }
    };
    let digest = sha256_hex(&result.body);
    new_state.etag = header(&headers, "etag")
        .map(str::to_owned)
        .or(state.etag.clone());
    new_state.last_modified = header(&headers, "last-modified")
        .map(str::to_owned)
        .or(state.last_modified.clone());
    new_state.last_body_sha256 = Some(digest.clone());
    if state.last_body_sha256.as_deref() == Some(digest.as_str()) {
        return Ok(PollResult::new("unchanged", new_state, None));
    }
    let mut kept = Map::new();
    for (k, v) in &headers {
        if ["etag", "last-modified", "cache-control", "date"].contains(&k.as_str()) {
            kept.insert(k.clone(), Value::String(v.clone()));
        }
    }
    let envelope = json!({
        "meta": {
            "source_id": source.id,
            "source_city": source.city,
            "source_url": source.url,
            "license": source.license,
            "rights_evidence_url": source.rights_evidence_url,
            "attribution": source.attribution,
            "acquisition_method": "reviewed_api_json",
            "http_retrieved_at": captured_at,
            "acquired_date": today,
            "source_observed_at": null,
            "origin_live_verified": false,
            "rights_scope": "research_only",
            "consumer_display_approved": false,
            "response_headers": kept,
            "sha256_http_body": digest,
            "selected_fields_only": true,
            "review_required": "Response retrieval is not event-level live verification",
        },
        "records": records,
    });
    Ok(PollResult {
        status: "changed",
        state: new_state,
        envelope: Some(envelope),
        reason: None,
    })
}
