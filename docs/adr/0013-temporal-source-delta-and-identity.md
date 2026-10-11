# ADR-0013 · Source-release delta is not real-world business change

**Status:** Proposed, subject to CI and PR review  
**Date:** 2026-10-11  
**Owner:** KEP-DATA-006

## Context

KEP has a SHA-256-pinned research copy of **4,803 genuine Overture Places records** from the September 2026 release (`2026-09-23.1`) in two small Istanbul research rectangles. It is **one source observation**, not a history of city changes. No physical business-existence, closure, operating-hours, or event labels have been collected. The next Overture release is *planned* for 2026-10-21 but is not currently an observed input.

Official Overture [GERS stability guidance](https://docs.overturemaps.org/gers/stability/) notes that registered place identifiers are intended to remain stable, not guaranteed to do so. A replaced ID may indicate matcher churn, source change, migration or an actual identity change. [Official changelog semantics](https://docs.overturemaps.org/gers/changelog/) define `added`, `removed`, `data_changed`, `unchanged` as **data-release changes**; the source says `removed` does **not** mean a real-world closure. Official change detection excludes `sources` and `confidence` from comparable properties; KEP reports those separately.

## Decision

Create a **read-only two-snapshot change engine** under `labs/core/kepcore/overture_delta.py`:

1. **Immutable-ish input envelope:** recompute each validated snapshot's canonical population SHA-256 just before comparison. The existing 4,803-record September snapshot is loaded only via its strict archive verification. An operator-supplied later bundle must match a separately supplied release and SHA, same cell bounds, compatible schema, no display rights and no live/open-now fields. SHA equality does **not** authenticate S3, reviewers, or a physical business.
2. **Keyed source changes:** count retained/added/absent record IDs; separately count property/geometry revisions, changes in confidence, provenance updates, and known↔unknown field transitions. Validate release time order and v2 schema; fail on unreviewed schema/region changes.
3. **ID churn is not an auto-merge:** a disappeared ID and added ID with identical normalized name and category within 45m creates an explicit **human review hint**, never an automatic identity link or closure/opening.
4. **Never turn record edits into world events:** No source disappearance→business closure, new listing→new opening, geometry edit→physical move, `operating_status`→open now, or Overture `confidence`→calibrated ground truth.
5. **No false longitudinal claims:** offline test uses 4,803 **real September records plus a plainly flagged synthetic future overlay**. Counts from that comparison are engineering-test outcomes. Zero true October Overture source observations exist in the experiment.
6. **Guarded output:** bounded detail and ID-churn review lists must disclose truncation, never silently pass incomplete review as no anomalies.

## Alternative approaches

- **Treat removed IDs as closed:** rejected, high risk of incorrect notifications.
- **Unconditionally match similar records:** rejected, conflates chains, colocated businesses, and GERS churn.
- **Use Overture official changelog only:** useful corroborating input, but its definition intentionally excludes confidence/source changes KEP also needs to audit. We can compare both after obtaining *two* real release observations.
- **Fetch August + September immediately and compare:** August 2026 uses schema v1.18 versus September v2.0; requires a separately reviewed migration and a time-bounded historical retrieval before old releases expire. No such historical acquisition is represented by this PR.

## Acceptance / rollback

`python -m unittest discover -s tests -v`, `python -m benchmarks.overture_delta_eval`, and `python scripts/overture_release_delta.py` must run offline in Python 3.11/3.13 GitHub CI. `main` is changed only by merged PR after successful checks. Revert PR to remove module; no database migration, Web Push, scheduled jobs, live browser, or production code changed.

## Next experiment

After Overture issues a later release, create a **separate manual-only acquisition** with exact reviewed release, SHA checks and matching cell bounds. If its schema differs, develop and test explicit mapping before any comparison. Then label a selected subset of altered POIs with independent reviewers, compare first-party changelog IDs vs KEP diffs, measure the rate of ID churn and source revision without claiming actual physical opening/closure.
