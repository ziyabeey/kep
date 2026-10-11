# ADR-0015: Historical S3 object preflight before Overture backfill

**Decision:** Accepted for research (2026-10-11)
**Scope:** KEP-DATA-008, follows issue #22 and ADR-0014.

## Motivation

A release listed by STAC may no longer have all public Parquet bytes. A
manual historical Overture DuckDB query should fail early if even one object
under the exact old release prefix cannot be listed and HEAD-read. On
2026-10-11, a bounded unauthenticated ListObjectsV2 request returned a real
Parquet key under the historical `2026-08-19.0` Places prefix. No August
Istanbul extract was downloaded by this metadata inspection.

## Decision

Before any historical remote SQL, issue one small, bounded anonymous S3
ListObjectsV2 GET against the *fixed* pinned prefix and then HEAD the
returned *single* Parquet object. Require status 200 and matching key,
content-length and ETag. Do not follow redirects or accept arbitrary hosts,
prefixes, filenames, releases or run-time SQL. Record a separate research
receipt linked by SHA-256 to the normalized bundle and its manifest.

This is an availability check, not a proof of complete historic coverage.
Only the actual post-query bundle + manifest, reviewed with the retained
Sept 2026 bundle, could support **source-record** change estimates.
No business closure/opening, consumer publication, model-training ground
truth, or exact physical existence is inferred.

## Counterexamples & rollback

- STAC exists, S3 prefix empty: reject before costly remote query.
- S3 list contains key, anonymous HEAD 403: reject.
- HEAD size/ETag mismatch: reject, don't trust inconsistent metadata.
- All checks pass, later regional query fails: report failure; preflight
  does NOT promote the release to acquired.
- `latest` is September: never fall back automatically.
- To roll back: revert new probe module, CLI preflight lines, workflow receipt
  step and documentation; historical archive remains unchanged.

## Safeguards

No secrets in workflow, manual dispatch remains required, offline CI uses
only a mocked transport, S3 key check is exact, and uploaded receipt contains
public object metadata only. S3 ETag is not a reliable SHA-256.
