# KEP-DATA-006 · Temporal source-delta lab

**Important:** The reference data are 4,803 *real Overture September 2026 records*. The second snapshot in the default demonstration is **synthetically edited**. The lab has **zero actual observations from a later Overture release**. This is a software experiment, not a city business-opening/closure study.

## Why build it?

A user asks KEP: *"Is this cafe still here?"* A listing absent in the next map-data update is **not sufficient to answer "It closed."** A provider can remove a source, replace an identity, alter regional coverage, or improve matching. Similarly, a coordinate revision does not mean the business physically moved. See Overture's [GERS ID stability](https://docs.overturemaps.org/gers/stability/) and [release changelog](https://docs.overturemaps.org/gers/changelog/) descriptions.

| Source observation | KEP research disposition | Prohibited inference |
|---|---|---|
| Old ID missing from new release | `no_longer_listed_ids` | Business permanently closed |
| New ID appears | `newly_listed_ids` | New business just opened |
| Same ID, coordinate changes | `geometry` revision, measured metres | Physical relocation |
| Same ID, `operating_status` changes | Data property revision | Currently open or closed right now |
| Overture `confidence` changes | Separate `confidence_only_revised_ids` | A calibrated truth probability |
| Old/new IDs share exact normalized name/category and <45m | Human-review identity candidate | Automatic merge or verified successor |
| Address becomes `null` | `address_became_unknown` | Address was physically removed |

Source `source_provenance` array order has no semantic meaning; it is compared as a set-like sorted list. Distinct providers/data rights are kept and separate changes are reported. Conflicts and possible ID churn remain pending human review.

## Offline experiment commands

```bash
cd labs/core
python -m unittest tests.test_overture_delta -v
python -m benchmarks.overture_delta_eval
python scripts/overture_release_delta.py
```

Default artificial fixture on the 4,803 historical reference records:

| Artificial edit | Expected observation |
|---|---:|
| Stable UUIDs retained | 4,801 |
| Added IDs in fake later fixture | 2 |
| IDs absent from fake later fixture | 2 |
| Stable IDs with field or coordinate revision | 5 |
| Stable IDs with confidence-only revision | 1 |
| Potential ID-reassignment human-review hints | 1 |
| Verified business openings / closures | **0 / 0** |

No live network, browser, API token, notification, consumer display or private reviewer file is used. Input hashes preserve research reproducibility. The report's `synthetic_second_release=true` and `real_world_business_changes_estimated=false` are non-optional interpretation flags.

## How a later real research extract will be compared

First obtain a **separately reviewed** later Overture release and build exactly the same *minimal source records* (`places_minimal.json` + `manifest.json`). Run the approved manual research workflow, verify the release's STAC signature/hash and raw provenance independently, document attribution and save original outputs in an access-controlled archive. Do not silently use `latest` as a historical release.

The following command is an interface example, **not a command currently ready to run with actual October records**:

```bash
python scripts/overture_release_delta.py \
  --candidate-dir .local/next_overture_pinned_bundle \
  --candidate-release 2026-10-21.0 \
  --candidate-sha256 <INDEPENDENTLY_REVIEWED_NORMALIZED_SHA256> \
  --candidate-observed-at 2026-10-22T10:00:00+03:00
```

Here `2026-10-21.0` is **the proposed release ID on Overture's schedule**, not an acquired snapshot. A real acquisition dated in the future is blocked by the CLI. If the actual release or schema differs from the planned one, register a new exact release and review the schema migration. The loader accepts only the two existing small Istanbul rectangles, v2 field contract, pinned SHA, source metadata, and `consumer_display_approved=false`. A supplied matching SHA is merely internal consistency: the source of that SHA must be independently verified outside this generic comparison.

## Scientific questions to test with two REAL releases

- How often did an ID disappear only to have a matching replacement nearby? What fraction is identity churn versus source coverage?
- How many coordinates, names, addresses, classifications and provider attributions change, and how fast?
- Does the [Overture official changelog](https://docs.overturemaps.org/gers/changelog/) agree with locally replayed changes? Its `sources`/`confidence` exclusions must be handled separately.
- Of a **pre-registered, blinded random subset of changed places**, how often does independent evidence confirm a physical move, closure or new opening?
- At a fixed verification budget, does selective follow-up yield fewer false closures than a naive "removed means closed" baseline?

Until there are two real releases **and** independent human evidence, KEP has no empirical Istanbul business-churn rate or field-validated superiority over competing apps.

## Privacy, licences and rollback

No direct personal phone, reviews, social accounts or usernames are collected. Source-specific licensing and attribution follow `DATA_LICENSES.md`. The comparator uses the existing minimized research schema and does not grant consumer-display rights. Remove the DATA-006 modules and CI smoke to roll back; the original source archive and human-review files remain untouched.
