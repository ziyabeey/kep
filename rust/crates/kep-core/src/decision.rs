//! The decision kernel from `core.py`: hard gates, missing-evidence checks,
//! ordering and the final action. No model, popularity or quality signal is
//! used; calendar, rights and factual constraints are hard gates.

use crate::availability::{OpeningStatus, field_is_fresh, opening_status_ist};
use crate::distance::{haversine_km, round4};
use crate::isotime::{IstDateTime, istanbul_dt};
use crate::pyval::{
    PyError, PyNum, dedupe, py_num, pyfloat, pyget, pyindex, pystr, python_str, truthy,
};
use crate::query::Query;
use crate::text::fold;
use serde_json::{Map, Value, json};

/// Result of [`decide`]; `to_json` matches `Decision.to_dict()`.
#[derive(Debug, Clone, PartialEq)]
pub struct Decision {
    pub action: &'static str,
    pub selected: Vec<Value>,
    pub reasons: Vec<String>,
    pub considered: usize,
    pub blocked: Map<String, Value>,
    pub policy_version: String,
}

impl Decision {
    fn silent(reason: &str) -> Decision {
        Decision {
            action: "SILENT",
            selected: vec![],
            reasons: vec![reason.to_owned()],
            considered: 0,
            blocked: Map::new(),
            policy_version: "query_aware_v0.3".to_owned(),
        }
    }

    pub fn to_json(&self) -> Value {
        json!({
            "action": self.action,
            "selected": self.selected,
            "reasons": self.reasons,
            "considered": self.considered,
            "blocked": self.blocked,
            "model_used": false,
            "policy_version": self.policy_version,
        })
    }
}

fn record(r: &Value) -> Result<&Map<String, Value>, PyError> {
    r.as_object().ok_or(PyError::TypeError)
}

fn is_str(v: Option<&Value>, s: &str) -> bool {
    v.and_then(Value::as_str) == Some(s)
}

/// `temporal_state()`: where an event sits in time relative to `when`.
pub fn temporal_state(r: &Value, when: &IstDateTime) -> Result<&'static str, PyError> {
    let r = record(r)?;
    if !is_str(Some(pyindex(r, "kind")?), "event") {
        return Ok("not_applicable");
    }
    if is_str(pyget(r, "lifecycle"), "cancelled") {
        return Ok("cancelled");
    }
    let starts = pyindex(r, "starts_at")?;
    let start = istanbul_dt(pystr(starts)?)?;
    let ends = pyget(r, "ends_at")
        .filter(|v| truthy(Some(v)))
        .unwrap_or(starts);
    let end = istanbul_dt(pystr(ends)?)?;
    if when.date_naive() > end.date_naive() {
        return Ok("expired");
    }
    if when.date_naive() < start.date_naive() {
        return Ok("future");
    }
    let event_kind = pyindex(r, "event_kind")?;
    if is_str(Some(event_kind), "program_range") || is_str(Some(event_kind), "exhibition_range") {
        return Ok("in_declared_range_not_daily_availability");
    }
    if *when < start {
        return Ok("later_today");
    }
    if pyget(r, "ends_at").is_none() {
        return Ok("duration_unknown");
    }
    Ok(if *when < end {
        "in_session"
    } else {
        "ended_today"
    })
}

/// `fresh()`: the record was checked live within `max_hours` before `when`.
pub fn fresh(r: &Value, when: &IstDateTime, max_hours: f64) -> Result<bool, PyError> {
    let r = record(r)?;
    let observed = r.get("source_observed_at");
    if !truthy(r.get("origin_live_verified")) || !truthy(observed) {
        return Ok(false);
    }
    let stamp = istanbul_dt(pystr(observed.expect("truthy"))?)?;
    let micros = (*when - stamp)
        .num_microseconds()
        .ok_or(PyError::ValueError)?;
    let age = micros as f64 / 1e6 / 3600.0;
    Ok(0.0 <= age && age <= max_hours)
}

/// Output of [`candidate_gate`]: hard exclusions, missing required evidence,
/// nonessential caveats and the straight-line distance when one was needed.
#[derive(Debug, Clone, PartialEq, Default)]
pub struct Gate {
    pub hard: Vec<&'static str>,
    pub needed: Vec<&'static str>,
    pub caveats: Vec<&'static str>,
    pub distance: Option<f64>,
}

fn valid_price(price: &Value) -> Option<f64> {
    match price {
        Value::Number(n) => n.as_f64().filter(|p| p.is_finite() && *p >= 0.0),
        _ => None,
    }
}

/// `candidate_gate()`: hard exclusion vs missing evidence vs caveats.
pub fn candidate_gate(rv: &Value, q: &Query) -> Result<Gate, PyError> {
    let r = record(rv)?;
    let mut g = Gate::default();
    let when = istanbul_dt(&q.at)?;
    let at = when.instant();
    if fold(pystr(pyindex(r, "city")?)?) != fold(&q.city) {
        g.hard.push("WRONG_CITY");
    }
    if q.kind != "any" && !is_str(Some(pyindex(r, "kind")?), &q.kind) {
        g.hard.push("WRONG_KIND");
    }
    if let Some(cat) = q.category.as_deref().filter(|c| !c.is_empty()) {
        if !is_str(Some(pyindex(r, "category")?), cat) {
            g.hard.push("WRONG_CATEGORY");
        }
    }
    if !is_str(pyget(r, "rights_scope"), "open_attribution") {
        g.hard.push("RIGHTS_NOT_APPROVED");
    }
    if is_str(pyget(r, "lifecycle"), "cancelled") {
        g.hard.push("CANCELLED");
    }
    if is_str(pyget(r, "evidence_status"), "disputed") {
        g.needed.push("DISPUTED_EVIDENCE");
    }
    if let Some(radius) = q.radius_km {
        match (pyget(r, "lat"), pyget(r, "lon")) {
            (Some(lat), Some(lon)) => {
                // Python fails in haversine_km (TypeError) if a radius comes without an origin.
                let (qlat, qlon) = (
                    q.lat.ok_or(PyError::TypeError)?,
                    q.lon.ok_or(PyError::TypeError)?,
                );
                let d = haversine_km(qlat, qlon, pyfloat(lat)?, pyfloat(lon)?)?;
                g.distance = Some(d);
                if d > radius {
                    g.hard.push("OUTSIDE_RADIUS");
                }
                g.caveats
                    .push("STRAIGHT_LINE_APPROXIMATE_NOT_WALKING_ROUTE");
            }
            _ => g.needed.push("COORDINATES_UNKNOWN"),
        }
    }
    if let Some(budget) = q.budget {
        match pyget(r, "price") {
            None => g.needed.push("PRICE_UNKNOWN"),
            Some(price) => match valid_price(price) {
                None => g.needed.push("PRICE_INVALID"),
                Some(_) if !is_str(pyget(r, "currency"), &q.currency) => {
                    g.needed.push("CURRENCY_CONVERSION_REQUIRED")
                }
                Some(_) if !field_is_fresh(rv, "price", &at, 48.0)? => {
                    g.needed.push("PRICE_FRESHNESS_UNVERIFIED")
                }
                Some(p) if p > budget => g.hard.push("OVER_BUDGET"),
                Some(_) => {}
            },
        }
    }
    if is_str(Some(pyindex(r, "kind")?), "event") {
        let state = temporal_state(rv, &when)?;
        if state == "expired" || state == "ended_today" {
            g.hard.push("EVENT_ENDED");
        }
        if !fresh(rv, &when, 48.0)? {
            g.needed.push("SOURCE_FRESHNESS_UNVERIFIED");
        }
        if is_str(pyget(r, "venue_precision"), "unresolved") {
            g.needed.push("VENUE_UNRESOLVED");
        }
        if q.require_exact_session && !is_str(Some(pyindex(r, "event_kind")?), "single_occurrence")
        {
            g.needed.push("SESSION_TIMES_UNKNOWN");
        }
        let single = is_str(Some(pyindex(r, "event_kind")?), "single_occurrence");
        if q.open_now {
            if !single {
                g.needed.push("DAILY_OPENING_HOURS_UNKNOWN");
            } else if state == "future" || state == "later_today" {
                g.hard.push("NOT_STARTED");
            } else if state == "duration_unknown" {
                g.needed.push("DURATION_UNKNOWN");
            }
        }
        if !single {
            g.caveats.push("DATE_RANGE_NOT_DAILY_SESSION_LIST");
        }
    } else {
        if q.open_now {
            let hours = r.get("opening_hours").unwrap_or(&Value::Null);
            let state = opening_status_ist(hours, &when);
            if state == OpeningStatus::Unknown {
                g.needed.push("OPENING_HOURS_UNKNOWN");
            }
            if !field_is_fresh(rv, "opening_hours", &at, 48.0)? {
                g.needed.push("SOURCE_FRESHNESS_UNVERIFIED");
            } else if state == OpeningStatus::Closed {
                g.hard.push("CLOSED_AT_REQUESTED_TIME");
            }
        }
        g.caveats
            .extend(["LIVE_STATUS_UNVERIFIED", "ADMISSION_NOT_CONFIRMED"]);
    }
    if q.quiet {
        let crowd = pyget(r, "crowd").and_then(Value::as_str);
        match crowd {
            Some(c) if ["low", "medium", "high"].contains(&c) => {
                if !field_is_fresh(rv, "crowd", &at, 0.5)? {
                    g.needed.push("CROWD_FRESHNESS_UNVERIFIED");
                } else if c != "low" {
                    g.hard.push("NOT_LOW_CROWD");
                } else {
                    g.caveats.push("LOW_CROWD_IS_NOT_ACOUSTIC_QUIETNESS_PROOF");
                }
            }
            _ => g.needed.push("CROWD_UNKNOWN"),
        }
    }
    Ok(g)
}

const POLICIES: [&str; 3] = ["query_aware", "blanket_verification", "simple_safe"];

fn codes(items: &[&'static str]) -> Value {
    Value::Array(dedupe(items).into_iter().map(Value::from).collect())
}

/// `decide()`: the action for a query over a catalog.
pub fn decide(catalog: &[Value], q: &Query, policy: &str) -> Result<Decision, PyError> {
    if !POLICIES.contains(&policy) {
        return Err(PyError::ValueError);
    }
    if q.proactive {
        if !q.push_opt_in {
            return Ok(Decision::silent("PUSH_NOT_AUTHORIZED"));
        }
        if q.mode == "work" || q.mode == "silent" {
            return Ok(Decision::silent("USER_MODE_BLOCK"));
        }
        let cap = if q.mode == "roam" { 2 } else { 1 }; // configurable, not learned optimality
        if q.already_sent_today >= cap {
            return Ok(Decision::silent("DAILY_FREQUENCY_CAP"));
        }
    }
    let when = istanbul_dt(&q.at)?;
    let at = when.instant();
    let mut blocked = Map::new();
    let mut allowed: Vec<(Option<f64>, String, Value)> = Vec::new();
    let mut unresolved: Vec<String> = Vec::new();
    for rv in catalog {
        let mut g = candidate_gate(rv, q)?;
        let r = record(rv)?;
        if policy == "blanket_verification" {
            if !fresh(rv, &when, 48.0)? {
                g.needed.push("BLANKET_FRESHNESS_REQUIRED");
            }
            if pyget(r, "price").is_none() {
                g.needed.push("BLANKET_PRICE_REQUIRED");
            }
            if pyget(r, "opening_hours").is_none() {
                g.needed.push("BLANKET_HOURS_REQUIRED");
            }
        }
        let id = python_str(pyindex(r, "id")?);
        if !g.hard.is_empty() {
            blocked.insert(id, codes(&g.hard));
            continue;
        }
        if !g.needed.is_empty() {
            blocked.insert(id.clone(), codes(&g.needed));
            unresolved.push(id);
            continue;
        }
        // No invented popularity or quality signals. Both safe policies use proximity.
        let price = match pyget(r, "price") {
            Some(p) if valid_price(p).is_some() && field_is_fresh(rv, "price", &at, 48.0)? => {
                p.clone()
            }
            _ => Value::Null,
        };
        let distance = g.distance.map(round4);
        let row = json!({
            "id": pyindex(r, "id")?,
            "name": pyindex(r, "name")?,
            "city": pyindex(r, "city")?,
            "kind": pyindex(r, "kind")?,
            "source_url": pyindex(r, "source_url")?,
            "source_record_hash": pyindex(r, "source_record_hash")?,
            "distance_km": distance,
            "distance_type": if distance.is_some() { Value::from("straight_line") } else { Value::Null },
            "caveats": g.caveats,
            "price": price,
            "evidence_status": pyindex(r, "evidence_status")?,
        });
        allowed.push((distance, id, row));
    }
    allowed.sort_by(|a, b| {
        let da = a.0.unwrap_or(f64::INFINITY);
        let db = b.0.unwrap_or(f64::INFINITY);
        da.total_cmp(&db).then_with(|| a.1.cmp(&b.1))
    });
    let version = format!("{policy}_v0.3");
    if !allowed.is_empty() {
        let selected: Vec<Value> = allowed
            .into_iter()
            .take(q.limit)
            .map(|(_, _, row)| row)
            .collect();
        let all_places = selected.iter().all(|s| is_str(s.get("kind"), "place"));
        return Ok(Decision {
            action: if all_places { "DISCOVER" } else { "RECOMMEND" },
            selected,
            reasons: vec!["REQUIRED_FIELDS_CHECKED".to_owned()],
            considered: catalog.len(),
            blocked,
            policy_version: version,
        });
    }
    if !unresolved.is_empty() {
        let mut reasons: Vec<String> = unresolved
            .iter()
            .flat_map(|id| blocked[id].as_array().expect("codes").iter())
            .filter_map(|c| c.as_str().map(str::to_owned))
            .collect();
        reasons.sort();
        reasons.dedup();
        let clarify = !reasons.is_empty()
            && reasons
                .iter()
                .all(|x| x == "CROWD_UNKNOWN" || x == "SESSION_TIMES_UNKNOWN");
        return Ok(Decision {
            action: if clarify { "CLARIFY" } else { "REFRESH" },
            selected: vec![],
            reasons,
            considered: catalog.len(),
            blocked,
            policy_version: version,
        });
    }
    Ok(Decision {
        action: "ABSTAIN",
        selected: vec![],
        reasons: vec!["NO_ELIGIBLE_RECORD".to_owned()],
        considered: catalog.len(),
        blocked,
        policy_version: version,
    })
}

/// A JSON scalar compared as Python does (`1 == 1.0 == True`). Integers stay
/// exact, as Python's are.
#[derive(Debug, Clone)]
enum PyKey {
    None,
    Num(PyNum),
    Str(String),
}

impl PartialEq for PyKey {
    fn eq(&self, other: &Self) -> bool {
        match (self, other) {
            (PyKey::None, PyKey::None) => true,
            (PyKey::Num(a), PyKey::Num(b)) => a == b,
            (PyKey::Str(a), PyKey::Str(b)) => a == b,
            _ => false,
        }
    }
}

fn py_key(v: &Value) -> Result<PyKey, PyError> {
    match v {
        Value::Null => Ok(PyKey::None),
        Value::String(s) => Ok(PyKey::Str(s.clone())),
        _ => py_num(v).map(PyKey::Num).ok_or(PyError::TypeError), // unhashable
    }
}

/// `sorted({...})` over JSON scalars: first-seen representative of each
/// equal group, then sorted; TypeError when two kinds must be compared.
fn sorted_set(values: impl Iterator<Item = Value>) -> Result<Vec<Value>, PyError> {
    let mut uniq: Vec<(PyKey, Value)> = Vec::new();
    for v in values {
        let k = py_key(&v)?;
        if !uniq.iter().any(|(u, _)| *u == k) {
            uniq.push((k, v));
        }
    }
    if uniq.len() > 1 {
        let all_num = uniq.iter().all(|(k, _)| matches!(k, PyKey::Num(_)));
        let all_str = uniq.iter().all(|(k, _)| matches!(k, PyKey::Str(_)));
        if !(all_num || all_str) {
            return Err(PyError::TypeError);
        }
        uniq.sort_by(|(a, _), (b, _)| match (a, b) {
            (PyKey::Str(x), PyKey::Str(y)) => x.cmp(y),
            (PyKey::Num(x), PyKey::Num(y)) => x.py_cmp(y).unwrap_or(std::cmp::Ordering::Equal),
            _ => std::cmp::Ordering::Equal,
        });
    }
    Ok(uniq.into_iter().map(|(_, v)| v).collect())
}

/// Claims grouped by `(entity_id, field)`, with the `"entity/field"` label.
type ClaimGroup<'a> = ((PyKey, PyKey), String, Vec<&'a Map<String, Value>>);

/// `reconcile_claims()`: conflicting same-field values stay disputed.
/// Counts are not probabilities.
pub fn reconcile_claims(claims: &[Value]) -> Result<Value, PyError> {
    let mut groups: Vec<ClaimGroup> = Vec::new();
    for cv in claims {
        let c = record(cv)?;
        let (e, f) = (pyindex(c, "entity_id")?, pyindex(c, "field")?);
        let key = (py_key(e)?, py_key(f)?);
        match groups.iter_mut().find(|(k, _, _)| *k == key) {
            Some((_, _, members)) => members.push(c),
            None => groups.push((key, format!("{}/{}", python_str(e), python_str(f)), vec![c])),
        }
    }
    let mut out = Map::new();
    for (_, label, cs) in groups {
        let field = |k: &str| -> Result<Vec<Value>, PyError> {
            cs.iter().map(|c| pyindex(c, k).cloned()).collect()
        };
        let values = sorted_set(field("value")?.into_iter())?;
        let roots = sorted_set(field("publisher_root")?.into_iter())?;
        let urls = sorted_set(field("source_url")?.into_iter())?;
        let disputed = values.len() > 1;
        out.insert(
            label,
            json!({
                "status": if disputed { "disputed" } else { "source_recorded" },
                "value": if values.len() == 1 { values[0].clone() } else { Value::Null },
                "observed_values": values,
                "publisher_roots": roots,
                "independent_publisher_count": roots.len(),
                "source_urls": urls,
                "action": if disputed { "REFRESH" } else { "NONE" },
            }),
        );
    }
    Ok(Value::Object(out))
}

/// `check_model_selection()`: a model may only pick ids the core selected.
/// This makes no API call.
pub fn check_model_selection(decision: &Decision, proposed: &[String]) -> Value {
    let permitted: Vec<String> = decision
        .selected
        .iter()
        .filter_map(|r| r.get("id").map(python_str))
        .collect();
    let mut invalid: Vec<String> = proposed
        .iter()
        .filter(|p| !permitted.contains(p))
        .cloned()
        .collect();
    invalid.sort();
    invalid.dedup();
    if !invalid.is_empty() {
        return json!({"accepted": false, "reason": "MODEL_CANNOT_BYPASS_CORE", "invalid_ids": invalid});
    }
    json!({"accepted": true, "selected_ids": dedupe(proposed), "model_called": false})
}
