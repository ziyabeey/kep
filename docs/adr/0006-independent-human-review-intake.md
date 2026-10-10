# ADR-0006 · Reviewed field-claim intake before calibration

**Status:** research implementation, no consumer release authority  
**Date:** 2026-10-11  
**Tracking:** #9 KEP-SCI-002, PR scoped to SCI-002B

## Problem

The earlier temporal source-calibration lab accepts a single `ReviewedClaim` per source-root field claim. That is a useful numerical interface but **does not enforce the human review process** promised in ADR-0005. In particular, `starts_at`, `venue` and `cancelled` require multiple human reviewers and explicit handling of contradictory findings. Without that process, an AI-generated or uncorroborated label could accidentally become training data.

## Thesis / antithesis / synthesis

- **Thesis:** a single reviewer can quickly label hundreds of source claims; cheap but vulnerable to errors and reviewer drift.
- **Antithesis:** force two or three reviews of every field before any experiment; expensive, delays all calibration, including lower-risk price metadata.
- **Synthesis:** critical claims require at least **two distinct human reviewer IDs**. Noncritical claims permit one; contradictory ballots **never majority-vote themselves into truth** and require a third, distinct human adjudicator. All decisions are tied to one immutable snapshot digest and a time cutoff. Pending/disputed examples are **not silently relabeled incorrect**. Only operator-approved research sources and locally hashed snapshots may be exported to the calibration interface.

## Invariant boundaries

1. `ReviewCandidate` contains the exact *claimed value* and field-specific metadata: source URL, publisher root, event identity, city, capture/decision timestamps, immutable SHA-256 and research right.
2. `ReviewBallot` is a pseudonymous human review, links to the same snapshot, has an evidence URL, a reason code, and a real review-completion timestamp.
3. `ReviewAdjudication` is required when human reviews disagree; its ID must differ from all initial reviewers. Reviewers cannot review the same claim twice, including case-only variations of an ID.
4. Reviews completed **on or after** the evaluation cutoff are excluded. Future labels must never migrate into an earlier as-of run.
5. A finalized `ReviewedClaim` can be exported only when registry use is explicitly `research_ingest`, the registered source and city match, and the original snapshot bytes match the recorded SHA-256.
6. Review evidence is an **operator assertion**; this tool does not verify whether the cited website supports a claim. Independent humans inspecting the same page do **not** create independent source corroboration.
7. Neither a correctly reviewed historical field nor a high statistical confidence authorizes publishing, push notifications, new source access or trust badges. All publishing remains disabled.
8. Inputs, snapshots, ballot histories and finalized labels live in gitignored private paths; no review bytes or personal accounts are committed.

## Implementation

- `labs/core/kepcore/review_intake.py`: typed, strict candidate/ballot/adjudication records; gate and as-of resolution.
- `labs/core/scripts/intake_human_reviews.py`: offline CLI, no HTTP/AI; default dry-run summary; opt-in label export requires registry + SHA-256 snapshots.
- `labs/core/tests/test_review_intake.py`: simulated review scenarios including missing second reviewer, contradictions, third review, cutoff leakage, duplicated roots, mismatched hashes and rights denial.
- `labs/core/docs/REVIEW_INTAKE_PROTOCOL.md`: detailed human workflow and CLI contract.

## Scientific cautions

- **Reviewer ID distinction is necessary, not sufficient:** actual human independence, evidence quality, identity governance and protocol adherence require an independent operating process.
- **Snapshot SHA-256 establishes bytes integrity, not truth.** Source itself might be wrong or intentionally misleading; temporal evidence may remain unresolved.
- Single reviews for noncritical fields carry lower adjudication confidence; `unknown` / `superseded` remain available and are excluded from binary calibration.
- Calibration conclusions remain **hypothetical** until enough real, legally collected, human-adjudicated Istanbul observations exist across train, calibration and test periods. No claim of conformal or future risk guarantee.

## Rollback

Remove research-only intake module, CLI, tests and ADR. No schema migration, external API, secrets or production state. Existing calibration runs remain unchanged.
