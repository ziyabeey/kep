# KEP-DATA-007 | August 2026 Overture historical research

**Status:** Offline contract implemented, **real August download not yet performed**. The 4,803 September records are real Overture source records; the August fixture used in unit tests is invented. No physical business statuses have been independently checked.

## Why August matters now

Overture's published maximum retention period is 60 days (two releases). `2026-08-19.0` is approximately 53 days old on 11 October 2026; its S3 Parquet objects may expire around **18 October 2026**. Its listing in a current STAC catalog is **not evidence that the underlying Parquet files remain downloadable**. [Release policy](https://docs.overturemaps.org/release-calendar/).

Older schema: **v1.18.0**. September `2026-09-23.1`: **v2.0.0**. August contains deprecated `categories` alongside optionally present `taxonomy` and `basic_category`. Older categories must not be copied into the new taxonomy field without an independently reviewed mapping. The September release removed the old categories field. See [v1.18 Places schema](https://docs.overturemaps.org/schema/v1.18.0/reference/places/place/) and [Overture Places taxonomy](https://docs.overturemaps.org/guides/places/).

## Manual GitHub capture

Open **Actions → Overture August 2026 preservation (manual research)**, choose `main`, click **Run workflow**, fill:

- `research_confirmation`: `RESEARCH_ONLY`
- `release`: `2026-08-19.0`

The job needs public S3/extension network access. It uses `duckdb==1.4.1` with `spatial` and `httpfs`. Hard-coded historical path; it does **not** ask the Overture CLI for latest. Both geographic bbox windows match September. If data is no longer hosted, or SQL is unsupported, the run must fail and publish no successful-data artifact. No credentials, permission bypass or private scraping.

On success download the **7-day** GitHub artifact (`places_minimal.json`, `manifest.json`) to controlled research storage. The `manifest.json` includes `normalized_sha256`, `stac_catalog_sha256`, `acquisition.observed_at`, `source_files` and an explicit note that upstream authenticity/business existence is unverified. The source files are minimal derived GeoJSON extracts, not original Parquet objects. Do not publish them as up-to-date business recommendations or permanently commit old data without a separate retention review.

## Offline smoke, no network

```bash
cd labs/core
python -m unittest tests.test_overture_august -v
python scripts/overture_august_legacy.py
python scripts/compare_overture_august.py --help
```

After a *real* manual capture, inspect the artifact and separately review its digests before comparison:

```bash
python scripts/compare_overture_august.py \
  --august-dir .local/overture-august-extracted \
  --august-sha256 <REVIEWED_NORMALIZED_SHA256> \
  --manifest-sha256 <REVIEWED_MANIFEST_SHA256> \
  --stac-sha256 <REVIEWED_CATALOG_SHA256> \
  --observed-at <MANIFEST_OBSERVED_AT>
```

Run comparison August → September, *not* the inverse. The output distinguishes: retained UUIDs, source-listed-only appearances/disappearances, address/geometry field revisions, category migration unknowns, confidence-only changes and possible identity churn requiring human review.

### Interpretation boundaries

- 4,803 September records is a *source-coverage* count for two research rectangles, not verified business existence.
- August and September are different source schemas. Even where both have taxonomy fields, actual hierarchy semantics can change. The report explicitly blocks declaring category drift comparable.
- STAC-listed releases are not archived data. Hashes establish byte agreement *only*, unless compared against independently authenticated artifacts.
- An ID removed from Overture may represent dataset coverage, merge, filtering or deduplication, **not a physical closure**.
- Official GERS changelog and independently labeled field evidence will be needed for real-world interpretations.
- Do not assume case studies or 60-person labels can establish accuracy for all of Istanbul.
