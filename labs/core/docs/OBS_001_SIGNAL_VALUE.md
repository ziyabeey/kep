# KEP-OBS-001 | Observable signals before another KEP decision module

**Research decision (2026-10-12): GO FOR A SECOND INDEPENDENT SYNTHETIC EXPERIMENT ONLY.** No new KEP Core module, no production permission, no source data hunt. This follows the failed CORE-004A policy and QA-001 test-value admission rules.

## Exact preregistration and first exercise

The protocol was committed BEFORE the feature extractor or simulator in commit 1876912a654e7aac8affe6c544687311b266de2c. The first complete code/execution snapshot is e25ce70c14a644a73fcd299e51e8e8b28a658578, whose *original* branch-commit source remains available for reproducibility; it is not shipping Core code.

- Six scenarios of **160 wholly synthetic cases each**, 960 total. New fixed seed 202610121015, separate from the exposed CORE-003/004A holdouts.
- Frozen comparisons: conservative CORE-003, fixed VOI CORE-002, completed-audit-age-only, and completed-audit-age plus unlabelled publisher-disagreement switch. All act on the same scenario, available source events and hidden prospective sensor results.
- Raw previous-publisher observations are projected to an ObservedVote with **no truth field**. Independent adjudication outputs may enter original CORE-003 source-learning only after the completion timestamp. Completed-audit telemetry exposes a timestamp, never the reviewer outcome.
- The hypothetical source-health signal is disagreement among publisher roots 'origin' and 'deep_root' across at least 18 previously observed unique synthetic background entities in the preceding 12 hours. A source-pair disagreement fraction over **0.35** marks a possible deterioration; last finished independent audit age over **8 hours** marks a feedback delay.
- Under old-enough feedback plus sufficiently low disagreement, propose the already existing fixed VOI method; otherwise use the existing conservative method. This is an **experimental policy selector**, never an executable source fetch or a consumer existence claim.
- Before results: minimum +0.025 simulated utility over conservative in stable outage, no worse than audit-age-only, no extra stable false assertions versus fixed VOI, drift regret each <=0.05 per case, zero extra correlated-rumor false assertions versus conservative, abrupt-alert recall >=0.5 and stable false-alert fraction <=0.25. All checks required.

First two-interpreter GitHub Actions run [#38203661808](https://github.com/ziyabeey/kep/actions/runs/38203661808) **passed**. Full decoded Python 3.11 and 3.13 JSON reports matched exactly, canonical SHA-256:

    3b5730287025f394f0f6a7453d833069e7c0aad38842f3c9e013f9efe1e2f27d

GitHub artifact ZIP SHA256 Python 3.11: 88c3661d3a86b62975196c7cce6b88f796ddb45f6e4b5cd15d5daf76509b048d; Python 3.13: 31d3ea027a4ef1a78f596bb53824e25aa21fc9564ef91b5e322b08662013353b.

## Actual first-run outcomes, synthetic utility units per case

| Scenario | Conservative | Fixed VOI | Audit age only | Unlabelled disagreement |
| --- | ---: | ---: | ---: | ---: |
| Stable quality, independent audit outage | 0.362188 | 0.519719 | 0.519719 | **0.519719** |
| Abrupt source deterioration + audit outage | 0.123906 | 0.105000 | 0.105000 | **0.128719** |
| Gradual deterioration + audit outage | 0.087844 | 0.045875 | 0.045875 | **0.087844** |
| Healthy audit pipeline | 0.477625 | 0.477625 | 0.477625 | 0.477625 |
| Delayed independent labels | 0.562031 | 0.566844 | 0.562031 | 0.562031 |
| Correlated false rumor across publishers | 0.333594 | 0.501469 | 0.501469 | 0.501469 |

The signal added NO extra utility over age-only during stable outages. Its value was in rejecting overly eager checking when source disagreement increased in **degraded** worlds: +0.023719 per case versus age-only in abrupt deterioration and +0.041969 in gradual deterioration. In stable outage, recovering fixed VOI decisions gained +0.157531 over conservative with the same number of false assertions (1); the paired conditional bootstrap range was [0.112562, 0.206594]. The small +0.004813 lift versus conservative in abrupt deterioration was **not a robust finding**: its synthetic conditional paired interval [-0.002156, 0.021406] includes zero.

At decision indices 85 onward, the alert flagged 68 of 75 cases in abrupt deterioration, all 75 in gradual deterioration and 0 of 75 in stable outage. The pair samples counted 39 distinct synthetic background entities per 12-hour lookback. No current test-case truth or prospective sensor answer entered the policy-visible feature.

## Failure that must remain visible

Shared upstream misinformation: the two sources agreed while being wrong. The disagreement alarm flagged **0/75** post-85 decision instances; the disagreement method, fixed method and conservative method each made **three false synthetic assertions**. This is NOT a lineage-independence detector. A clean disagreement rate is NOT proof of source correctness.

All eight precommitted research gates passed, so the *experiment* receives GO_FOR_FURTHER_RESEARCH_ONLY. An experiment passing its authored simulator does not establish real utility or allow the signal to be deployed.

## Stop/go for a second, genuinely different experiment

The next experiment must be preregistered separately with: **missing or delayed RAW publisher observations while review is down**, new colluding/syndicated provider structures, sparse background-pair coverage, and a nonzero cost for collecting/maintaining telemetry. Reusing only this seed or its same generator does not provide independent proof. In a world where two providers share the same incorrect upstream, no agreement/disagreement-only rule can guarantee physical correctness.

Falsification first: demonstrate that this signal avoids a distinct important mistaken action versus BOTH fixed and conservative controls on a new simulator, with paired false-assertion and utility accounting. If it fails, reject the candidate without threshold retuning on this exposed holdout. Only then reconsider an optional module; production still requires real validation and permissions.

## Engineering disposition

The historical first-run evaluator, temporary CI, and five targeted experimental tests remain in the original branch commit for reproduction only. **They were excluded from main** to avoid permanent algorithm growth or unnecessary CI overhead before added utility is independently replicated. The main tree includes this preregistration, result, explanation and ADR. The unchanged Core and 880-test CI stay the same.

Real Istanbul source accuracy: UNKNOWN. Real independent human labels used here: ZERO. Real source downloads: ZERO. Model calls: ZERO. Consumer publishing: DISABLED.

## Rollback

Remove only this public synthetic protocol, aggregate evidence, research report and ADR. No earlier source archive, field data or application algorithm has been changed.
