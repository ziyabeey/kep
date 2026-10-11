# KEP-DATA-005 · Third human adjudication and holdout planning

## Current evidence and scope

The frozen source archive contains **4,803** Overture POIs from two Istanbul sampling rectangles (release `2026-09-23.1`). **Zero** physical-existence judgments were available in the original two review workbooks at the time of implementation. There is no city-wide venue accuracy estimate. No person, model, or code may silently supply missing human field observations.

## Three-phase workflow

Keep completed reviewer A and B .xlsx files, private original sample plan, private seed, and any third adjudication JSONL in `labs/core/data/field_reviews_private/` (gitignored and access-controlled) or outside the checkout. Retain unedited originals and record reviewer invitations separately.

1. **A/B:** Complete their two existing workbooks independently. Each negative must have affirmative evidence of a real-world contradiction; an absent search result is not sufficient. A different reviewer ID string alone is not proof of human independence.
2. **Blinded C case issuance:** Only after an A/B *binary physical-existence disagreement*, run `blinded-cases`. It writes a new JSONL file containing only the immutable Overture attributes, a private pair-of-ballots hash commitment, and empty C decision fields. It **does not show A/B outcomes or identifying reviewer IDs**. Provide the case to a genuinely independent adjudicator who obtains fresh evidence, without conveying earlier verdicts. If A or B has `unknown` or missed the evaluation cutoff, don't coerce a C vote: manage a separately tracked re-review.
3. **Reconciliation:** C enters `exists`, `does_not_exist`, or `unknown`, pseudonymous identity, ISO-with-offset checked time, source-specific HTTPS evidence and substantive explanation. `reconcile` rejects an unexpected ID, changed case hash, altered source attributes, duplicate or same reviewer, early/late C vote, and any attempt to substitute `open_now` for physical existence. C's decision is recorded separately and original A/B workbooks are never rewritten. If even one case is unresolved, **error_fraction_estimate stays null**.

```bash
cd labs/core
# A/B and the other files below MUST be private and locally stored.
PRIVATE=data/field_reviews_private
python scripts/adjudicate_overture_field.py --mode blinded-cases \
  --reviewer-a "$PRIVATE/Reviewer_A.xlsx" \
  --reviewer-b "$PRIVATE/Reviewer_B.xlsx" \
  --plan "$PRIVATE/audit_plan_unlabeled.json" \
  --seed-file "$PRIVATE/AUDIT_PRIVATE_SEED_KEEP_SECRET.txt" \
  --evaluation-asof '2026-11-01T00:00:00+03:00' \
  --cases-output "$PRIVATE/blinded-adjudication-case-001.jsonl"

# After truly independent C responses have been recorded in the private file:
python scripts/adjudicate_overture_field.py --mode reconcile \
  --reviewer-a "$PRIVATE/Reviewer_A.xlsx" \
  --reviewer-b "$PRIVATE/Reviewer_B.xlsx" \
  --plan "$PRIVATE/audit_plan_unlabeled.json" \
  --seed-file "$PRIVATE/AUDIT_PRIVATE_SEED_KEEP_SECRET.txt" \
  --evaluation-asof '2026-11-05T00:00:00+03:00' \
  --third-ballots "$PRIVATE/blinded-adjudication-case-001.jsonl"
```

**Example future dates are illustrative.** The program never fetches URLs, logs the seed, calls an LLM, uploads these files to GitHub, or changes the user-facing venue catalog. The JSON output contains aggregate anonymous counts only, not personal reviewer IDs or evidence links.

## Sample-size and staffing forecast

```bash
python scripts/adjudicate_overture_field.py --mode forecast \
  --plan "$PRIVATE/audit_plan_unlabeled.json" \
  --seed-file "$PRIVATE/AUDIT_PRIVATE_SEED_KEEP_SECRET.txt"
```

This command **verifies the original freeze against the real archive** and computes a new design from the *remaining* 4,743 records. It never draws this proposed new sample or recycles the original 60. The study's estimand, sampling design, cost assumptions and reviewer capacity must be approved before issuing a new private seed for a distinct experiment.

| Proposed nominal 95% worst-case half-width | New, disjoint samples | Two reviewers × 12 minutes |
| --- | ---: | ---: |
| ±20 percentage points | 401 | 160.4 reviewer-hours |
| ±15 percentage points | 713 | 285.2 reviewer-hours |
| ±10 percentage points | 1,604 | 641.6 reviewer-hours |

Conservative per-stratum Hoeffding union bounds can be very wide. Without independent, complete and accurate human labels, these are **design forecasts only**, never measured error or a risk guarantee. Travel, evidence collection, adjudication, nonresponse and coordinate-check tasks may add material effort. Overture's own confidence is not an existence-truth label.

## Future observations

`physical_existence`, `currently_operating`, `open_now`, and `coordinate_correct` are separate research labels requiring separate protocols. An archived listing present in the dataset does not imply open now, and disappearance from a later release does not imply real-world closure. A second Overture release should be pinned, hashed and replayed in another PR when published.
