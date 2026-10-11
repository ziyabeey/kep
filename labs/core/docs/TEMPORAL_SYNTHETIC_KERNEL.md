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
