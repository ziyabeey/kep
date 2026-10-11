# ADR-0014 · Overture August historical release, not implicit latest

**Date:** 2026-10-11  
**Status:** Proposed, research-only  
**Issue:** [KEP-DATA-007 #22](https://github.com/ziyabeey/kep/issues/22)

## Context

The current first *real source* snapshot is September `2026-09-23.1`, schema v2.0, for two small Istanbul sampling rectangles (4,803 normalized records). KEP's temporal comparator has been tested with an explicitly synthetic second snapshot. To make source-change measurements, an independently captured *second real source release* is required. The August `2026-08-19.0` release uses the **v1.18** Places schema and is near Overture's 60-day public availability limit. STAC release listing is not proof that the S3 objects still exist.

The ordinary Overture CLI defaults to the **latest** release. Calling that CLI without an exact historical release selection would risk relabeling September as August. The historical acquisition therefore reads a hard-coded path `s3://overturemaps-us-west-2/release/2026-08-19.0/theme=places/type=place/*.parquet` using an explicit, bounded DuckDB query and does not fall back to `latest`.

## Decision

- One manual-only workflow, no PR/scheduled data collection, no credentials, only public S3 data.
- Only the **same two frozen sampling rectangles** as September. No national city extrapolation.
- Minimal projection: Overture UUID, name, coordinate, taxonomy/basic category, historical categories used for **aggregate migration diagnostics only**, confidence, operating status, first address, limited source metadata. Do not ingest social/phone/email/reviews.
- **No invented category mapping.** Legacy `categories.primary` is *not* copied to new `taxonomy.primary`. Native August `taxonomy` / `basic_category` values are retained when present. Missing fields remain missing. Category drift between schemas is explicitly non-comparable until reviewed.
- Exact release, STAC hash, source-derived cell GeoJSON hashes, normalized artifact hash, manifest hash, observation time and provenance recorded. Source hashes of derived extracts are **not** original Parquet hashes; local SHA checks are not publisher authentication.
- `removed` ≠ closed business, `added` ≠ newly opened business, `geometry revised` ≠ physical move, `confidence` ≠ calibrated truth.
- Research artifacts are short-lived (7-day GitHub artifact); no automatic commit of historical data, respecting provenance, retention and data-removal concerns.
- Upload/replay must require independent expected normalized and manifest hashes; dataset accepted only if same exact source, sampling windows and schema contract.
- If August S3 files have expired, the job fails. **Do not synthesize a real release.** Use the next actually published version as a separate future experiment.

## Test and rollout

`cd labs/core && python -m unittest tests.test_overture_august -v`. Existing main CI also runs the complete suite under Python 3.11 and 3.13 without network or Anthropic access. The 31+ offline fixtures are explicitly synthetic; a real historical August data set is not claimed until the manual job actually returns it.

## Rollback

Delete the new manual workflow and August-specific lab files. The existing September 4,803-record archive, field-review sample and previous release-diff code remain unchanged.
