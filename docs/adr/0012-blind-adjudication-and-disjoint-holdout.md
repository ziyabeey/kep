# ADR-0012 · Blinded third review and a disjoint new sampling frame

**Date:** 2026-10-11  
**Status:** Implemented in offline research code (not a completed field study)  
**Owner:** KEP LAB / KEP-DATA-005, Issue #18

## Problem

KEP-DATA-004 intentionally stops the 60-place audit when A and B contradict. A naive majority vote or silently replacing B's vote with C would hide a contested label and distort the audit trail. Meanwhile the current 60-place pilot has a preregistered Hoeffding-bound half-width of **0.517502**, so a narrowly stated prevalence rate needs a separately designed larger sample.

## Decision

1. Preserve the original A and B .xlsx files and review evidence **outside the repository**. An adjudication case contains only the sampled Overture ID, immutable source descriptors, and a SHA-256 commitment to the precise A/B ballots. It does **not disclose their decisions** to C.
2. Only a complete **binary disagreement** on *physical existence* may be adjudicated by a third distinct human pseudonym with a specific HTTPS evidence reference, timestamp no earlier than the A/B votes, and explanation. A missing ballot, `unknown` vote or post-as-of review is not transformed into a binary result.
3. The third review contains its **own explicit outcome**, not a majority inferred from the pair. A/B ballots are never rewritten and the case hash rejects subsequent modifications. Identity strings and evidence links are not proof that independent human beings performed those reviews.
4. Record a separate population-size proposal for a **disjoint next holdout**, excluding the pilot's 60 Overture IDs. Its estimand is the remaining 4,743 records, **not** the entire original 4,803-frame prevalence unless a new combined design is formally specified. This PR produces only a design/effort forecast; **no new sample has been drawn**.
5. Keep the dimensions separate: `physical_existence` is **not** `currently_operating`, `open_now`, or `coordinate_correct`. The new code never changes consumer publication privileges or verifies any venue as existing.

## Conservative numerical design

Six source-area × Overture-confidence strata. Bonferroni + Hoeffding union-bound; within-stratum simple random sampling, full completed high-quality human labels, nominal confidence 95%, no design or threshold selected using future audit results. Approximate sample needs for the disjoint **4,743** remaining records: 401 for ±0.20, 713 for ±0.15, 1,604 for ±0.10. The baseline pilot's existing 60 draw is not counted as new holdout. Planning at 12 min per reviewer and two reviews per new POI means 1,604 cases would consume **641.6 reviewer-hours**, before travel, evidence collection overhead, quality assurance or third reviews. These are *assumed planning inputs* and are not measured productivity.

A smaller/cheaper but less conservative estimator may be considered in a separate preregistered simulation with explicit assumptions. Do not silently reduce budget by inspecting the pilot outcomes.

## Verification cost and safety invariants

The originally implemented third-review tests repeatedly decoded the 4,803-place
archive. The audited code now verifies the signed-off local manifest, normalized
SHA-256, research-only source rights and full feature schema **once per audit
invocation**, and reuses only that validated in-memory frame to reconstruct the
same seeded stratified selection. It does **not** cache previously validated
files across invocations. Regression tests require exact plan parity against
the independently verified standalone sampler and verify that a subsequently
corrupted compressed archive still fails closed. The 30 dedicated unit tests
run in about 11 seconds locally rather than 25 seconds for the older 28-test
prototype. These times are diagnostics, not an SLA.

## Rollback

Delete the new `overture_adjudication.py` and its CLI, docs/tests/CI smoke line. No production DB writes, source-rights changes, user-visible publication or model API calls. Pilot A/B workbooks and seed remain unchanged.
