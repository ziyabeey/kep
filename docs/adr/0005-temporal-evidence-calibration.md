# ADR-0005 — Temporal source reliability calibration (KEP-SCI-002)

**Status:** research-only, partial implementation of Issue #9  
**Date:** 2026-10-11  
**Dependencies:** ADR-0002 source rights; ADR-0004 active evidence research; Issue #3 real, permitted Istanbul source

## Thesis, antithesis, synthesis

- **Thesis:** infer source trust from its reputation or the model's verbal confidence. Simple, but not a calibrated probability.
- **Antithesis:** assume all sources are equally reliable or count syndicated copies as independent corroboration. This hides source-level and field-level differences.
- **Synthesis:** collect an immutable timestamped **claim snapshot** and an independently reviewed **field-level outcome**. Fit publisher-root / field correctness using only earlier outcomes, select a risk/coverage policy on a later calibration period and evaluate once on an untouched test period. Publish remains **disabled** regardless of score.

## Implemented in this PR

1. `labs/core/kepcore/calibration.py`: typed review schema, immutable observation hash, approved `research_ingest` scope, timezone-aware chronology and one independent claim per publisher root per entity/field/time.
2. Strict global chronological train / calibration / test windows. Reviews adjudicated *after* their window are not allowed to leak backwards. The same entity+field is purged if it crosses windows.
3. Empirical source/field correctness estimates with shrinkage to field and global history; unsupported publisher groups fall back to pooled evidence, never magic “95% confidence.”
4. Global, field, and root+field baselines each select **their own threshold** using their own calibration-period data. A Wilson upper bound screens candidate thresholds; no threshold guarantees future error under drift.
5. Held-out Brier, ECE/calibration bins, risk–coverage, resolved/unknown/superseded, field slices and explicit source-drift diagnostics.
6. Deterministic **synthetic** benchmark showing what can break when one publisher group's error rate deteriorates. CI has zero model/API calls and no live scraping.

## Exclusions: not yet field-validated

- **No independently adjudicated İstanbul source history** exists for the claimed training/calibration/test horizon. There is no measured real-world reliability curve, source accuracy, timestamp accuracy or local event outcome.
- This is NOT conformal risk control or an independent statistical guarantee for all future periods. Wilson intervals assume independent Bernoulli trials; clustered publisher/event observations and distribution shift violate that simplifying assumption.
- No calibrated output is allowed to set `verified`, override factual/core gates, send Web Push, authorize a domain, or initiate unreviewed external calls.
- Human label must be about the captured claim **at the original decision time**, not what is true months later. `superseded` is not equivalent to `incorrect`.
- A publisher-root correctly mentioning an event is not independent proof of an occurrence, ticket availability, quality, or physical attendance.

## Gate to close Issue #9

- Obtain rights-reviewed İstanbul observations with multiple dated snapshots and independent corroboration where feasible.
- Have reviewers explicitly adjudicate venue/date/price/cancelled claim **as-of snapshot**, with evidence URL and snapshot SHA256. For critical disputed fields, second independent reviewer and reconciliation required.
- Collect enough independently labeled outcomes in train, calibration and test windows; document item/time/venue coverage and conflicts. Only after this may the operator consider a separate, gated production-readiness ADR.
- Compare against fixed-source and no-extra-research baselines with equal API budget, record field-wise false claims and missed events; any drift alarm is descriptive and should stop claims of a risk guarantee.

## Rollback

Remove the research module, docs and offline CI test. Existing Core, Radar, Scout and SCI-001 routes remain unchanged. No migration or production state change.

## Sources for protocol design

- https://pmc.ncbi.nlm.nih.gov/articles/PMC11092361/ (REFORMS: leakage, clustered observations)
- https://arxiv.org/abs/2507.16289 (sequential recommenders; global temporal split)
- https://docs.aws.amazon.com/prescriptive-guidance/latest/ml-operations-planning/splits-leakage.html
