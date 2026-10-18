//! `kep-query --query FILE [--lab-root DIR]`
//!
//! Structured-query demo, the Rust counterpart of `labs/core/query.py`.
//! NOT a natural-language model or a web consumer app. Prints the decision
//! as the Python script does (same JSON, same layout).

use kep_canon::python_json_pretty;
use kep_core::{Query, decide, load_catalog};
use std::path::PathBuf;
use std::process::ExitCode;

const USAGE: &str = "usage: kep-query --query QUERY [--lab-root DIR]";

fn fail(message: &str) -> ExitCode {
    eprintln!("{USAGE}\nkep-query: error: {message}");
    ExitCode::from(2)
}

fn main() -> ExitCode {
    let mut query: Option<PathBuf> = None;
    let mut lab_root = std::env::var_os("KEP_LAB_ROOT")
        .map(PathBuf::from)
        .unwrap_or_else(|| {
            PathBuf::from(concat!(env!("CARGO_MANIFEST_DIR"), "/../../../labs/core"))
        });
    let mut args = std::env::args_os().skip(1);
    while let Some(arg) = args.next() {
        match arg.to_str() {
            Some("--query") => query = args.next().map(PathBuf::from),
            Some("--lab-root") => match args.next() {
                Some(dir) => lab_root = PathBuf::from(dir),
                None => return fail("argument --lab-root: expected one argument"),
            },
            Some("-h" | "--help") => {
                println!("{USAGE}");
                return ExitCode::SUCCESS;
            }
            _ => {
                return fail(&format!(
                    "unrecognized arguments: {}",
                    arg.to_string_lossy()
                ));
            }
        }
    }
    let Some(query_path) = query else {
        return fail("the following arguments are required: --query");
    };
    let text = match std::fs::read_to_string(&query_path) {
        Ok(t) => t,
        Err(e) => return fail(&e.to_string()),
    };
    let value: serde_json::Value = match serde_json::from_str(&text) {
        Ok(v) => v,
        Err(e) => return fail(&e.to_string()),
    };
    let catalog = match load_catalog(&lab_root) {
        Ok(c) => c,
        Err(e) => return fail(&e.to_string()),
    };
    let decision = Query::from_json(&value).and_then(|q| decide(&catalog, &q, "query_aware"));
    match decision {
        Ok(d) => {
            println!("{}", python_json_pretty(&d.to_json(), 2));
            ExitCode::SUCCESS
        }
        Err(e) => fail(&format!("invalid query ({})", e.name())),
    }
}
