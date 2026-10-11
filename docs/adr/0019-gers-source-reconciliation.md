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
6. Ordinary CI is network-free and uses Python 3.11/3.13. Optional manual acquisition requires explicit confirmation and a fresh output path, has a bounded body budget, and exits nonzero on incomplete capture. Remove the temporary push-triggered acquisition/publishing workbench before merge.

## Acceptance and limitations

Baseline: 601 tests. New regression cases are added before their corresponding fixes. Reproduce real results using `python scripts/reconcile_gers_releases.py --check`; timing measurements are excluded from deterministic equality checks.

Source counts remain 4,650/4,803, shared 4,581, locally added 222, removed 69, revised 198 and confidence-only 3,337. The new queue has four unverified identity candidate pairs versus the existing comparator's three. Official-event agreement, physical-event precision/recall, calibrated business confidence, actually wasted inspections and competitor superiority remain unmeasured.

Both raw catalogs and the original failed-capture receipt are SHA-pinned. The original August ZIP is unchanged. Checksums are local integrity evidence, not independent publisher authentication. Source references and experiment details: `labs/core/docs/GERS_RECONCILIATION.md`.

## Rollback

Revert the DATA-013 implementation, its three test files, manual capture CLI, replay/benchmark files, access-evidence directory, report, and DATA-013 CI/documentation additions. Do not revert or regenerate the August/September source archives or earlier research modules. No database, production, Web Push, paid API, consumer or field-review state was changed. Reverting DATA-013 affects only this isolated research layer.
