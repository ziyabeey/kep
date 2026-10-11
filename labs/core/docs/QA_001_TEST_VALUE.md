# KEP-QA-001: Measure test usefulness before writing more tests

Date: 2026-10-11. Experiment is software QA on fictional KEP Core inputs, NOT a statistical sample of real failures.

## Why this replaces test-count milestones

879 green tests meant the existing authored rules pass. It did not tell us whether a particular false source claim, future label or costly sensor regression would be detected, nor whether an extra test would improve a decision. We therefore designed a deliberately small mutation experiment before adding ANY new regression test.

## Original preregistration and fixed trial

- Source snapshot: main d65cb9da2c5232a2848cae5b09ce6e6d5a9942bf.
- Frozen manifest: benchmarks/test_value_protocol.json. Twelve explicit source mutations, with rationale and ordinal priority weights chosen before detection outcomes.
- Two comparisons: 12 named high-priority sentinel tests versus 52 existing targeted tests from CORE-001/002/003.
- All mutations are applied to a throwaway local copy of the three modules and minimal synthetic fixtures. Original source files are SHA-checked before and after. Both groups must pass clean controls. Invalid or missing mutations fail the audit rather than count as catches.
- These injected faults are authored counterfactuals, not observed bug frequencies or a representative defect distribution. A killed mutation means one of the selected tests rejected this particular code change, not that KEP is correct in the world.

## What actually happened

| Measured outcome | 12 sentinels | Full focused suite |
| --- | ---: | ---: |
| Before additional test (52 focused tests) | 10/12 faults caught | 11/12 |
| After ONE targeted test (53 focused tests) | 10/12 | **12/12** |

First experiment: https://github.com/ziyabeey/kep/actions/runs/38174495768 .
Second identical fault set, after targeted test: https://github.com/ziyabeey/kep/actions/runs/38174675518 .
Both were independently run under Python 3.11 and 3.13 with matching semantic scores. Original and remediation ZIP digests are stored in reports/KEP_QA_001_TEST_VALUE.json. Runtime varies by host; selected 12 were NOT reliably faster than the larger suite, and trimming tests solely by number would have lost coverage.

### Two gaps, two different responses

1. M10_SYNDICATED_TRAINING: the 12-test sentinel missed double-counting contradictory same-root training observations. The EXISTING full suite already detected it through test_conflicting_same_observation_is_not_training_data. This requires better test SELECTION for a small smoke suite, **not** another test duplicating the same contract.
2. M11_WRONG_SPECIFICITY_BOUND: even the entire 52-test focused suite missed substituting the true-positive sensitivity bound for specificity. This could let a sensor that endorses all nonexistent venues pass a risk filter. A SINGLE new functional test now checks a 40-positive/40-negative synthetic audit and proves that conservative CORE-003 refuses the zero-specificity candidate. Re-running the SAME 12 faults killed this formerly surviving mutation in both Python versions.

**Important:** 12/12 after remediation is a fixed-set regression result, not independent generalization. A new held-out fault set would be needed to claim performance on unseen faults.

## Admission gate for every next KEP test or benchmark

Every new test request must answer these questions BEFORE writing test cases:

1. Which actionable KEP decision or hard prohibition does it protect? Does failure produce a wrong action, permission bypass, unwanted cost, avoidable abstention, or future-data leakage?
2. What is the smallest plausible wrong behavior to inject as a control, and is it ALREADY caught by existing focused tests? If yes, reuse rather than duplicate.
3. How much consequence does that failure have? Engineering severity can prioritize experiments but is not a calibrated incident probability.
4. What changes if the test detects the failure? Stop rule: no demonstrated incremental regression protection or no decision consequence -> do not add it.
5. What is its real runtime and maintenance cost? Measure repeatably; test count alone cannot substitute for speed or value.
6. For a NEW decision strategy benchmark, freeze the simulator, policies, baseline, independent holdout and primary metric BEFORE results. Report missed true decisions, false assertions, check costs and abstention. A synthetic win never proves real-world KEP advantage.

## Prioritize next CORE experiments by a falsifiable question, not the next version number

| Candidate | Why it matters | Predeclared failure and comparator |
| --- | --- | --- |
| Shared upstream rumor | CORE-003 correlated-failure regime produced the same false assertions in all methods | New synthetic shared-lineage detection versus existing CORE-003, plus no-check control; require fewer wrong assertions without unacceptable loss of correct decisions |
| Audit feedback outage | CORE-003 conservative utility dropped from 0.586 to 0.367 versus fixed VOI under its synthetic outage | Same-time, separate HOLDOUT of outage/recency strategies; jointly compare false assertions, true cases missed and utility |
| More blind unit tests on known rights rule | Already covered by existing targeted tests and killed relevant mutations | **Do not prioritize** unless a new distinct rights failure survives a recorded mutation |

These are candidate hypotheses, not claims that the new strategies will beat the baseline. Do not tune thresholds against earlier frozen test worlds and call their improvements independent.

## Reproduce and control resource cost

From labs/core:

    python scripts/audit_test_value.py --protocol
    python -m unittest tests.test_adaptive_trust -v
    python scripts/audit_test_value.py --output YOUR_NEW_LOCAL_QA_REPORT.json

Full mutation audit is ON-DEMAND, not part of every CI job. It runs three focused suites only in an isolated Python temporary workspace with socket access denied. Previously captured CI scores are preserved in the checked-in report. The temporary push-triggered mutation workbench is removed before merge. Ordinary Python 3.11/3.13 CI retains all functional regression tests without adding repeated mutation-suite cost.

## Limits and rollback

Selected source mutations can be easy to catch and do not estimate real error rates. The new test was tailored to a revealed gap, so the improved score is a regression fix, not scientific proof on new scenarios. No source data were downloaded, no production API, consumer publication, human labels, push messages, new sensor or model was run.

Rollback: remove only the optional QA mutation audit script, frozen protocol, one new adaptive-trust test, this report, ADR and small README note. Existing CORE modules and all historical files stay unchanged.
