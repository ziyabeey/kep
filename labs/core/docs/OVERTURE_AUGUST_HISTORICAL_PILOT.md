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

## DATA-008: historical S3 preflight (11 October 2026)

The upstream STAC child *lists* `2026-08-19.0` and an unauthenticated S3
ListObjectsV2 query under the exact historical Places prefix returned one
`part-*.zstd.parquet` key. **This is not the August Istanbul data extract.**
No real August region has been retained in this study yet.

Before the expensive historical DuckDB query, `--fetch` now checks that the
public S3 prefix lists exactly one object when `max-keys=1`, then performs a
HEAD request for that **exact old-release Parquet object**. The GET list and HEAD
ETag/content length must agree. No body is downloaded in the probe. If the
object is inaccessible, the job fails before the DuckDB work. There is no
redirect, host substitution, credential upload, or fallback to `latest`.

Explicit connectivity probe only, not the full download:

```bash
cd labs/core
python scripts/overture_august_legacy.py --probe
```

The manually triggered GitHub workflow still performs the full extract only
after successful preflight and uploads three research files:
`places_minimal.json`, `manifest.json`, and `historical_public_preflight.json`.
The receipt hashes the two data files and records **one** public object's
reported HEAD/listing metadata. It does *not* authenticate every S3 part,
establish original raw-file SHA-256, prove a region was fully extracted,
verify any physical business, or authorize consumer display. In particular,
S3 ETags (including multipart ETags) are **not** content SHA-256 hashes.

Offline CI mocks GET/HEAD. It does not spend network bandwidth or retrieve
any new historical data. If public retention expires or an object cannot
be accessed, the project must report `HISTORICAL_DATA_UNAVAILABLE` and use
a later **genuinely acquired** release rather than filling the gap synthetically.


## DATA-009: historical backfill order and provisional two-release result

**Corrected comparison contract:** a release's publication date and its local
acquisition timestamp are different clocks. The 19 August source can be obtained
on 11 October **after** the September source was obtained, yet the correct
comparison remains August → September. The comparator allows reversed
*acquisition* timestamps only when the exact Aug 19 operator-research snapshot is
compared to the pinned Sep 23 frozen archive. Reversed release dates, all other
origins, and default snapshot comparisons still fail closed.

**Completeness:** both original bounded pilot cells must contain at least one
valid extracted August source row. A missing, empty or entirely rejected cell
stops the manual capture rather than creating thousands of false "removed IDs".
The resulting manifest contains per-cell rows-read and valid-row counts. These
are counts within fixed rectangles, not borough administrative districts.

**New manual result:** on a *successful* August workflow, the same job now
performs an offline comparison with the existing 4,803 September records.
The seven-day artifact includes a fourth file, \`source_delta_provisional.json\`,
alongside \`places_minimal.json\`, \`manifest.json\`, and
\`historical_public_preflight.json\`. The report records release and separate
download timestamps, category migration uncertainty, by-cell coverage, source
record churn and human-review hints.

**Evidence gate:** the immediate comparison checks internally supplied manifest
and receipt hashes, not independently authenticated S3 source bytes.
\`evidence_status=PROVISIONAL_INTERNAL_HASH_CHECK_NOT_INDEPENDENT_SOURCE_VERIFICATION\`
is compulsory. Zero independently verified business closures/openings are
inferred. No historical POI data is automatically committed or published.

**Capture remains user-triggered:** GitHub Actions → Overture August 2026
preservation (manual research) → Run workflow on \`main\`, with exact
\`research_confirmation=RESEARCH_ONLY\` and \`release=2026-08-19.0\`.
No regular CI job makes external requests. Run soon if the historical Parquet
objects remain available; failure, empty cells or schema mismatch must be
reported instead of estimated or patched with synthetic rows. After download,
separately review report digests, Overture attribution/retention permissions,
GERS changelog and independent field labels before any scientific interpretation
or long-term storage.
