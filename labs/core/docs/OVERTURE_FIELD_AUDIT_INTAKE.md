# KEP-DATA-004 | Real Overture places: blind reviewer Excel intake

**Purpose:** Read the two already prepared field-review workbooks from KEP-DATA-003, check they still describe exactly the **same frozen 60/4,803 places**, and create a design-based diagnostic **only after all independent reviews agree**.

The workbooks are not proof that a site is operating. **No human results have been entered in the source pilot.** Structural checks on all 4,803 real source records do not imply actual venue-existence validation.

## Files that MUST stay outside the public repo

- `KEP_Istanbul_Real_Field_Reviewer_A.xlsx`, `KEP_Istanbul_Real_Field_Reviewer_B.xlsx` (human identities, evidence, future labels)
- `AUDIT_PRIVATE_SEED_KEEP_SECRET.txt`
- `audit_plan_unlabeled.json` and any completed adjudication

Preserve the unedited originals separately; reviewers fill copies **without seeing each other's judgments**. For each row they enter `exists`, `does_not_exist` or `unknown`, replace the `reviewer-a`/`reviewer-b` placeholder with their real pseudonymous reviewer identity, provide an ISO timestamp with zone, a specific HTTPS evidence link (not the generic coordinate search), and a substantive reason. Unknown results are not converted into successes or failures.

## Run locally

```bash
cd labs/core
python scripts/intake_overture_field_workbooks.py \
  --reviewer-a data/field_reviews_private/Reviewer_A.xlsx \
  --reviewer-b data/field_reviews_private/Reviewer_B.xlsx \
  --plan data/field_reviews_private/audit_plan_unlabeled.json \
  --seed-file data/field_reviews_private/AUDIT_PRIVATE_SEED_KEEP_SECRET.txt \
  --evaluation-asof 2026-10-12T00:00:00+03:00
```

No model or network is called. CLI only prints anonymous **counts and high-level status**, never names of people, seed, evidence URL or location of individual ballots. The `evaluation-asof` freezes which reviewer responses could have been known; later responses remain missing. The timestamp above is illustrative, not a claim that field reviews occurred on that day.

### Expected output for the currently blank real workbook pair

```json
{
  "status": "INCOMPLETE_BLIND_AUDIT",
  "population_n": 4803,
  "selected_n": 60,
  "reviewer_a_completed": 0,
  "reviewer_b_completed": 0,
  "concordant_resolved": 0,
  "missing_or_late": 60,
  "error_fraction_estimate": null
}
```

The actual report contains other metadata and the frozen sample allocation. It also includes `design_precision_forecast`. **Do not commit private files or completed review data.**

## Analysis rules

- **Source claims**: Overture 2026-09-23.1 contains 4,803 normalized POIs in two small rectangles. No upstream provider has been independently authenticated with retained raw GeoJSON and no live business status has been checked.
- **Sampling**: 60 selected by confidence-band × research-cell strata, seed kept private. Sampling proportions differ; use preregistered design weights, never naïve sample mean.
- **Blinding**: Overture confidence is deliberately withheld from the reviewer workbook; the XLSX reader still verifies the recorded name, address, category, lat/lon and map link.
- **Completeness**: One unreviewed, unknown, contradictory or out-of-cutoff record makes the rate unavailable. A disagreement requires a separately audited third-human decision, not a majority inferred by AI.
- **Precision**: Conservative 95% Hoeffding union-bound half-width for these strata is **0.517502** (51.75 percentage points). This is computed *before* labels and does not by itself establish any business error rate. Real human reviews and tighter sampling are needed before a useful prevalence estimate.
- **Privacy**: Reviewer IDs and visited URLs should remain in separately access-controlled local files. Do not upload them as GitHub artifacts or log them in CI.

## What to test next

1. Conduct genuinely independent blind reviews, with negative labels requiring stronger evidence than an absent search listing.
2. Design a third-review adjudication trail before settling any disagreements.
3. After the pilot, preregister a statistically powered **new** audit sample; do not resample until a desired result appears.
4. On the next real Overture release, take a second pinned source snapshot and report change-of-claim, missingness and duplicate drift **without asserting venue closure on missing records**.
