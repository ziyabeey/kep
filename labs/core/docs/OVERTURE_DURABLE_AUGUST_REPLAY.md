# KEP DATA-012 | Real Overture August artifact preserved

**Source:** [Overture Maps attribution](https://docs.overturemaps.org/attribution/) and [Places](https://docs.overturemaps.org/guides/places/).

Two real *source datasets* from identical Beşiktaş and Karaköy sampling rectangles:

| Release | Schema | Source records | GitHub capture |
|---|---|---:|---|
| 2026-08-19.0 | Places v1.18 | 4,650 | Actions #38121005943, captured 2026-10-11 |
| 2026-09-23.1 | Places v2 | 4,803 | Actions #38096227796, captured 2026-10-10 |

The exact historic August Actions ZIP is permanently included at `data/real/overture_istanbul_2026-08-19.0/original_actions_artifact.zip`. The previous artifact expires 2026-10-18, but the Git-tracked research copy remains available. Original ZIP hash: `cb9ee86c128b4839a00722e1b192f460691c0f33e358f0b0b9ae458ea403ef05`. The ZIP holds four minimal source/metadata files and no individual human field-review results. The original global raw Parquet is not preserved or independently signed.

## Repeat the measured change offline

```bash
cd labs/core
python scripts/replay_pinned_august.py
python -m unittest tests.test_overture_durable_original -v
```

The replay should produce **4,581 retained IDs, 222 newly listed, 69 no longer listed, 198 changed name/address/geometry/etc. records, 3,337 confidence-only revisions**. These are SOURCE record changes, not independently observed changes to shops or opening hours. August was acquired *later in clock time* than September; publication order differs from collection order. `categories`/`taxonomy` cannot be blindly treated as semantically equivalent.

### Why preserve the ZIP instead of recomputing a snapshot?

The original Action ZIP, its exact internal SHA-256 values, and the original preflight report remain unchanged. `kepcore/overture_archive_artifact.py` independently verifies all four and compares the source records to the immutable September baseline. GitHub CI includes a standard-library-only replay step and never re-downloads the expiring artifact.

### Next research

Separate SCI-003 random verification from targeted DATA-011 source drift triage. Only independent dated human inspection can establish real business presence and any error rate. Added/removed listing IDs, supplier confidence, and coarse geographic sampling windows are not real-world truth.
