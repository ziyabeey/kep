# ADR-0024: prioritize real blinded field quality over further source-I/O optimization

Date: 2026-10-11. Research status: awaiting independent human review. Related: Issue #13, Issue #22, KEP-FIELD-001.

## Context

KEP-DATA-013 through -017 established reproducible Istanbul Places release differences, guarded GERS observations, patch-repeat identification and Parquet cost limits. Despite 785 passing unit tests, real business existence and physical change prediction remain unmeasured. Further metadata optimization alone cannot establish empirical quality.

A 60-POI blind review and third-review intake already exists in DATA-003/004/005 but has zero real A/B ballots. Duplicating the sampler or implementing another uncertain upstream download would not move us toward actual field performance.

## Decision

1. Operate a NEW, clearly distinguishable 60-record secret-seeded stratified draw over the unchanged 4,803-record September Places source frame. Freeze the exact sample-plan SHA-256, private seed commitment and per-case fixed baseline decisions BEFORE anyone reviews a case. Preserve the earlier anonymous 60-sample design unchanged; never assert the new draw is identical.
2. Human A and B receive separate blind XLSX files, both validated by the existing strict DATA-004 OOXML loader. They never receive the private seed, selection probabilities, supplier confidence, prelocked naive/KEP decisions or each other's votes. The private workbooks, seed, frozen plan and evidence stay OFF GitHub.
3. Frozen baseline: naive asserts physical existence for all 60 source-listed places; current KEP research gate abstains on all 60 because no independent evidence or consumer rights exists. This comparison measures claim-coverage discipline, **not** model predictive superiority. All human-ground-truth-derived error fractions stay null until complete, independent, timely A/B labels satisfy the existing design-based estimator.
4. Reuse DATA-004's strict workbook ingestion and weighted interval and DATA-005's third-human conflict route. Do not silently turn `unknown`, no internet search results, missing reviewer evidence, source confidence, `added` or `removed` into real business opening/closure labels.
5. Add a light standard-library-only offline `field_pilot` readout and audit-progress CLI, synthetic regression tests and a pinned real source cohort commitment, but no external API, new sampler engine, model fitting, production, publication, reviewer file uploads or broad re-design.
6. Retain the pre-review conservative 95% half-width **0.517502** for the six-stratum 60-record frame and explain it is insufficient for a tight prevalence estimate. Require a separately designed, sufficiently sized holdout for future predictive KEP-versus-baseline effectiveness.

## Actual current observation

- Source: Overture Places `2026-09-23.1`, 4,803 genuine **source records**, sampled in two small Istanbul research boxes.
- New independent cohort size: 60. Frozen at `2026-10-11T17:27:29.232163+00:00` with secret seed. Only the public commitments are stored in `reports/KEP_FIELD_001_PREREGISTRATION.json`.
- Human existence labels actually collected: **0**. Source error rate, KEP predictive accuracy and business openings/closures: **null**. Public study baseline naive assertions 60 and KEP automatic assertions 0, without presenting this as a measured accuracy win.
- Original strict importer accepted **both real yet completely blank 60-row workbooks**, confirming A=0, B=0, 60 missing, and no rate.
- The private coordinator artifact and separate reviewer sheets are shared only as private conversation deliverables, NOT copied to the public GitHub repository.

## Rollback

Remove only new field-pilot module/CLI/tests, public aggregate commitments, docs and offline CI smoke step. Do not touch pinned August/September Places archives, previous GERS results, previous human-intake modules or future private real review files. No consumer, database, API or Web Push migration to reverse.

Protocol: `labs/core/docs/REAL_FIELD_PILOT_001.md`.
