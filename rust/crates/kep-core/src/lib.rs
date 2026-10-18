//! KEP Core decision kernel in Rust.
//!
//! The Python lab in `labs/core` is the reference implementation (ADR-0034).
//! Every function here is checked against vectors that the Python code writes
//! to `rust/parity/`; a mismatch is a Rust bug unless an ADR says otherwise.
//!
//! Inputs are strict JSON (`serde_json::Value`): NaN and Infinity cannot enter
//! through this boundary, unlike Python objects built in memory.

pub mod availability;
pub mod catalog;
pub mod decision;
pub mod distance;
pub mod isotime;
pub mod model_boundary;
pub mod pyval;
pub mod query;
pub mod scheduler;
pub mod text;

pub use catalog::load_catalog;
pub use decision::{Decision, decide};
pub use pyval::PyError;
pub use query::Query;
