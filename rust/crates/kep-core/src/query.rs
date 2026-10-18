//! The structured query (`core.Query`) and its validation.

use crate::distance::haversine_km;
use crate::isotime::istanbul_dt;
use crate::pyval::PyError;
use crate::text::py_strip;
use serde_json::Value;

pub const DEFAULT_AT: &str = "2026-10-10T18:00:00+03:00";

/// A structured discovery query. Field meanings follow `core.Query`.
#[derive(Debug, Clone, PartialEq)]
pub struct Query {
    pub city: String,
    pub kind: String,
    pub category: Option<String>,
    pub at: String,
    pub budget: Option<f64>,
    pub currency: String,
    pub lat: Option<f64>,
    pub lon: Option<f64>,
    pub radius_km: Option<f64>,
    pub open_now: bool,
    pub quiet: bool,
    pub require_exact_session: bool,
    pub mode: String,
    pub proactive: bool,
    pub push_opt_in: bool,
    pub already_sent_today: i64,
    pub limit: usize,
}

const FIELDS: [&str; 17] = [
    "city",
    "kind",
    "category",
    "at",
    "budget",
    "currency",
    "lat",
    "lon",
    "radius_km",
    "open_now",
    "quiet",
    "require_exact_session",
    "mode",
    "proactive",
    "push_opt_in",
    "already_sent_today",
    "limit",
];

impl Query {
    /// `Query(**object)`: TypeError for unknown or missing fields and for
    /// ill-typed values (the reference does not type-check, so a few odd
    /// inputs Python tolerates, like `limit: true`, are rejected here);
    /// ValueError for values `__post_init__` rejects.
    pub fn from_json(value: &Value) -> Result<Query, PyError> {
        let obj = value.as_object().ok_or(PyError::TypeError)?;
        if obj.keys().any(|k| !FIELDS.contains(&k.as_str())) {
            return Err(PyError::TypeError);
        }
        let text = |k: &str, default: &str| -> Result<String, PyError> {
            match obj.get(k) {
                None => Ok(default.to_owned()),
                Some(Value::String(s)) => Ok(s.clone()),
                Some(_) => Err(PyError::TypeError),
            }
        };
        let opt_text = |k: &str| -> Result<Option<String>, PyError> {
            match obj.get(k) {
                None | Some(Value::Null) => Ok(None),
                Some(Value::String(s)) => Ok(Some(s.clone())),
                Some(_) => Err(PyError::TypeError),
            }
        };
        let opt_num = |k: &str| -> Result<Option<f64>, PyError> {
            match obj.get(k) {
                None | Some(Value::Null) => Ok(None),
                Some(Value::Number(n)) => n.as_f64().map(Some).ok_or(PyError::TypeError),
                Some(_) => Err(PyError::TypeError),
            }
        };
        let flag = |k: &str| -> Result<bool, PyError> {
            match obj.get(k) {
                None => Ok(false),
                Some(Value::Bool(b)) => Ok(*b),
                Some(_) => Err(PyError::TypeError),
            }
        };
        let int = |k: &str, default: i64| -> Result<i64, PyError> {
            match obj.get(k) {
                None => Ok(default),
                Some(Value::Number(n)) => n.as_i64().ok_or(PyError::TypeError),
                Some(_) => Err(PyError::TypeError),
            }
        };
        let Some(Value::String(city)) = obj.get("city") else {
            return Err(PyError::TypeError); // missing required argument
        };
        let limit = int("limit", 3)?;
        let q = Query {
            city: city.clone(),
            kind: text("kind", "any")?,
            category: opt_text("category")?,
            at: text("at", DEFAULT_AT)?,
            budget: opt_num("budget")?,
            currency: text("currency", "TRY")?,
            lat: opt_num("lat")?,
            lon: opt_num("lon")?,
            radius_km: opt_num("radius_km")?,
            open_now: flag("open_now")?,
            quiet: flag("quiet")?,
            require_exact_session: flag("require_exact_session")?,
            mode: text("mode", "balanced")?,
            proactive: flag("proactive")?,
            push_opt_in: flag("push_opt_in")?,
            already_sent_today: int("already_sent_today", 0)?,
            limit: if (1..=50).contains(&limit) {
                limit as usize
            } else {
                0
            },
        };
        q.validate(limit)?;
        Ok(q)
    }

    /// `__post_init__`, in the reference's order.
    fn validate(&self, limit: i64) -> Result<(), PyError> {
        if !["TRY", "EUR", "USD", "GBP", "MXN"].contains(&self.currency.as_str()) {
            return Err(PyError::ValueError);
        }
        if self.lat.is_none() != self.lon.is_none() {
            return Err(PyError::ValueError);
        }
        if let (Some(lat), Some(lon)) = (self.lat, self.lon) {
            haversine_km(lat, lon, lat, lon)?;
        }
        if !["work", "roam", "balanced", "silent"].contains(&self.mode.as_str()) {
            return Err(PyError::ValueError);
        }
        if !["event", "place", "any"].contains(&self.kind.as_str()) {
            return Err(PyError::ValueError);
        }
        if py_strip(&self.city).is_empty() {
            return Err(PyError::ValueError);
        }
        if let Some(b) = self.budget {
            if !b.is_finite() || b < 0.0 {
                return Err(PyError::ValueError);
            }
        }
        if let Some(r) = self.radius_km {
            if r < 0.0 || !r.is_finite() {
                return Err(PyError::ValueError);
            }
            let (Some(lat), Some(lon)) = (self.lat, self.lon) else {
                return Err(PyError::ValueError);
            };
            haversine_km(lat, lon, lat, lon)?;
        }
        if !(1..=50).contains(&limit) {
            return Err(PyError::ValueError);
        }
        if self.already_sent_today < 0 {
            return Err(PyError::ValueError);
        }
        istanbul_dt(&self.at)?;
        Ok(())
    }
}
