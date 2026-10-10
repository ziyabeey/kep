# ADR-0008 · Pinned Overture Places pilot, not live discovery

**Date:** 2026-10-11  
**Status:** Research-only implementation; field dataset acquisition still pending

## Why

SCI-001–003 tested belief, source provenance, time-based calibration and review sampling on small cached records or explicitly synthetic worlds. To evaluate city inventory quality, KEP needs a licensed, *real* geographic reference pool without pretending it supplies real-time events. Overture Places is a suitable test source, not a live restaurant review or open-now truth source.

## Decision

1. Start with two **approximate geographic sample cells** near central Beşiktaş and Karaköy. These are not legal district boundaries; use actual administrative polygon boundaries before district-specific coverage claims.
2. Pin the full Overture release `2026-09-23.1` and schema v2, using `taxonomy.primary` and `basic_category`. **Do not read deprecated `categories`**. The normalizer rejects old-schema input instead of silently losing its classifications.
3. A separate manual workflow downloads GeoJSON with `overturemaps download --bbox ... --type place`, requires STAC `latest` to agree before AND after acquisition, and freezes raw input SHA-256 values, minimal output SHA-256, the client version and provenance. If STAC moves, stop and review a new release under a new PR. Do not silently roll forward to latest.
4. Offline CI never reads Overture's remote dataset or spends API/browser tokens. It exercises malformed geometry, invalid IDs, wrong/unknown category, missing data, out-of-cell coordinates, release changes, duplicate IDs, and local replay with **synthetic fixtures**.
5. Only keep place ID, name, taxonomy, coordinates, selected business address data, Overture confidence, operating status and per-source license/provenance. Strip emails, phones, social media, websites, reviews and arbitrary text.
6. `operating_status: open` is NOT "open now". `confidence` is NOT independent verification. Unknown hours/prices/events, undetermined administrative district and human label status remain explicitly null/false.
7. Same exact Overture feature IDs are deduplicated; conflicting same-ID rows **abort**. Nearby same-named POIs are flagged as *possible duplicates* for human review, never merged automatically.
8. Sampling of the frozen pilot inventory uses the same *stratified SRS allocation* principle as SCI-003, storing strata, inclusion probabilities, frozen population hash and a private-seed hash. POI review tasks are **not** event-claim labels; SCI-003 event `ReviewedClaim` risk rates cannot be asserted from them.
9. No auto publication, business write, push notification, model API key, or user-facing availability claim is enabled by this PR.

## Licensing

Overture Places theme includes CDLA Permissive 2.0, Apache 2.0, and CC0 upstream components. Keep exact release, contributor/license attribution and any NOTICE obligations; do not collapse all sources to a blanket CC0/ODbL assumption. Overture Places does *not* ingest OpenStreetMap as a theme, but joining separately with OSM may change downstream obligations.

- https://docs.overturemaps.org/guides/places/
- https://docs.overturemaps.org/attribution/
- https://docs.overturemaps.org/getting-data/overturemaps-py/
- https://docs.overturemaps.org/blog/2026/09/23/release-notes/

## Scientific acceptance criteria

- [x] Data extraction and schema normalization are implemented and tested with synthetic fixtures.
- [x] Immutable local file/hash check and conditional release pin implemented.
- [x] Deterministic quality statistics, human-review-only possible duplicates, and stratified audit sampling implemented.
- [x] Manual bounded GitHub workflow provided; no background scraping enabled.
- [ ] **Real Overture Istanbul acquisition and release-stamped manifest executed and inspected**.
- [ ] Check city coverage against independently sourced reference data (not just Overture's own categories or confidence).
- [ ] District accuracy using independently verified administrative polygons and human field reviews.
- [ ] Measure duplicate precision/recall with independent labels, calibrated confidence and cross-release drift.

## Failure and rollback

Stop without publication on missing data, changed STAC release, oversized response, incompatible schema, conflicting feature IDs, or unverifiable sample. Revert this research-only PR to remove the additional adapter and workflow. No production DB migration exists.
