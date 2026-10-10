# ADR-0009 · Overture POI artifact integrity and existence survey

**Status:** Adopted for research-only lab; no production deployment.  
**Date:** 2026-10-11  
**Follow-up:** Issue #13 (real POI acquisition and field truth); Issue #9 remains a separate **event-claim** calibration project.

## Decision

The manual Overture workflow is the **only** remote data-acquisition path. It must run `verify_overture_pilot.py --require-live` after a bounded download and before uploading any artifacts. Regular pull-request CI must remain 100% offline; it evaluates synthetic data and deliberate corruption cases.

The verifier checks canonical byte representations, normalized file SHA-256, frozen population SHA-256, pinned release, two sampling cells, exact field allowlist, coordinates, row accounting, candidate duplicates, research-only flags, and source-attribution declarations. It checks **internal consistency**, not independent authenticity of downloaded upstream bytes: raw source files are not exported in the public artifact and a malicious or erroneous producer could manufacture consistent files and hash strings. Accordingly, it must report `upstream_acquisition_authenticated=false` and `real_world_place_existence_verified=false` even after an otherwise successful manual download.

For the eventual *existence* field test, use a second, frozen, randomized audit stratified by **sampling cell × Overture existence-score band**: missing; low ≤0.50; medium (0.50,0.80]; high >0.80. These are preregistered **sampling bins**, not thresholds for accepting or recommending a business. Each stratum has a nonzero inclusion probability. The private seed remains outside GitHub. A frozen selection cannot be altered after outcome review. Only complete, concordant outcomes from two separate human reviewer IDs enter a weighted prevalence estimate; a disagreement, unknown vote, missing record or late review means **no overall rate** is returned. Reviewer IDs and source URLs do not cryptographically prove independence or truth.

The estimator uses finite-population stratum weights, with a conservative per-stratum Hoeffding union bound. The interval is conditional on a correct and complete frame, a genuine uniform-without-replacement draw within strata and accurate human reviews. It does not cover release-to-release drift, unknown businesses not in Overture, reviewer error, or current opening hours. An Overture `confidence` value predicts relative existence likelihood; the upstream documentation explicitly says it is *not calibrated across providers*.

## Non-goals

- Running a paid model, publishing/sending push, changing source permissions or deploying an app.
- Automatically deciding two nearby POIs are the same, verifying commercial operation, live open-now or address correctness.
- Assuming the Overture release has been downloaded in this session; the verified real POI count remains zero until a successful source artifact and human review.
- Conflating manually gathered suspicious examples with statistically sampled cases.

## Experiment interpretation

`python -m benchmarks.overture_audit_eval` runs 200 **invented** records, 16 surveys per draw and 60 independent deterministic draws. It contrasts the naive sample fraction and the inclusion-probability weighted estimator with known artificial existence outcomes. These are diagnostic method tests, **not** Istanbul precision numbers.

The first viable real pilot must use the existing manual GitHub workflow, download `places_minimal.json` and `manifest.json`, check their local integrity, generate and archive a private-seed frozen plan, then collect two genuinely independent human judgments. Only afterward may a field estimate be calculated. Real source rights, attribution and collection timestamps remain attached to the artifact.

## Rollback

Revert this PR. The underlying `KEP-DATA-001` offline importer and its old `pilot_audit_plan` are unchanged, and no production state is modified. The next manual ingestion would simply lose the extra post-processing integrity check, which is why it is mandatory after adoption.
