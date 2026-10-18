# KEP-OBS-002 | A pilot stop rule fired: procedural NO-GO, holdout never opened

**Research decision (2026-10-18): NO_GO_NOT_DISCRIMINATING (procedural).** The frozen OBS-002 holdout was **cancelled and never run**. Its seed `202610180615` is retired and must not be reused. This follows KEP-GATE-001 ([#39](https://github.com/ziyabeey/kep/issues/39)) items 5 and 6 and ADR-0030.

**This is not evidence for or against the OBS-001 disagreement signal in degraded worlds.** The pilot could not reach the part of the timeline where the signal could matter.

## What was preregistered

The protocol [obs_002_protocol.json](../benchmarks/obs_002_protocol.json) was committed in `9dad81a` before any generator or evaluator code existed. Its SHA-256 is `e8445240…23fe`, and the evaluator refused to run if the file changed.

- A new synthetic generator, not CORE-002/003 case generation. It covers six regimes of 240 hourly cases. The mechanisms are raw-vote loss and delay during a review outage, deep_root syndicated with origin, drift that starts mid-outage, a shared rumor on current cases, and a telemetry charge of 0.004 utility on every pair-telemetry read.
- The OBS-001 selector rule, unchanged: origin/deep_root pair, 12 h lookback, at least 18 entities, cutoff 0.35, review age above 8 h.
- Comparators: never, conservative CORE-003, fixed VOI CORE-002 and audit-age-only.
- Ten hard gates. The primary gate (G1–G3) required the candidate to beat **both** fixed VOI and conservative in the mid-outage drift regime.
- A 60-case pilot on a separate seed. Its stop rule: if the candidate makes the same proposal as BOTH controls on every pilot case, cancel the holdout and record NO-GO.

## What happened

1. The evaluator (`62cf01f`) compared proposals by action, as the reused CORE-002/003 executors record them. The pilot returned **NO_GO_NOT_DISCRIMINATING**: on all 360 pilot cases the candidate made the same proposal as conservative and as audit-age-only.
2. The implementer then changed the comparison to (action, probe), as deviation **D1** in `b8a794e`, and confirmed that the change flipped the verdict before committing it. Under D1, 5 cases in the syndicated regime differ from conservative, where the probe was deep instead of balanced. **The candidate still equals audit-age-only on all 360 cases**, so the telemetry signal changed no decision.
3. An independent auditor, a separate worker from the designer, found **no leakage**. It found that the reused Core modules were byte-identical to `f8ec7cf` and that the pilot JSON was identical on Python 3.11 and 3.13. It also found that the original 7 targeted tests missed subtler variants of the preregistered faults, so 13 audit tests were added (`2a18772`, 900/900 locally, CI [run 39104469538](https://github.com/ziyabeey/kep/actions/runs/39104469538) green). It flagged D1 as decisive and post-pilot.
4. An independent methodology panel considered three options: strict stop, amending the protocol, and accepting D1. All three lenses rejected accepting D1. An adversarial refuter then overturned the panel's amendment majority, for three reasons:
   - #39's acceptance line says the large benchmark is *cancelled* when the strategies do not discriminate.
   - Amending a fixed experiment after the fact is forbidden.
   - Anything a protocol amendment could add can be had more cleanly from a new preregistration with a new seed.

D1 is therefore recorded as a **post-pilot interpretive deviation, not a bug fix**. The action-only verdict stands.

## Why the pilot could not discriminate (derivable from the frozen constants alone)

| Timeline point | Step |
| --- | ---: |
| Review outage starts | 24 |
| Pilot ends | 60 |
| Conservative's audit history runs out (12 per class, 72 h window) | ≈86 |
| Drift onset | 150 |
| G9 alarm-recall window opens | 180 |

Over steps 0–59 there is no drift, and conservative still has READY audits. The signal therefore read pair telemetry 28 times per outage regime, raised no alarm, and was identical to audit-age-only. That matches OBS-001's finding that the signal adds nothing in stable outages. In the raw-loss regime, 28 of 28 telemetry reads had too few pairs (mean 1.5 against the 18 needed), so the fallback to conservative did work as designed.

## Lessons for any future preregistration

- A discriminability pilot must be small and **aimed at the mechanism**, for example cases sampled after the audit-history and drift onsets. A short prefix of the holdout timeline does not do that.
- Define "proposal" explicitly, and use the same definition for discriminability and for any identity gate such as G7.
- Test a signal's discriminability against its **nearest control** (here audit-age-only), not against "both controls". Otherwise a candidate that only reproduces the simpler control can pass.
- A stop rule that fires is final for that study. Revisiting the question means a new study with a new seed, labelled as reopening a procedural NO-GO.

## Learning ledger (KEP-GATE-001 item 8)

| Observed result | Engineering decision | Research time | Still uncertain |
| --- | --- | --- | --- |
| Stop rule fired. The signal changed 0 of 360 pilot decisions vs audit-age-only. | No selector, module, test suite or CI job admitted. The evaluator stays only in branch history (`2a18772`). | One session: prereg, evaluator, independent audit, methodology panel. | Whether the signal adds value over audit-age-only under drift or syndication. Untested. |

## Engineering disposition

Following ADR-0028/0029/0030, the experimental evaluator `benchmarks/obs_002_eval.py` and its 20 targeted tests were removed from the final tree. They are preserved at `2a1877261020af62fce2be1a7511729842419e9a` (PR #46) for replay only. Main keeps this document, the protocol, the [aggregate report](../reports/KEP_OBS_002_NO_GO.json) and [ADR-0031](../../../docs/adr/0031-obs-002-procedural-no-go.md). Core CI is unchanged (880 tests at the time).

Real Istanbul source accuracy: UNKNOWN. Real human labels: ZERO. Source downloads: ZERO. Model calls: ZERO. Consumer publishing: DISABLED.

## Follow-up

The owner reopened the question as a new study, KEP-OBS-003, with new seeds. It was closed before its freeze by pre-data design arithmetic: even with the mechanism working as designed, the expected gain over audit-age-only stays below the 0.025 bar. See [ADR-0035](../../../docs/adr/0035-obs-003-closed-by-design-arithmetic.md).

## Rollback

Delete this document, the OBS-002 protocol, the report and ADR-0031. No Core code, archive or field file was changed.
