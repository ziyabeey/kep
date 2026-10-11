# ADR-0022: Same-publisher cross-patch regional event fingerprints

Date: 2026-10-11. Status: accepted only when code, report and offline PR CI are green. Related: Issue #22, PR #33, DATA-013/014/015.

## Context

DATA-014 observed 64 identical paired Places GERS footers, sizes and ETags across Sep 2026 patch paths. DATA-015 pinned a geographically bounded .0 added/removed projection. Documentation states the .1 patch corrected base and building_parts UUIDs but does not authenticate the comparison baseline that generated either changelog. We need observable source-row evidence before treating repeated publisher paths as distinct historical changes.

## Decision

1. Select exactly two matching .1 membership groups from the immutable DATA-014 footer metadata. Preserve DATA-015's default .0 reader policy; .1 is a distinct explicit opt-in that retains fixed byte/request limits and source allowlisting.
2. Capture a separately approved research-only .1 projection of the exact same bounding boxes, event types and union IDs as .0. Retain no raw ID rows; pin only the original canonical aggregate receipt and its SHA-256. Do not re-download August Places.
3. Compare canonical regional projected event fingerprints, not just counts, footer SHA-256, or ETags. A match establishes **same bounded projection**, not full Parquet equality, upstream authentication or a changelog build baseline.
4. Keep both publisher paths under one evidence root. In every output, leave global ID-union membership agreement, verified patch predecessor, physical business openings/closures and consumer accuracy as null or false. A green workflow must not silently promote evidence.
5. Preserve the original DATA-013/014/015 scripts and frozen archives. Ordinary Python 3.11/3.13 CI stays offline and standard-library-only; optional Arrow and network access are limited to the explicitly triggered temporary study, removed before merge.
6. Follow a test-first path with synthetic contract tests, mocked transport, separate pinned real footer and aggregate receipt tests. Any checksum, mismatched metadata, missing evidence, conflict or out-of-budget read halts.

## Observed result

The source reading task returned 218 regional added, 67 removed, 285 unique regional IDs and a SHA-256 of 524aeb660c7be71ddcd4fcd67f54c0c9af5bc15828ffe6208a85f81991d204c3, identical across .0 and .1. Each selected scan examined 207,733 row-group records. The .1 source read used 14 HTTP ranges, 8,022,067 HTTP application-body bytes, 5.293186 seconds, under a hard 16 MiB cap. This does not show complete 4,872-ID tracking or business truth.

DATA-016 original receipt SHA-256: a1bfed37f2fa0f83bbd3bf395297cbd01f4a47e054c25b767db37ccf3cf2ea64. GitHub Actions downloaded artifact ZIP SHA-256: 82a6dc93283e5e3c01feb68cd3a3cc66da69506d41438b576a236cf6df98274f. Byte checks are not independent publisher authenticity.

## Scientific limitations

DATA-014 indicated 1,236 region-excluded row groups still candidates for tracked IDs, and all-ID official agreement remains null. The two compared paths share Overture as one publisher, so equality cannot be counted twice. Overture .1 patch's actual changelog generation ancestor remains unverified. Unchanged patch regional observations may reflect republished files rather than a genuine zero-change independent period. No physical openings/closures or model accuracy are inferred.

## Rollback

Revert only DATA-016 modules, scripts, tests, pinned regional receipt, this ADR/protocol, explicit optional .1 range-reader parameter and added offline CI gate. Preserve prior Places, DATA-013, DATA-014 footers, DATA-015 receipt and PR #32 history. No database, Web Push, production or consumer migration to undo.

Details: labs/core/docs/GERS_PATCH_REGIONAL_EQUIVALENCE.md.
