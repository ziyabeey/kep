# KEP-DATA-001 · Two-cell Istanbul Places pilot

**Status:** Local contract tested; no fresh Overture Istanbul snapshot has been retrieved in this development environment. All committed smoke tests use conspicuously **synthetic** GeoJSON features. Never report those five example businesses as existing places.

## Why this is not a city recommendation dataset yet

September 2026 Overture schema 2 removed `categories`. Use `taxonomy.primary` and `basic_category`. GERS-membership is not proved by a UUID, the `confidence` score is not proof that a shop exists, and `operating_status='open'` is not proof of current hours. A rectangular crop is not a Beşiktaş or Karaköy district boundary. Historic ratings from the separate UCI dataset must never be joined by name alone.

## Source and license

- Overture v2 Places schema: https://docs.overturemaps.org/guides/places/
- Exact pinned release: `2026-09-23.1`, https://docs.overturemaps.org/blog/2026/09/23/release-notes/
- STAC: https://stac.overturemaps.org/catalog.json
- Contributor and licensing table: https://docs.overturemaps.org/attribution/
- Downloader: https://docs.overturemaps.org/getting-data/overturemaps-py/

The contributor license families include CDLA Permissive 2.0, Apache 2.0 and CC0. The selected source metadata is retained; unknown per-record licenses remain unknown. `consumer_display_approved=false` is a KEP product safety gate, **not** a claim that these open datasets are legally barred from being displayed.

## Sampling cells, W/S/E/N (longitude, latitude)

- `besiktas_center`: [29.0020, 41.0400, 29.0100, 41.0455]
- `karakoy_center`: [28.9700, 41.0200, 28.9810, 41.0275]

These are **research sampling windows**, not administrative polygons. They are deliberately small to control data transfer and manual-audit cost.

## Run locally without network, safely

```bash
cd labs/core
python -m benchmarks.overture_places_eval
python scripts/overture_istanbul.py  # Prints the pinned plan; zero network requests
python -m unittest tests.test_overture_places -v
```

For real acquisition on a network-enabled workstation, opt in explicitly:

```bash
python -m pip install overturemaps
python scripts/overture_istanbul.py --fetch --output .local/overture-pilot-2026-09-23.1
```

The CLI validates the Overture STAC `latest` release before and after download. **If the newest STAC release is no longer the pinned 2026-09-23.1, the run stops**, rather than pulling a different release under the same label. Propose a new pinned version via PR. The script never requires a token, and no production data is written.

GitHub UI alternative: **Actions → Overture Istanbul Places Research (manual) → Run workflow**, from the default branch, enter `RESEARCH_ONLY` and confirm the exact pinned release. No scheduled or PR-triggered data download exists. The action emits an artifact retained for seven days containing only sanitized `places_minimal.json` and `manifest.json`; the raw download stays ephemeral on the runner.

For local files supplied from an independently controlled download, pass both `--besiktas-geojson` and `--karakoy-geojson` along with a **new** `--output`. This does not establish authentic upstream provenance. The `manifest.json` clearly records `operator_supplied_local_files` rather than claiming a trusted network download.

## Research results

`places_minimal.json`: deterministic, strictly limited normalized attributes; no contacts, active events, current hours, consumer prices or user IDs. `manifest.json`: raw checksums, normalized checksum, exact release, license links, invalid/missing field counts, possible duplicates and zero validated outcomes. Potential duplicate is a *review suggestion*, not a merged entity. Errors from conflicting same-ID versions or unexpected release halt the process.

For unbiased place auditing, create an off-repo seed file, pass `--audit-seed-file` and retain the seed privately. The resulting `audit_plan_unlabeled.json` stores inclusion probabilities, strata and hash commitments. **No error rate is estimated until actual reviewers label the selected places.**

## Next scientific work

1. Run the manual Overture job, freeze and inspect its checksum/manifest.
2. Confirm the source-specific attribution metadata and inspect out-of-box, null-name, null-taxonomy, duplicate-review rates.
3. Independently validate 30–60 randomly selected POIs for position, name and current operation, with documented evidence. Distinguish spatial mismatch from missing ground truth.
4. Only then run confidence-vs-truth calibration and compare fixed script vs research Scout with the same raw snapshots and cost budget.

This pilot **does not resolve** Issue #3 (live event feed) or Issue #9 (real-world event-claim calibration).
