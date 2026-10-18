# ADR-0031: Honour the OBS-002 pilot stop rule; record a procedural NO-GO

Date 2026-10-18. Status: **accepted NO-GO (procedural)**. Product rollout NOT approved.

## Context

ADR-0030 allowed exactly one further, independently designed synthetic test of the OBS-001 unlabelled-disagreement selector. KEP-OBS-002 was preregistered in commit `9dad81a` (protocol SHA-256 `e8445240…23fe`) before any code existed. It had a new generator, a new holdout seed, an unchanged selector and ten hard gates. A 60-case pilot was to cancel the holdout if the candidate's proposals matched both controls on every pilot case (KEP-GATE-001 / #39 item 5).

## Decision

The stop rule fired. On the evaluator as it stood at pilot time (`62cf01f`), the candidate matched conservative and audit-age-only on all 360 pilot cases. A post-pilot change of the comparison key, deviation D1 (`b8a794e`), would have reversed the verdict. An independent auditor and an independent methodology panel judged D1 to be a post-pilot interpretive deviation, not an allowed bug fix. Even under D1, the telemetry signal changed none of the 360 decisions versus audit-age-only.

Therefore:

- Record OBS-002 as **NO_GO_NOT_DISCRIMINATING**. The holdout (seed `202610180615`) is cancelled, was never run, and is retired.
- Do not amend OBS-002 or reuse its holdout. Revisiting the question requires a new, separately labelled preregistration with a new seed.
- Admit no selector, module, test suite or CI job. The audited evaluator and its 20 targeted tests are kept only at `2a18772` for replay.

This NO-GO is **procedural**. The pilot ended at step 60, before conservative loses its audit history (≈86), before drift onset (150) and before the alarm-recall window (180). It provides **no evidence about the signal in degraded or syndicated worlds**. It also does not contradict OBS-001's finding that the signal adds nothing over audit age in stable outages.

## Consequences

- Future discriminability pilots must target the mechanism, define "proposal", and test against the nearest control.
- A fired stop rule is final for its study.
- No real data, labels, model calls or publishing were involved. Core and its 880-test CI are unchanged.

Full record: `labs/core/docs/OBS_002_NO_GO.md`, `labs/core/reports/KEP_OBS_002_NO_GO.json`.

## Rollback

Delete this ADR, the OBS-002 protocol, report and document. Nothing else changed.
