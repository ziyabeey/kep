# ADR-0026: synthetic one-step value-of-information gate above CORE-001

Date: 2026-10-11. Status: research-only, accepted only after green Python 3.11/3.13 CI and exact benchmark review. PR #37 follows ADR-0025.

## Context

CORE-001 implements strict asynchronous as-of evidence, one-vote-per-publisher-root, Core eligibility veto and a hypothetical model context allowlist. Its frozen synthetic benchmark revealed a real engineering tradeoff *within the invented simulator*: tighter source corroboration avoids false assertions but loses correct opportunities when independent evidence is missing or delayed. User explicitly requested zero new real-data searches or downloads and wants to establish the kernel using wholly synthetic data.

An earlier Evidence Lab implements assumed Bayesian channel sensitivity/specificity and information-value mathematics. The new layer should reuse those primitives rather than invent a competing provider or silently alter existing decision rules.

## Decision

1. Add an entirely optional and offline one-step planner restricted to one eligible Core candidate with **one existing fresh positive publisher-root claim**. Use existing source time/independence checks; never permit a failed Core rights, date, price, geography or consent gate to be upgraded.
2. Preserve hard abstention and human-review routes for contradictory, negative-only, zero-valid-root and already-fully-corroborated cases. One new sensor cannot solve zero source roots under CORE-001's two-root contract.
3. Candidate check must be explicitly approved for *hypothetical research*, independent of the already-used publisher root, bounded by normalized check cost and maximum response latency. A duplicated same-root free sensor or an unapproved near-perfect sensor is forbidden.
4. Rank permitted checks under five *frozen* policies: never, cheapest, max-information, always-strong and value-of-information. VOI evaluates a one-step positive reply's modeled utility using existing Evidence Lab functions, subtracts the utility-unit cost, and only proposes a net-positive check. All likelihood/reward/penalty parameters are **assumed**, uncalibrated, not measured from Istanbul or actual KEP.
5. PROPOSE_CHECK has **no host action, network call, source crawl, tool permission or production effect**. Even after an invented check comes back, the simulated final decision is still subject to unchanged CORE-001 rights/identity/source gates at the same deadline for each policy; result is LAB_CORROBORATED at most, never true physical existence.
6. Pair **2,400** predeclared wholly synthetic known-truth trials across 6 regimes and 5 strategies, with the prospective answers hidden inside a Trial envelope and structurally absent from planner View. Charge the cost even if the source responds negatively. Include quality degradation and mirror storms; do not tune parameters on observed results or hide unfavorable outcomes.
7. Require both Python 3.11 and 3.13 full CI plus stable aggregate-result SHA-256 comparison, with no new data acquisition or change to pinned real source archives/FIELD-001 private files. Simulation bootstrap intervals describe uncertainty conditional on this invented generator, not field accuracy.

## Rollback and limits

Revert only the optional CORE-002 planner/benchmarks/tests, offline replay and CI additions, this ADR and lab study. No need to revert CORE-001, source archives, user data, credentials, database, model integration, field files, existing quotas or push/consumer features. Future multi-step adaptive verification is separate and should not be assumed safe because this one-step proposal passes CI.

Full experiment: labs/core/docs/CORE_002_BUDGETED_EVIDENCE.md.
