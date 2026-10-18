# ADR-0032: Preregistered third Overture release comparison (KEP-DATA-018)

Date: 2026-10-18. Status: proposed; the capture itself waits for the Overture release planned for 2026-10-21. Related: Issue #22, DATA-010/011/013/015/016.

## Context

KEP has two real, pinned Overture Places releases for the same two sampling cells: 2026-08-19.0 (Places v1.18) and 2026-09-23.1 (v2.0). Their official GERS changelog cannot be reconciled directly, because STAC shows 2026-09-23.0 between them and the patch baseline is unattested (DATA-013/014/016). Overture's release calendar (read 2026-10-18) lists 2026-10-21.0 as the next release, schema version TBD, and keeps public releases for about 60 days.

A third release opens two questions two releases cannot answer: how often a record that left the source comes back, and whether local cell membership changes match the official regional changelog of a release whose STAC predecessor is our pinned September archive.

On 2026-10-11 the user paused new data collection. This ADR only prepares code; no source is read until the user triggers the manual workflow.

## Decision

1. Freeze the protocol before any third-release data exists: `labs/core/sources/overture_third_release.json`, SHA-256 pinned in `kepcore/overture_third_release.py`. Any later edit fails the offline tests.
2. Accept a release only when STAC latest equals it, its date is in 2026-10-14..2026-11-17, and it differs from both reference releases. Otherwise stop before reading data.
3. Compute six preregistered metrics (M1-M6). M1-M5 are three-release source-record trajectories inside the two cells. M6 compares local membership changes with official regional added/removed changelog rows, only when the STAC prev link is 2026-09-23.1 and every selected row group was read. M6 always carries a status: a missing, failed or inconsistent GERS capture is an `ABSTAIN_*` status with its reason, never a silent null, and an abstaining M6 reports no local-versus-official cross counts.
4. If the publisher schema is not v2.0.0, category fields are excluded from the second-hop comparison, including the per-ID revised/unchanged classification. When the release catalog carries `schema:version`, an operator input that contradicts it stops the comparison. August-to-September category changes never count.
5. If the third-release normalizer rejects any in-cell record (anything other than `outside_sampling_cell`), all metrics abstain: a dropped record would otherwise read as "no longer listed".
6. A STAC prev link is navigation evidence, not an attested changelog build baseline. M6 is reported with that label and as same-publisher evidence.
7. Acquisition is one manual `workflow_dispatch` workflow with fixed byte and request caps (16 MiB footers, 16 MiB / 128 requests event rows). `load_protocol` fails if a protocol value differs from the constant that enforces it in shared code. Ordinary CI stays offline and runs a labelled synthetic dress rehearsal of the full compare path. The manual workflow was checked with actionlint 1.7.7; a failed Arrow pre-flight skips only the GERS step, and M6 then reports `ABSTAIN_GERS_CAPTURE_MISSING`.
8. Outputs are aggregates and ID-set digests. No metric is a business opening, closure or accuracy rate. No consumer publication, Web Push, paid API, model call or human label.
9. Every capture receipt records the protocol SHA-256 and the code commit (`GITHUB_SHA`) that captured it; the report adds the commit that ran `compare` (`null` outside GitHub Actions), and the manual workflow asserts the two commits are equal. `compare` rejects a capture made under another protocol version, so an offline re-run after a protocol edit cannot pass as the preregistered one, and an offline re-run with edited code shows up as `compare_code_commit: null`.
10. There is no GO/NO-GO gate and no primary metric (`decision_gate: NONE_DESCRIPTIVE_SOURCE_STUDY`). Like DATA-008 to DATA-017, this is a descriptive source study; no product or engineering decision depends on its numbers. A gate added after any third-release data exists would make a new study.

## Pre-data protocol revisions

All made on 2026-10-18, before the release existed, each re-pinning the protocol hash:

| Commit | Protocol SHA-256 | Why |
|---|---|---|
| 6fa5201 | `24cada00…b9f3` | First version, committed together with the code |
| 90c8f8c | `61c71df2…7b4d` | Pre-run review: category fields excluded from M3's per-ID classification on a schema change; STAC `schema:version` cross-check; abstain on in-cell normalizer rejections |
| 93d254c | `254e3876…f7e4` | Owner review: M4's field list moved into the protocol (`m4_factual_fields`) with a note on why M3 and M4 differ on `source_provenance`; the operator schema is recorded at capture and fixed for later offline runs; a missing, incomplete, inconsistent or invalid GERS capture makes only M6 abstain; `preregistration_note` added |
| this PR's last protocol commit | `759cb0bb…fe60` | Audit against the `kep-denetci` checklist: the window note no longer contradicts the window; the existing conflicting-rows abstain and the no-cross-counts rule are now listed; M5 rounds differences to 9 decimals so an exact 0.05 move never counts; capture provenance rule; explicit `decision_gate` |

The frozen version is `759cb0bbdd1447bbe39388033f593b190d28155a8877681fb57a7c21d69ffe60`. Branch commits may be squashed on merge, so this hash, which every receipt and report carries, is the durable anchor; the protocol commit on `main` is the merge of PR #44.

Code-only fixes in the same round, none of which changes a metric definition: the workflow always hands the GERS directory to `compare`; the workflow warns on every M6 abstain; the footer budget is built from the protocol; a receipt whose origin contradicts its manifest is rejected; malformed GERS files abstain instead of aborting the report; every row of a selected GERS row group has its bbox validated before the cell filter, so a NaN row stops the capture instead of vanishing. Tests now pin the M4 and M5 numerators, cover `taxonomy_primary`, wide changelog row groups, the runtime read caps, the window edges and `run_places` with STAC and the download stubbed.

## Process against CLAUDE.md

`CLAUDE.md` and the role files reached `main` while this PR was open (#43). Against its rules:

- **Protocol first (rule 1):** not met. Protocol and analysis code were committed together. Blindness rests on the release not existing yet; every report says so (`preregistration_note`).
- **GO/NO-GO gate (rule 1):** none, by design (decision 10).
- **Frozen protocols are not changed; the auditor rejects an implementer PR that edits the protocol:** the protocol was edited three times in this PR after `frozen_at`, each time together with code (table above). Every edit predates any third-release data and re-pins the hash, and the rule reached `main` after the first two edits. Whether that is acceptable is the lead's call, not this PR's.
- **Designer and auditor in different sessions:** the protocol and code were written in one session, and the audit above ran there too, as separate subagent calls with no design role. `CLAUDE.md` allows subagent calls for roles but says the designer and the auditor cannot be the same session, so an audit from a different session is still owed before merge.
- **Learning ledger (rule 7):** belongs to the follow-up PR that pins the October artifact, because there is no result yet.

## Consequences

The study can run within minutes of the release, and its analysis cannot be quietly tuned after the fact: every receipt and report carries the protocol hash and the code commit that produced it. The publisher schema is still an operator input, cross-checked only when the STAC catalog carries `schema:version`. If the workflow runs more than once, the follow-up PR pins every run's artifact and lists every run ID, not a chosen one. The capture artifact lives 7 days, so a follow-up PR must pin it, as with August (ADR-0017/0018). If Overture ships an intermediate patch first, M6 abstains and M1-M5 still run. If the run happens after the November release becomes STAC latest, the capture stops; a historical S3 route like DATA-008 would be a separate study.

## Rollback

Revert the DATA-018 module, script, rehearsal, tests, protocol, workflow, the CI step, this ADR and the runbook. The two small compatible changes (`release` override in `scripts/overture_istanbul.py`, `releases` parameter in `validate_objects` and `decode_footer`) default to previous behaviour. No pinned archive, report or production system changes.

Details: `labs/core/docs/OVERTURE_THIRD_RELEASE.md`.
