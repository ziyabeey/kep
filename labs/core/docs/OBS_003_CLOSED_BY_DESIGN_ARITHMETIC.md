# KEP-OBS-003 | Closed before freeze by pre-data design arithmetic

**Decision (2026-10-18): CLOSED_BY_DESIGN_ARITHMETIC.** No generator, evaluator, test, pilot or holdout was ever written or run. Seeds `202610180002` and `202610181000` are retired unused. See [ADR-0035](../../../docs/adr/0035-obs-003-closed-by-design-arithmetic.md) and the [aggregate record](../reports/KEP_OBS_003_RESULT.json).

## Why there was an OBS-003

OBS-002 ended as a procedural NO-GO ([ADR-0031](../../../docs/adr/0031-obs-002-procedural-no-go.md)): its pilot could not reach the mechanism. The owner reopened the question as a new study with new seeds. Under KEP-GATE-001 ([#39](https://github.com/ziyabeey/kep/issues/39)) the question is whether the unchanged OBS-001 disagreement selector adds value over audit-age-only, and avoids mistakes compared with both fixed VOI and conservative, once the review pipeline is down and sources drift.

## How the protocol was designed

A designer who had not seen any OBS-002 pilot output wrote [obs_003_protocol.json](../benchmarks/obs_003_protocol.json). Three independent critics then reviewed it, each through one lens: whether the pilot reaches the mechanism, forking paths, and decision value. They raised 15 blocking issues, and all were resolved. A final checker verified the result.

Before the protocol could be frozen, three agents worked out the expected outcome from the protocol's own constants, using exact closed-form arithmetic. No simulation was run.

## What the arithmetic shows (synthetic constants only)

- The selector's expected gain over audit-age-only in the mid-outage drift window is **0.0196 utility per case**. The preregistered bar is **0.025**.
- Early alarms around steps 160–177 abstain from deep checks that still have positive expected value. This uses up part of the later benefit, because the check's expected utility only turns negative at about step 177.
- The chance of a GO was at most about 0.04 with one timeline, and about 0.27 with 113 replicate timelines (roughly 113 times the runtime).
- One reference policy was also checked. It knows the drift schedule and abstains exactly when the check turns negative (from step 178). Even that policy reaches only about 0.05 G2a power. This covers that one schedule, not every possible switch (correction C1).

The owner chose to close the study by decision card on 2026-10-18 at 11:17 UTC. The choice is recorded verbatim in the protocol.

## Corrections added during PR review

- **C1:** the oracle claim is limited to the one step schedule that was evaluated.
- **C2:** G2's per-case bootstrap treats the steps as exchangeable. In fact neighbouring steps are dependent, because they share up to 11 of the 12 lookback hours. The power figures for G2 are therefore approximate. The closure rests on the G1a expectation (0.0196 < 0.025), which does not depend on the inference method. That expectation is itself a closed-form approximation. Any future study must use independent replicates or a bootstrap that preserves the dependence (cluster or block).

## What this does and does not say

The arithmetic is about one authored simulator family. It does not measure real sources. It also does not cover other signals: in particular, detecting a shared upstream origin is still open, and no rule based only on disagreement can provide that (ADR-0030).

## Learning ledger

| Observed | Engineering decision | Cost | Still open |
| --- | --- | --- | --- |
| The expected value is below the bar even with the mechanism working as designed | No code was written; the selector is dropped for this generator family | One design workflow, no simulation | Observable lineage / shared-origin detection |

Real human labels: ZERO. Source downloads: ZERO. Model calls: ZERO. Consumer publishing: DISABLED.
