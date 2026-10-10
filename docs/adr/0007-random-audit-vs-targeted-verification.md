# ADR-0007: Separate targeted verification and randomized reliability audit

**Status:** Accepted as **research-only** architecture; **not** accepted as production risk policy.  
**Date:** 2026-10-11  
**Context:** KEP-SCI-001, KEP-SCI-002/002B, Issue #9.

## Thesis
Prioritize human review for the most uncertain, urgent or important claims. This catches defects efficiently and makes KEP safer at decision time.

## Antithesis
A selected pool of suspicious claims is not a representative sample. Using its raw error fraction to estimate the correctness of every tracked event can invert the conclusions of the entire calibration system. Different reviewer IDs and a SHA-256 snapshot alone cannot establish true source correctness.

## Synthesis and decision
Maintain two **separate queues and denominators**:

- Targeted queue for incident response/active evidence acquisition (NO population error claim).
- Prespecified, private-seeded stratified random audit on an enumerated frozen frame. Include every stratum, log known inclusion probabilities and exact population SHA; no audit postselection once labels are inspected.

Estimate weighted source-field error **only when all sampled items have complete, independently adjudicated labels by an explicit cutoff**. Otherwise mark the population estimate unavailable. Provide conservative finite-frame sampling bands, no claim of future guarantees. Enforce research rights and actual local snapshot bytes, never bypass approved source registry. New module cannot publish event content, issue push, approve rights, or change source trust scores in production.

## Rejected alternatives

- Train source trust exclusively on suspected failures: selection bias.
- Treat missing adjudications as correct or remove them silently: nonresponse bias.
- Use arbitrary model confidence as sampling probability: not a random audit.
- Pick sampling thresholds after observing held-out outcomes: test leakage.
- Use a sophisticated propensity model before we have population-wide exposure and sample-selection logging: unidentifiable.

## Evaluation and rollback

- SCI-003's synthetic 1,000-claim benchmark demonstrates selection bias and the behavior of our design, not real quality.
- Offline unit tests on Python 3.11/3.13 enforce provenance, plan replay, no cross-origin mixing, frozen frame, no sampling if any group is uncovered, and no estimate with missing labels.
- Source licensing, missing event coverage, proper randomization, real reviewer independence, and prospective user benefit remain operational experiments.
- Entire module is additive and can be rolled back by reverting the PR; it does not modify consumer data paths.
