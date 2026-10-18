//! `kep-query` prints exactly what `query.py` prints for the lab examples.

use std::process::Command;

#[test]
fn examples_match_python_stdout() {
    let vectors: serde_json::Value = serde_json::from_str(
        &std::fs::read_to_string(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/../../parity/core.json"
        ))
        .unwrap(),
    )
    .unwrap();
    let examples = concat!(env!("CARGO_MANIFEST_DIR"), "/../../../labs/core/examples");
    for case in vectors["cli"].as_array().unwrap() {
        let name = case["name"].as_str().unwrap();
        let out = Command::new(env!("CARGO_BIN_EXE_kep-query"))
            .args(["--query", &format!("{examples}/{name}")])
            .output()
            .unwrap();
        assert!(
            out.status.success(),
            "{name}: {}",
            String::from_utf8_lossy(&out.stderr)
        );
        let expected = format!("{}\n", case["stdout"].as_str().unwrap());
        assert_eq!(String::from_utf8(out.stdout).unwrap(), expected, "{name}");
    }
}

#[test]
fn bad_query_exits_2() {
    let dir = std::env::temp_dir().join(format!("kep-cli-test-{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    let path = dir.join("q.json");
    std::fs::write(&path, r#"{"city": "İstanbul", "limit": 0}"#).unwrap();
    let out = Command::new(env!("CARGO_BIN_EXE_kep-query"))
        .arg("--query")
        .arg(&path)
        .output()
        .unwrap();
    assert_eq!(out.status.code(), Some(2));
    std::fs::remove_dir_all(&dir).ok();
}
