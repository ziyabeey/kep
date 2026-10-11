# KEP-FIELD-001 | Real-world physical-existence pilot, before labels

**Status: frozen, private fieldwork ready, ZERO actual human labels as of 2026-10-11.** Related: [Issue #13](https://github.com/ziyabeey/kep/issues/13), [Issue #22](https://github.com/ziyabeey/kep/issues/22), [ADR-0024](../../../docs/adr/0024-real-field-pilot-evaluation.md).

## Why we are changing direction

DATA-013/014/015/016/017 proved repeatable source ingestion, cautious source-diff labels, official GERS subset observations, and metadata access properties. Those are **software and publisher-data** results. We still do not know how often an Overture listed place physically exists, or whether any KEP signal anticipates real-world change earlier than a baseline. More S3 engineering cannot answer the first question.

This pilot operationalizes the **already implemented** DATA-003 private sampling, DATA-004 two-blinded-XLSX intake, DATA-005 third-human adjudication and population estimator; it does not duplicate those engines. We first measure label and evidence readiness. A future, separately sampled temporal change detector evaluation will test earlier/later changes after sufficient independent field evidence.

## True original data, new private draw

On **2026-10-11T17:27:29.232163Z**, BEFORE any human verdict, a new secret-seeded random sample of **60** was frozen from **4,803** actual source records of Overture Places release `2026-09-23.1`. Source compressed archive SHA-256: `4c25683a5d3af99444130c1f2be27b43dbdded3b756174111da0e9f722509bcf`.

These are two small research rectangles near Beşiktaş and Karaköy, **not all Istanbul and not the entire districts**. Stratification: 6 cells = (2 research rectangles) x (3 nonempty Overture confidence bands); selection follows the existing preregistered stratified random design with finite-frame inclusion probabilities. Source confidence is not reviewer truth.

The previously prepared historical anonymous 60-sample freeze is not silently replaced, recovered or treated as identical. The new `KEP-FIELD-001` 60-record cohort is a **separate independent draw**. No source data had to be re-downloaded. The script/tool that creates the real reviewer ZIP is NOT executed by GitHub CI.

We froze the following publicly shareable SHA-256 commitments, **never** the seed, 60 source IDs, private reviewer metadata or the lock's contents:

| Frozen part | SHA-256 |
| --- | --- |
| Unlabeled exact private sample plan | `3d728f609810c418179404d7cb6e45f484819d5e18d49e3b968c5bdcb8090a14` |
| High-entropy private seed commitment (not seed) | `36ad1f725c3db1510397680d873a32434373a6bca8de68b267c621555c3fe4a6` |
| 60 per-case naive/KEP policy locks | `2a09b337e17d240f5dbdb63ea44dd8201e8e4b38b3a09c3c345825085de726bd` |

The public status is `reports/KEP_FIELD_001_PREREGISTRATION.json`, with `human_labels=0`, `physical_openings=null`, `physical_closures=null`, `source_nonexistence=null`, `claim_accuracy=null`.

## Frozen, fair first-stage comparison

**Primary question:** Given an independent blind survey of these *source-listed* places, what is the **design-weighted share of physical nonexistence judgments** in the sampled frame? This is a source-quality diagnostic, not a closure/opening rate. Existing estimator only releases a statistic when ALL 60 A/B records have concordant, timely `exists` or `does_not_exist` judgments. Otherwise: `null` (missing/unknown/conflict are not guessed).

**Fixed policy baselines**, frozen BEFORE labels:
1. **Naive source assertion:** every Overture-listed record is asserted to be physically real (60/60 automatic assertions). Its source-nonexistence diagnostic, if measurable, is based on design weights, not naive unweighted sample percentage.
2. **Current KEP research rights/evidence gate:** no unverified Overture POI receives an automatic confirmed-existence assertion (**0/60 assertions**). This is *safe abstention*, but zero coverage is **not** predictive accuracy, higher business usefulness or competitor superiority.

No learned model is being evaluated here. After enough evidence, a separate prospective evaluation with an independently frozen holdout is needed for **KEP change-prediction performance**, e.g. precision, recall, timeliness, abstention and annotation cost versus a realistic equal-information baseline. Do NOT select a threshold after looking at this sample's results.

**Statistical limitation:** For the 60-record six-stratum design, the existing conservative nominal 95% union-bound half-width forecast is **0.517502**, or ±51.75 percentage points. This is far too wide for a precise source-wide rate. It is a field-process pilot, not a proof of citywide accuracy or a production launch criterion. Nonresponse, correlated external evidence and reviewer error are additional concerns.

## Human field protocol

Two genuinely distinct people **A and B** review the same 60 cases independently. Each sees the source name/category/address/coordinates and a map-search convenience link, **not supplier confidence, KEP verdict, the other person's vote, seed or selection probabilities**. Reviewers provide:

- `exists` when there is affirmative specific evidence the physical place corresponding to the source POI exists; `does_not_exist` only with affirmative *contradictory* evidence; `unknown` for ambiguity or insufficient evidence.
- Actual review timestamp in ISO 8601 with zone, stable private pseudonymous reviewer ID, a specific HTTPS evidence URL not equal to the generic coordinate-search link, and substantive explanatory reason. Merely absent web results never establish closure.
- Preserve evidence roots and observation dates; Overture-derived/mirrored listings are **not independent corroboration**, and a second reviewer ID alone doesn't prove independence.
- Never equate the physical-existence label with currently open, operating hours, exact branding, coordinate correctness, ID supersession, historical opening/closure or event availability.
- A/B do not exchange verdicts. In a disagreement the existing DATA-005 third-human adjudication is used, separately blinded; unknown/late outcomes are retained as unknown, not coerced to a binary verdict.

The user privately received a coordinator-only ZIP containing the new seed, plan, case-policy lock, initial 0/60 audit output and Turkish instructions, plus **two separately accessible blinded `.xlsx` workbooks**. No such files, live labels, named businesses, reviewer IDs, raw evidence URLs or private seeds belong in GitHub. Keep the coordinator ZIP away from both field reviewers. The ZIP is a working artifact in this conversation, NOT an upload to this repository.

## Reproduce the public method (no private files, network or model)

```bash
cd labs/core
python scripts/evaluate_field_pilot.py --protocol
python -m unittest tests.test_field_pilot tests.test_field_prereg_real -v
python -m unittest discover -s tests -v
```

After **actual human workbooks** are returned, securely unpack coordinator files into a new untracked/ignored directory, and use the same frozen plan and seed:

```bash
cd labs/core
python scripts/evaluate_field_pilot.py \
  --reviewer-a .local/field001/KEP_Istanbul_Real_Field_Reviewer_A.xlsx \
  --reviewer-b .local/field001/KEP_Istanbul_Real_Field_Reviewer_B.xlsx \
  --plan .local/field001/audit_plan_unlabeled.json \
  --seed-file .local/field001/AUDIT_PRIVATE_SEED_KEEP_SECRET.txt \
  --evaluation-asof YOUR_REAL_TIMEZONE_AWARE_CUTOFF
```

Do not literally pass `YOUR_REAL_TIMEZONE_AWARE_CUTOFF`: use the actual audited ISO timestamp cutoff; never backdate responses. `scripts/adjudicate_overture_field.py` remains the unchanged third-human workflow. The new evaluator itself writes no files, contacts no services, prints no source IDs/seed/ballot URLs, and never publishes consumers.

## Go/no-go

The initial go/no-go is **whether 60 genuine A/B reviews and source-linked evidence can be collected** while preserving independence and privacy. A computed rate may be viewed for a research diagnostic only after full admissible labels and manual review of evidence-root independence. An improved source prediction model needs an independently frozen holdout with adequate precision, and a second dated independent audit to study early change. Nothing automatically authorizes production, public places, recommendations or notifications.

Public source/rights: https://docs.overturemaps.org/guides/places/ and https://docs.overturemaps.org/attribution/ .

## Rollback

Revert `kepcore/field_pilot.py`, `scripts/evaluate_field_pilot.py`, its tests, the public preregistration summary, this protocol/ADR and the added offline CI step. **Do not delete/replace old source archives, previous scientific work or the private immutable coordinator pack**. There is no database, source, model, push or consumer migration.
