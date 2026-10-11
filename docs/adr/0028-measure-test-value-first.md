# ADR-0028: Test admission must be driven by measured defect/decision value

Date: 2026-10-11. Status: accepted after successful QA-001 regression demonstration.

## Context

KEP passed 879 unit tests yet the previous CORE-002/003 simulations did not show universally better decision utility. Growing test counts without evaluating whether a test protects an actionable failure may waste engineering effort.

## Decision

Do not reward test totals or author large test suites speculatively. Before new regressions, freeze a consequence-oriented defect and run the existing test suite against a disposable mutation. Prefer reusing existing tests over duplicates. Introduce a NEW test only when there is an uncovered important failure. Recheck that exact fault and full normal CI. Compare added test runtime and maintenance burden.

QA-001 preregistered twelve synthetic faults, twelve sentinels, and fifty-two existing focused tests BEFORE outcomes. The big suite caught eleven faults; sentinels caught ten. The remaining unobserved bug was a specificity lower bound accidentally copied from sensitivity. One new functional, decision-level test caught it, bringing focused coverage to twelve of twelve. That is a regression outcome on an authored set only, not real detection probability.

Do not replace existing focused tests with the 12-sentinel subset based on count: the smaller subset was not reliably faster and missed an existing source-duplication guard. Keep full focused tests in ordinary CI. Run the expensive mutation research on demand, not every commit. No production modules, real-world data or core safety policies are changed by this ADR.

New synthetic STRATEGY experiments need a similarly preregistered baseline, impact metric, immutable holdout, and abort criteria. False assertions, valid decisions missed, cost per check, and unknown truth must be reported together; a simulator win cannot become a claim of physical venue accuracy.

## Safeguards

- Mutated modules live only in a temporary offline copy; original checksums are verified unchanged.
- Existing good-code control must pass or the mutation study aborts.
- False negative faults, source time leakage, root dependence, budget/rights bypass, and wrong abstention have higher review priority than extra test coverage numbers.
- User request to stop real-data hunting remains in force.

## Rollback

Drop QA-001 optional test audit tooling/report and the one targeted new synthetic test. All preexisting experiments, source archives and production systems remain unchanged.

Full results: labs/core/docs/QA_001_TEST_VALUE.md.
