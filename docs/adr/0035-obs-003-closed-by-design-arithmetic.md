# ADR-0035: Close KEP-OBS-003 from pre-data design arithmetic; abandon the disagreement selector on this generator family

Date 2026-10-18. Status: **accepted, CLOSED_BY_DESIGN_ARITHMETIC**. No pilot or holdout was run. Product rollout NOT approved.

## Context

ADR-0031 closed OBS-002 as a procedural NO-GO, and the owner chose to reopen the question as a new study, KEP-OBS-003. A fresh designer drafted the preregistration (`labs/core/benchmarks/obs_003_protocol.json`, draft r2). Three independent critics, covering mechanism reach, forking paths and decision value, raised 15 blocking issues, and all were resolved in the draft. Before the freeze, three independent agents computed exact closed-form arithmetic from the protocol's own constants. No RNG, generator, planner or evaluator was run.

## Finding

The arithmetic assumes the selector works exactly as the constants imply. Under that assumption:

- The expected gain of the unchanged OBS-001 selector over audit-age-only in the mid-outage drift window is **+0.0196 utility per case**. The preregistered materiality bar is 0.025.
- Early alarms (steps ~160–177) abstain from deep checks that still have positive expected value. That cancels part of the later benefit, and the check's expected value only turns negative near step 177.
- One 90-case window cannot show value at this confidence for **any** switch. An oracle that abstains exactly when checking turns negative reaches G2a power of only about 0.05.
- P(GO) for the single-timeline design is at most about 0.04. A 113-replicate design would reach about 0.27, limited by the expected effect being below the bar, at roughly 113× the runtime.

## Decision

The owner (Ziya) chose to close OBS-003 from this arithmetic, by decision card on 2026-10-18 at 11:17 UTC. The verbatim choice is recorded in the protocol's `owner_power_confirmation_required_before_freeze.recorded_choice`. The other options offered were 113 replicate timelines, or running the single-timeline design as drafted.

- Abandon the unlabelled-disagreement selector as a candidate on this synthetic generator family. Do not open a module or design issue for it.
- Retire seeds 202610180002 (pilot) and 202610181000 (holdout) unused.
- No thresholds, costs or seeds were tuned. The draft protocol is kept as the design record.

This is a statement about an authored simulator's constants. It is not evidence about real sources. It also does not cover different signals, such as lineage or upstream-dependence detection, which no disagreement-only rule can provide (ADR-0030).

## Learning ledger (KEP-GATE-001 item 8)

| Observed | Decision | Cost | Open |
| --- | --- | --- | --- |
| Pre-data power analysis showed the expected value was below the bar | Stop before writing any code | One design workflow; no simulation | Whether any observable signal can detect a shared upstream origin |

## Rollback

Delete this ADR and the OBS-003 draft protocol. Nothing else changed.
