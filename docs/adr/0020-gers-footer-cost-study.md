# ADR-0020: metadata-first GERS I/O planning and unverified patch baseline

Date: 2026-10-11. Status: accepted on merge for research code only. Relates to #22 and PR #31; follows ADR-0019.

## Context

The prior 256 MiB experiment did not produce a completed official event batch. Increasing its budget without understanding row-group layout would conceal the cost and coverage problem. DATA-014 preregistered a separate 16 MiB application-body metadata experiment and completed it within 1,072,094 body bytes (2,063,202 conservatively reserved), using 392 requests.

## Decision

1. Keep acquisition explicit and metadata-only: exact allowlisted public release paths, bounded footer/range reads, ETag/If-Match and Content-Range checks, no retries/redirects. An incomplete acquisition exits nonzero.
2. Reuse DATA-013's pinned Places pair, release metadata and canonical representation. Never re-download the August archive. Preserve exact new footer bytes and per-object hashes in a separate research artifact.
3. Keep ordinary CI offline/standard-library-only. The optional pinned Arrow dependency belongs only to manual acquisition. Remove the temporary push-triggered source/authoring workbench before merge.
4. Treat row-group statistics as exclusion bounds, never presence proof. Unknown statistics retain groups. Keep spatial scope explicitly distinct from exact ID-union scope.
5. Report chunk-byte sums as estimates, not observed query transfer or universal algorithm lower bounds. Two release paths are summed without assuming cache identity.
6. Preserve the observed 64 cross-release identical footer/ETag/size pairs. Do not count them as independent evidence, authenticate full event content from metadata, or assume STAC prev links prove a changelog's comparison baseline. Block the scientific claim of completed per-hop reconciliation until that baseline is verified.

## Observed result

128 objects, 1,244 row groups. ID min/max retains all 1,244 groups: estimated six-column chunks 5,789,190,970 bytes. Geographic pruning retains eight groups: 35,805,264 bytes, but is incomplete for arbitrary ID movement. 1,236 excluded regional groups remain ID candidates. No event rows or data pages were read; official agreement and business-event accuracy remain null.

The original successful metadata ZIP is pinned at SHA-256 `1cefe054f5b61adfa2117d43e441626ab5355fed1096aa105b397d70f619bf9d`; the first source-length validation failure is preserved separately. Acquiring metadata is a success for DATA-014, not completion of Issue #22.

57 new tests build on 664 existing cases (721 total). Thirty-two initial tests were written before the new planner, followed by thirteen transport regressions before the lengthless-response/status/encoding fix. Twelve real archive checks remain separate from these synthetic/mock cases. Exact replay and Python 3.11/3.13 CI gate merge; no independent human scientific review is implied by automated checks.

## Rollback

Revert only DATA-014 modules, scripts, three test files, footer artifact/failure receipt, result reports, this ADR/protocol and added offline CI steps. Preserve all prior Places and DATA-013 archives/modules. There is no database or consumer migration to undo. The ephemeral acquisition workflow is absent from the final change.

Full methodology, source references, measured timings and remaining experiment: `labs/core/docs/GERS_FOOTER_COST.md`.
