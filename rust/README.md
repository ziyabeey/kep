# KEP Core in Rust

KEP Core's product kernel, ported module by module from the Python lab in
[`labs/core`](../labs/core), which stays the reference implementation
([ADR-0034](../docs/adr/0034-rust-core-port.md)).

| Crate | Contents | Python reference |
|---|---|---|
| `kep-canon` | Canonical JSON and SHA-256, byte-identical to `stable_hash` | `kepcore/core.py` |
| `kep-core` | `model_boundary` (model context and structured reply check), `scheduler` (`due_sources`) | `kepcore/model_boundary.py`, `kepcore/scheduler.py` |
| `kep-core` | `radar` (KEP-SRC-001 policy gate: source registry, URL check, one controlled poll through a caller-supplied transport; no HTTP client) | `kepcore/radar.py` |
| `kep-store` | `Store`: SQLite objects, observations, outbox, push queue and decision log (bundled SQLite via `rusqlite`) | `kepcore/store.py` |
| `kep-core` | `availability` (opening hours, field freshness), `isotime` | `kepcore/availability.py` |
| `kep-core` | `catalog`, `query`, `decision` (gates, `decide`, `reconcile_claims`, model guard), `distance` (georust `geo::Haversine`), `text` | `kepcore/core.py` |
| `kep-cli` | `kep-query`, same JSON output as `query.py` | `query.py` |

## Run

```bash
cd rust
cargo test                    # unit tests + parity with the Python vectors
cargo clippy --all-targets -- -D warnings
cargo run -p kep-cli -- --query ../labs/core/examples/galata_nearby.json
```

`kep-query` finds the lab catalog through the checkout it was built from. A
copied binary needs `--lab-root path/to/labs/core` or `KEP_LAB_ROOT`.

## Parity vectors

`parity/export_vectors.py` runs the Python reference on a fixed input set and
writes `parity/availability.json`, `parity/core.json`, `parity/boundary.json`, `parity/store.json` and `parity/radar.json`. The Rust tests must reproduce every case.
Cases where Rust is deliberately stricter are listed in `KNOWN_GAPS` in
`crates/kep-core/tests/parity.rs`, each with its reason.

```bash
python3 rust/parity/export_vectors.py          # regenerate after a Python change
python3 rust/parity/export_vectors.py --check  # what CI runs
```

A behaviour change is made in Python first (with its test), then the vectors
are regenerated, then Rust follows.
