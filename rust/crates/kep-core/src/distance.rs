//! Straight-line distance, computed with georust's `geo::Haversine`.

use crate::pyval::PyError;
use geo::{Distance, Haversine, Point};

/// `haversine_km()`: great-circle distance in km between two lat/lon points.
///
/// Inputs are validated exactly as the Python reference does (finite, in
/// range) before `geo` computes the distance. `geo` uses the same mean Earth
/// radius (6371.0088 km) and formula, but evaluates it in a different order,
/// so results can differ from Python in the last bit. They agree after the
/// 4-decimal rounding KEP reports (`round(d, 4)`); see the parity tests.
pub fn haversine_km(lat1: f64, lon1: f64, lat2: f64, lon2: f64) -> Result<f64, PyError> {
    if ![lat1, lon1, lat2, lon2].iter().all(|v| v.is_finite()) {
        return Err(PyError::ValueError); // Coordinates must be finite
    }
    let lat_ok = |v: f64| (-90.0..=90.0).contains(&v);
    let lon_ok = |v: f64| (-180.0..=180.0).contains(&v);
    if !(lat_ok(lat1) && lat_ok(lat2) && lon_ok(lon1) && lon_ok(lon2)) {
        return Err(PyError::ValueError); // Invalid coordinate range
    }
    let meters = Haversine.distance(Point::new(lon1, lat1), Point::new(lon2, lat2));
    if meters.is_nan() {
        // Rounding pushed the haversine term just above 1 (antipodal points).
        // Python clamps it to 1, which is half the Earth's circumference.
        return Ok(6371.0088 * 2.0 * 1.0_f64.asin());
    }
    Ok(meters / 1000.0)
}

/// Python's `round(x, 4)`: correctly rounded to 4 decimals, ties to even.
pub fn round4(x: f64) -> f64 {
    format!("{x:.4}").parse().unwrap_or(x)
}
