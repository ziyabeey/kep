# ADR-0032: Preregistered third Overture release comparison (KEP-DATA-018)

Date: 2026-10-18. Status: proposed; the capture itself waits for the Overture release planned for 2026-10-21. Related: Issue #22, DATA-010/011/013/015/016.

## Context

KEP has two real, pinned Overture Places releases for the same two sampling cells: 2026-08-19.0 (Places v1.18) and 2026-09-23.1 (v2.0). Their official GERS changelog cannot be reconciled directly, because STAC shows 2026-09-23.0 between them and the patch baseline is unattested (DATA-013/014/016). Overture's release calendar (read 2026-10-18) lists 2026-10-21.0 as the next release, schema version TBD, and keeps public releases for about 60 days.

A third release opens two questions two releases cannot answer: how often a record that left the source comes back, and whether local cell membership changes match the official regional changelog of a release whose STAC predecessor is our pinned September archive.

On 2026-10-11 the user paused new data collection. This ADR only prepares code; no source is read until the user triggers the manual workflow.

## Decision

1. Freeze the protocol before any third-release data exists: `labs/core/sources/overture_third_release.json`, SHA-256 pinned in `kepcore/overture_third_release.py`. Any later edit fails the offline tests.
2. Accept a release only when STAC latest equals it, its date is in 2026-10-14..2026-11-17, and it differs from both reference releases. Otherwise stop before reading data.
3. Compute six preregistered metrics (M1-M6). M1-M5 are three-release source-record trajectories inside the two cells. M6 compares local membership changes with official regional added/removed changelog rows, only when the STAC prev link is 2026-09-23.1 and every selected row group was read.
4. If the publisher schema is not v2.0.0, category fields are excluded from the second-hop comparison, including the per-ID revised/unchanged classification. When the release catalog carries `schema:version`, an operator input that contradicts it stops the comparison. August-to-September category changes never count.
5. If the third-release normalizer rejects any in-cell record (anything other than `outside_sampling_cell`), all metrics abstain: a dropped record would otherwise read as "no longer listed".
6. A STAC prev link is navigation evidence, not an attested changelog build baseline. M6 is reported with that label and as same-publisher evidence.
7. Acquisition is one manual `workflow_dispatch` workflow with fixed byte and request caps (16 MiB footers, 16 MiB / 128 requests event rows). Ordinary CI stays offline and runs a labelled synthetic dress rehearsal of the full compare path. The manual workflow was checked with actionlint 1.7.7; a failed Arrow pre-flight skips only the GERS step.
8. Outputs are aggregates and ID-set digests. No metric is a business opening, closure or accuracy rate. No consumer publication, Web Push, paid API, model call or human label.

## Consequences

The study can run within minutes of the release and its numbers cannot be tuned after the fact. The capture artifact lives 7 days, so a follow-up PR must pin it, as with August (ADR-0017/0018). If Overture ships an intermediate patch first, M6 abstains and M1-M5 still run. If the run happens after the November release becomes STAC latest, the capture stops; a historical S3 route like DATA-008 would be a separate study.

## Rollback

Revert the DATA-018 module, script, rehearsal, tests, protocol, workflow, the CI step, this ADR and the runbook. The two small compatible changes (`release` override in `scripts/overture_istanbul.py`, `releases` parameter in `validate_objects` and `decode_footer`) default to previous behaviour. No pinned archive, report or production system changes.

Details: `labs/core/docs/OVERTURE_THIRD_RELEASE.md`.
