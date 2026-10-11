# KEP-CORE-004A | NO-GO: a failed test is a useful product decision

**Research date:** 2026-10-12 (Istanbul). **Status: NO-GO.** The proposed bounded 48-hour historical-audit grace policy was NOT admitted to KEP Core. The full, preregistered synthetic holdout ran successfully, but the candidate did not improve decision behavior.

## Why test this, not blindly implement CORE-004?

The [CORE-003 frozen research report](../docs/CORE_003_TEMPORAL_TRUST.md) identified a larger avoidable simulated-utility loss from **audit-outage over-abstention** (57 true opportunities missed under conservative policy versus 17 under fixed VOI) than the three false assertions shared by competing methods in its correlated-rumor scenario. That prioritization was made before this experiment.

The protocol in [outage_value_protocol.json](../benchmarks/outage_value_protocol.json) was committed at `8edf6cc2469b5d7fff3ad142c341affca4b06c4c` **BEFORE policy implementation**. Six new synthetic regimes × 180 cases, a distinct seed, four fixed methods and explicit acceptance thresholds were frozen. No live city records, labels, source crawls, model calls or production actions were involved.

### Proposed (but rejected) optional research policy

When CORE-003 abstained *only* for insufficient recent independent audit labels, consider slightly older, fully adjudicated synthetic historical audits for up to 48 hours, and only when each relevant source root had at least 12 known true and 12 known false audit cases and both nominal Wilson lower rates were ≥0.62. Never override an actual uncertain-origin warning, failed rights/price/consent gate, source conflict, source independence requirement, budget or deadline.

This sounds conservative, but it must **change a useful decision**, not merely add code that satisfies unit tests. It was run only in a temporary PR branch, never integrated with the consumer or deployed core.

## Actual first new holdout

Original independent GitHub Actions run [#38180120019](https://github.com/ziyabeey/kep/actions/runs/38180120019), **success** on Python 3.11 and 3.13. Full decoded synthetic JSON reports match and have canonical SHA-256:

`f00c4d2da46f35ad63f1da671171db3b69dfb67abf85ad1318d8207e1b337a46`.

The independently downloaded GitHub artifact ZIP digests are retained in [the anonymous negative report](../reports/KEP_CORE_004A_NO_GO.json). These hashes prove exact replay and source integrity within the GitHub experiment, **not** actual-world correctness.

| Wholly synthetic regime | Fixed VOI utility | Existing conservative utility | Candidate grace utility |
| --- | ---: | ---: | ---: |
| Outage, otherwise stable | 0.517972 | 0.344167 | **0.344167** |
| Outage plus abrupt quality degradation | 0.135667 | 0.183694 | 0.183694 |
| Outage plus gradual quality degradation | 0.276083 | 0.261250 | 0.261250 |
| Healthy independent audits | 0.434833 | 0.434833 | 0.434833 |
| Delayed review results | 0.424806 | 0.372639 | 0.372639 |
| Shared incorrect rumor | 0.306028 | 0.306028 | 0.306028 |

Units are **invented simulator utility** (correct assertion +1, false assertion −4, subtract normalized check cost). They are not accuracy in Istanbul, true revenue, performance of a deployed model or a real-world risk rate.

**Primary preregistered acceptance criterion failed:** A utility gain of at least **+0.025 per case over the existing conservative policy in outage_stable** was required; observed difference was **0.000**. The proposed policy issued the **same number of checks** and missed the **same 53 true opportunities**. Other safety criteria passed, but cannot rescue the missing positive value. The acceptance decision is **NO-GO**.

In the new shared-rumor stress, all three checking policies also generated eight false synthetic assertions each. This result is about the NEW holdout and must not be confused with the prior CORE-003 holdout's three errors in 160 cases.

## Why it failed and what to do instead

The 48-hour recency guard plus the two-class audit sufficiency and risk rules were too restrictive to create any additional useful check in the frozen scenarios. **This is a hypothesis drawn from the stated rule and observed outcomes, not a proof of universal impossibility.** We did **not** relax the thresholds after inspecting these scores or repeatedly reuse the same holdout to manufacture a win.

The next sensible *new* experiment is to first test **what decision information is observable when a source-audit pipeline fails**, including separate costs for delayed truth and potential source deterioration. Explicitly preregister uncertainty, stopping rules, false-positive loss and opportunity cost. A softer time window might be investigated only with a genuinely new seed and holdout. Source lineage remains a separate safety risk, not something to fix by inventing unavailable upstream-correlation data.

## Disposition and resource discipline

- **No new policy or algorithm merged.**
- Experimental `outage_grace.py`, first-holdout generator and 13 targeted temporary tests plus the temporary Actions workbench were removed from the final PR tree before merge.
- Preserved only this negative report, the genuinely predeclared protocol, and a concise architectural rejection record.
- Normal 880-test CORE CI remains unchanged. No repeated expensive holdout run is added to every commit.
- The historical first-run source tree (for reproduction/audit only) is retained at [experimental commit e802d04](https://github.com/ziyabeey/kep/commit/e802d04bf7a33476e5af8e96e18d893f6894bc09). This is **not** a shipping module.

**Rule from QA-001 applied:** A passing test suite, an aesthetically plausible model, or a long list of features is not sufficient. Require *incremental decision value* under a fixed falsification test. If no value is demonstrated, reject it.

## Rollback

Remove only this report, original preregistered protocol and rejection note. No code, source archives, proprietary data, live integrations, notification flows or experimental model inference exist to roll back.
