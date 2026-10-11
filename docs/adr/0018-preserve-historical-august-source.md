# ADR-0018: Save the exact August 2026 Overture research artifact beyond retention

**Status:** Accepted for research only.  **Date:** 2026-10-11.

## Decision

Preserve the **original 430,240-byte, four-member GitHub Actions ZIP** at `labs/core/data/real/overture_istanbul_2026-08-19.0/original_actions_artifact.zip`, rather than merely saving its hash. GitHub Actions #38121005943 generated the public Overture August 2026 research extraction; artifact #11695042455 expires on 2026-10-18. The original ZIP SHA-256 `cb9ee86c128b4839a00722e1b192f460691c0f33e358f0b0b9ae458ea403ef05` and each member SHA-256 are already pinned in `kepcore/overture_archive_artifact.py`.

The ZIP contains only **minimal, normalized open Overture source records and research metadata**, not full S3 Parquet or user/reviewer data. A single-use GitHub workflow fetched the exact artifact using GitHub's token, checked SHA-256 and all 4 members, committed only the ZIP to this research branch, and removed its own workflow file. No recurring data download or write permission is left in `main`.

## Testable invariants

- 4,650 Overture August source records, 4,803 September source records; exact two-release replay of 4,581 shared IDs, 222 newly listed IDs, 69 no-longer-listed IDs, 198 factual-property/geometry changes and 3,337 confidence-only changes.
- Offline CI works without GitHub artifact availability, authentication tokens, browsers or network.
- Filename, file bytes, original ZIP SHA-256 and original per-file digests are frozen. A corrupt or substituted ZIP fails closed.
- Source provenance, record chronology and divergent category schemas are respected. August was *retrieved* after September; the *release* order is August then September.
- `consumer_publish=false`; none of the source-record changes imply verified openings, closures, operating hours or physical moves.

## Rights and scope

Overture Maps attribution and source licenses: https://docs.overturemaps.org/attribution/ . This research uses bounded, public POI data previously extracted with attribution. Retain source-provider/license fields; consumer display approval is a separate KEP product control. No original global Parquet, private audit seed, human reviewer vote or social/phone data is committed.

## Rollback

Revert the preserved research ZIP, the durable offline replay script, regression tests and CI smoke. This does not affect consumer services or the original 4,803-record September archive.
