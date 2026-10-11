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


## Observed initial benchmark and status

First full fixed-protocol run: 960 wholly synthetic evaluation cases (6 x 160), 5 predeclared strategies, no real-world data or human audits. Both Python 3.11 and 3.13 decoded CI reports identical; full canonical SHA-256 c587b34c1e4801847c8bd8b71dc1b05c9ead5ee9cb28eeacab1dea1cd9c89e48.

Adaptive posterior mean beats fixed VOI in abrupt degradation (fictional utility/case 0.320250 vs 0.233875); conservative lower bound beats fixed VOI under gradual degradation (0.153312 vs 0.135531). Under feedback outage, however, lower bound loses strongly (0.367219 vs 0.585594), despite both making zero false assertions, because it misses many true opportunities. Under correlated publisher errors all three remain identical at 0.453844 and still make three false assertions each. These findings are **conditional on an authored simulator**, not a calibrated real-world risk bound. No optimization threshold was chosen after viewing the results; future adjustments require a new locked trial design.
