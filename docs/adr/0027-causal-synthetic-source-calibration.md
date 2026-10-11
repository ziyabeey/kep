# ADR-0027: Adapt synthetic source reliability with independent, causally available labels

Date: 2026-10-11. Status: proposed, merge only with green Python 3.11/3.13 and frozen synthetic results. Related PR #38 and KEP-CORE-003.

## Context

CORE-002's immutable synthetic study demonstrated that **more checking can worsen outcomes** when fixed error-rate assumptions overstate the quality of a degraded source. Rather than searching for more real datasets, the user explicitly wants to finish the KEP decision kernel using fictional signals until proprietary data is available. Existing source calibration and one-step utility modules are research-only; none has real physical-business accuracy data.

## Decision

1. Model only independent, uniformly sampled, **fictional historical adjudications**, each with a source observation time and a later time when the outcome is known. Do not accept current test-case truth, policy-selected review outcomes, missing provenance or time-travel labels. Keep per-publisher/per-entity deduplication and reject contradictory copies.
2. Learn **sensitivity and specificity separately**, conditioned on the independently audited fictional true-positive/true-negative classes, using bounded Beta smoothing and Wilson lower bounds. Do not report these as real-world calibrated probabilities.
3. Only historical labels already reviewed by the as-of timestamp may influence a query. Use a predeclared 72-hour recent window, at least 12 of each truth class and a 0.62 conservative lower-bound threshold. Missing or poor evidence withholds the new check. The posterior-mean and fixed-assumption policies remain comparison controls.
4. Route through the unchanged Core hard policy and the existing CORE-002 budget/deadline/one-root-to-two-root check planner, NEVER automatically fetch, call a model or authorize publishing. All outcomes remain LAB-only; physical business openings and closures remain unknown.
5. Preregister 6 chronological stress regimes x 160 synthetic test trials, 5 predeclared policies, and an independent background audit stream with feedback latency. All policies face the same cases and possible sensor answers. Hold test truth and prospective replies in an evaluation wrapper that is NOT passed to the policy. Include drift, delayed labels, missing labels and correlated errors that the model may fail to detect.
6. Preserve negative outcomes. A conservative source confidence gate can harm coverage; a marginally calibrated source can still participate in correlated misinformation. Report check costs separately from the unmodeled labor required for independent audits.
7. Keep original real archives, customer/field-review data, and all older research modules untouched. Require full offline Python 3.11/3.13 unit and locked benchmark replay to merge.

## Rollback

Remove only CORE-003's optional source-calibration modules, synthetic tests/benchmark/protocol, offline CI replay and documentation. No consumer, production, real-source or database migrations. See labs/core/docs/CORE_003_TEMPORAL_TRUST.md.
