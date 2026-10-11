# KEP-CORE-001: time-aware research kernel on known-truth synthetic data

**Research-only, offline-only. No new real-data search, download, field visit, registry/Parquet work, model training, consumer or notification action.** Earlier immutable Istanbul archives and private FIELD-001 reviews are left unchanged. Related: Issue #13/#22 only historically; [ADR-0025](../../../docs/adr/0025-temporal-evidence-kernel.md); [PR #36](https://github.com/ziyabeey/kep/pull/36).

## Goal

Make the existing Core hard eligibility gate, the independent source-root evidence rules and the Laya/MiMo structured model boundary work together as a **deterministic temporal decision pipeline**. Do not claim real-world truth from two sources, regardless of whether they agree.

## Decision sequence

1. Existing Core decides which candidates pass rights, user filters, budget, radius, times and hard constraints. Core REFRESH, CLARIFY, ABSTAIN and SILENT cannot be promoted by source agreement.
2. An immutable Signal has an event ID, entity ID, publisher root, observation time, *available-to-KEP* time, Boolean assertion and research-rights scope. Both times are timezone-aware, delivery cannot precede observation, and as-of replay never sees future or late events. A fixed lab TTL (48h) excludes stale observations. Duplicated identical event IDs are idempotent; conflicting reuse is rejected.
3. Collapse by (entity ID, publisher root), taking the most recent observation timestamp, independent of arrival order. Identical syndicated posts count ONCE. Contradictory same-clock source claims are disputed; conflicting independent roots also block.
4. At least two currently permitted and fresh **independent positive publisher roots**, with no active contradiction, produce status MULTI_ROOT_SUPPORT. Single-root claims are incomplete; negative-only assertions prompt human review, NEVER an actual shop closure label.
5. Pass only the candidates surviving both gates to the EXISTING model adapter. It cannot invent IDs, alter quoted facts or bypass a stale snapshot. No actual model is called.
6. Results are LAB_CORROBORATED / LAB_ABSTAIN / CORE_REFUSED, always research-only. A supported publisher claim is **not verified physical existence**. Real-world accuracy, official event agreement, opening/closure rate, consumer publish and model use remain false or null.

## Synthetic experiment frozen BEFORE comparison

The fixed config at benchmarks/temporal_core_protocol.json specifies seed **20261011**, **600 cases per regime** (3,000 total), 300 paired bootstrap draws and false assertion penalty **4** in normalized utility units. Truth is in SimCase, physically separate from policy input CaseInput. The same cases and prerecorded sensor outputs are given to five authored methods. No method is trained or tuned on the hidden outcome.

| Regime | Shift or adversary |
| --- | --- |
| matched | Assumed sensors sens/spec ~.90/.87 and .85/.82 |
| mirror_attack | 12 copies of one origin; sometimes no second independent source |
| delivery_lag | Some independent observations are first available after the decision clock |
| source_degradation | Sensitivity/specificity deteriorate to .62/.60 |
| rights_blocked | Hard catalog or sensor research-use permissions unavailable |

| Policy | Intended comparison |
| --- | --- |
| core_only | Existing Core eligibility with no second existence evidence gate |
| count_raw_messages | Deliberately unsafe method double-counting syndicated posts |
| single_root | One fresh supporting root sufficient |
| temporal_root | New strict independent-root/time/rights gate |
| always_abstain | Zero-coverage safety control |

The simulation records assertions, correct and false assertions, fraction of assertions wrong, coverage, missed true cases, normalized utility and paired conditional bootstrap differences. A conservative gate may score worse than an expansive baseline on utility. The protocol does **not** require a winner, and the reported intervals are conditional on these hand-authored assumptions, NOT real Istanbul field estimates or actual KEP competitor/user benefits. The original source archives are not used as synthetic truth.

## Offline reproduction

From labs/core:

    python -m unittest tests.test_temporal_pipeline tests.test_temporal_core_eval -v
    python -m benchmarks.temporal_core_eval
    python -m unittest discover -s tests -v

Ordinary Python 3.11/3.13 CI runs those checks without internet, optional data acquisition or model keys and saves aggregate-only output. A categorical two-root agreement is not a calibrated probability; independent human checks and a new prospective holdout would be required for physical business claims.

## Rollback

Revert only the new temporal pipeline module, simulator/benchmark, tests, fixed config, protocol, ADR-0025 and CI step. Leave older Core algorithms, all pinned real Overture archives, original simulated studies and FIELD-001 private coordinator/reviewer files untouched. No production/database/push migration.


## Initial frozen simulator result (October 11, 2026)

The exact **3,000-scenario** simulator output reproduced byte-identically on GitHub Actions Python **3.11 and 3.13**, before the checksum was frozen. Canonical SHA-256 of the complete sorted output is:

    1907d98db2cc142f20b393092eca9bfd81f03724ea91e0dfd7ea03629294b2ea

To verify this regression boundary offline, run:

    python scripts/replay_temporal_core.py --check

The checksum is an engineering guard. It is not external validation or real-business evidence. It deliberately fails if an updated source algorithm, generator assumption or configuration changes output; then a researcher must inspect what changed instead of silently changing the benchmark.

| Wholly synthetic regime | Temporal root asserted / 600 | False / asserted | Temporal utility per case | Raw-message utility | Single-root utility |
| --- | ---: | ---: | ---: | ---: | ---: |
| matched | 350 | 7 / 350 (2.0%) | 0.525 | 0.535 | 0.483333 |
| mirror_attack | 248 | 1 / 248 (0.40%) | 0.405 | 0.638333 | 0.63 |
| delivery_lag | 183 | 0 / 183 (0%) | 0.305 | 0.556667 | 0.498333 |
| source_degradation | 209 | 21 / 209 (10.05%) | 0.173333 | 0.218333 | 0.156667 |
| rights_blocked | 256 | 3 / 256 (1.17%) | 0.401667 | 0.376667 | 0.37 |

**The conservative policy does NOT win every synthetic metric.** In mirror and delivery-lag scenarios, a permissive one-root or raw-message control can earn more normalized utility by asserting more true cases, even while risking more false assertions. Under degraded source quality, the two-root kernel still makes **21 false assertions** of its 209 total. If we naively optimized this benchmark after seeing results, the holdout would be contaminated. We keep these adverse observations visible and propose separate next experiments, not a new claim of superiority.

None of these rates is Istanbul venue correctness, real model performance, verified shop closures, a production risk ceiling or a confidence interval for humans. The simulator's label distribution, sensor reliability, delay and utility are **invented by design**. The deferred/human-review outcomes should eventually connect to an authorized source-evidence workflow using new independent calibration, not be silently converted to acceptance.
