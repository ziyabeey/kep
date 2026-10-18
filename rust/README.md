# KEP Core in Rust

KEP Core's product kernel, ported module by module from the Python lab in
[`labs/core`](../labs/core), which stays the reference implementation
([ADR-0034](../docs/adr/0034-rust-core-port.md)).

| Crate | Contents | Python reference |
|---|---|---|
| `kep-canon` | Canonical JSON and SHA-256, byte-identical to `stable_hash` | `kepcore/core.py` |
| `kep-core` | `availability` (opening hours, field freshness), `isotime` | `kepcore/availability.py` |

## Run

```bash
cd rust
cargo test                    # unit tests + parity with the Python vectors
cargo clippy --all-targets -- -D warnings
```

## Parity vectors

`parity/export_vectors.py` runs the Python reference on a fixed input set and
writes `parity/availability.json`. The Rust tests must reproduce every case.
Cases where Rust is deliberately stricter are listed in `KNOWN_GAPS` in
`crates/kep-core/tests/parity.rs`, each with its reason.

```bash
python3 rust/parity/export_vectors.py          # regenerate after a Python change
python3 rust/parity/export_vectors.py --check  # what CI runs
```

A behaviour change is made in Python first (with its test), then the vectors
are regenerated, then Rust follows.
