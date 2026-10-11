# ADR-0019: GERS reconciliation boundaries and checked release compatibility

Date: 2026-10-11. Status: accepted on merge for research-only code; real official-event validation is **incomplete**.
Related: Issue #22, PR #30; follows ADR-0013/0014/0018.

## Context

Two existing, immutable Istanbul source extracts can be replayed offline. A local bounding-box difference is not an official global changelog event, nor a business event. The actual STAC catalogs show August -> September `.0` -> September `.1`. Comparing the last changelog directly with the August baseline would use the wrong predecessor.

A bounded, explicit source capture accessed public data but ended `INCOMPLETE_CAPTURE` without a complete event batch. The original receipt and catalogs are retained, rather than replacing missing events with predictions. An initially green research-workbench run is not a passing data-acceptance gate.

## Decision

1. Add `gers_reconciliation.py` on top of the existing validated snapshot, delta, drift and archive components. Keep raw schema differences, partial projections, source roots and duplicate observations explicit.
2. Real direct-event reconciliation is blocked by the pinned nonconsecutive release chain. An operator label cannot override it. Implemented event-envelope contracts are tested only with labeled synthetic rows, separately from untouched real-archive regression tests.
3. Preserve contradictory event variants and abstain on unverified predecessor, partial capture, missing events, conflicting observations or incompatible inputs. No added/removed-to-opening/closure conversion, model-as-independent-vote, automatic identity merge or consumer publication.
4. Keep confidence/source-only updates outside physical-change verification. Retain schema-only cases for technical review. Identity hypotheses may use exact normalized names and <=45 m distance within a cell, not incompatible category equality. They are targeted candidate pairs, not verified matches or a random audit.
5. Keep public reports aggregate-only; private queue exports are new mode-0600 files under the non-symlinked ignored `.local` directory. No reviewer labels, seeds or customer data are committed.
6. Ordinary CI is network-free and uses Python 3.11/3.13. Optional manual acquisition requires explicit confirmation and a fresh output path, has a bounded body budget, and exits nonzero on incomplete capture. The temporary push-triggered acquisition/publishing workbench was removed in `ac353e4454c7eb287215624172d0df35ad0207cc`.

## Acceptance and limitations

Baseline: 601 tests. DATA-013 adds 63 tests, for 664 total: 30 synthetic reconciliation cases, 10 pinned-real replay cases, 21 boundary/export/capture guards, and two nonzero-denominator review regressions. These are four files: `test_gers_reconciliation.py`, `test_gers_real_replay.py`, `test_gers_guards.py`, and `test_gers_review_regressions.py`. New regression cases were added before their corresponding fixes. Reproduce real results using `python scripts/reconcile_gers_releases.py --check`; timing measurements are excluded from deterministic equality checks.

[PR CI run 38145130867](https://github.com/ziyabeey/kep/actions/runs/38145130867) passed both Python 3.11 and 3.13 jobs for implementation head `ac353e4454c7eb287215624172d0df35ad0207cc`. Both aggregate replay artifacts were subsequently downloaded, their ZIP hashes checked against GitHub's artifact digests, and their entire `stable_results` objects compared equal. This is cross-runtime software consistency, not independent evidence of business truth. Artifact retention is seven days; the deterministic reference report and input archives remain in Git.

| CI artifact | ZIP SHA-256 |
| --- | --- |
| Python 3.11, `11704426584` | `d8d63cc38d2df2f22bcb3b27e060114ab8e4b667bf45e098d7f5f2bcabcc0dbe` |
| Python 3.13, `11703884736` | `6675d404fb8c52b9a91bf92e7a0d39f87bb5985f6d334bb42a0d4575bb8f7abe` |

Measured warm median seconds in that run were 0.001106 / 0.172814 / 0.539712 for naive / deterministic / reconciliation on Python 3.11, and 0.000658 / 0.093831 / 0.305380 on Python 3.13. Each uses three untraced repetitions with already-loaded inputs. A separate tracemalloc run measured reconciliation peaks of 24,953,077 and 24,952,957 bytes respectively, not total process RSS. Different runners and runtimes prevent attributing the time difference solely to Python version; the faster naive method performs substantially less work. These CI measurements do not replace the separately identified local measurement in the committed experiment report.

Source counts remain 4,650/4,803, shared 4,581, locally added 222, removed 69, revised 198 and confidence-only 3,337. The new queue has four unverified identity candidate pairs versus the existing comparator's three. Official-event agreement, physical-event precision/recall, calibrated business confidence, actually wasted inspections and competitor superiority remain unmeasured.

Both raw catalogs and the original failed-capture receipt are SHA-pinned. The original August ZIP is unchanged. Checksums are local integrity evidence, not independent publisher authentication. Source references and experiment details: `labs/core/docs/GERS_RECONCILIATION.md`. Issue #22 remains open for per-hop official-event capture/reconciliation and independent field evidence.

## Rollback

Revert the DATA-013 implementation, its four test files, manual capture CLI, replay/benchmark files, access-evidence directory, report, and DATA-013 CI/documentation additions. Do not revert or regenerate the August/September source archives or earlier research modules. No database, production, Web Push, paid API, consumer or field-review state was changed. Reverting DATA-013 affects only this isolated research layer.
