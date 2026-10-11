# ADR-0011: Frozen POI sampling frame and independent blind Excel review intake

**Status:** Accepted as offline research infrastructure only  
**Date:** 2026-10-11  
**Tracks:** KEP-DATA-004 / Issue #13, depends on PR #16 (real Overture frame), SCI-003, DATA-002.

## Problem

KEP has 4,803 real Overture source records, but **zero independent ground-truth labels**. A private stratified random sample of 60 records and two independent, identical reviewer templates exist. Without an audited intake path, a swapped ID, edited displayed address or omitted hard-to-verify venue could silently bias source reliability estimates. The existing estimator expects structured JSON ballots and cannot directly read the actual field sheets.

## Decision

A narrow **offline XLSX reader**, implemented with bounded standard-library OOXML parsing, reads only the known `Saha Denetimi` and `Araştırma Kimliği` sheets. It never runs Excel macros, workbook formulas, scripts or network calls. It enforces:

- Source release `2026-09-23.1`, 4,803-record population hash, exact 60 sampled IDs, immutable registered GitHub source run, role A/B and every visible name/address/category/coordinate/map link against the pinned repository archive.
- Frozen sample rebuilt using an **off-repository private seed**, archived source checksums and sampling date. Unmatched source frame, changed sample allocation, missing/extra rows or changed immutable columns fail closed.
- Reviewer ID, independently supplied specific HTTPS citation, timestamp and explanation for each completed vote. Placeholder reviewer IDs cannot be submitted as real labels.
- Two distinct human reviewer *identifiers* must agree on a resolved existence label. `unknown`, missing/late votes, or conflicts yield **no population error-rate estimate**; disagreement requires a separately audited third-human resolution workflow.
- Existing population-weighted `estimate_existence_error` is called **only when all 60 rows are concordant and resolved**. Its conservative, preregistered Hoeffding interval is reported, not substituted by an optimistic sample standard error.
- No secret seed, raw human IDs, evidence URLs or individual labels are output by the CLI; no consumer display, `open_now`, push, nor source-rights mutation.

## Precision warning

In the frozen 60/4,803 sample, the conservative 95% stratified Hoeffding union-bound **half-width is 0.517502**, before seeing any labels. Thus 60 is a **process pilot**, not proof of a useful ±5% or ±10% source-error prevalence. Intervals assume random drawing within strata and correct human labels, neither proved by a code-only test. Do not call an inferred result "verified Istanbul accuracy".

## Explicit non-goals

- No actual human existence reviews have been collected.
- No online/AI verification of source records; Google coordinate search is not a substitute for venue existence evidence.
- No import of arbitrary spreadsheets or unsanitized reviewer uploads into CI.
- No independent proof that two distinct IDs represent different people. Operational blind review still required.
- No third-human adjudication or inference under nonresponse yet. These are separate follow-on tasks; never impute labels.

## Validation and rollback

- Unit tests use *simulated human votes* on the real frozen Overture IDs. They do not create true existence labels.
- Python 3.11 / 3.13 offline CI runs the importer schema tests and the original 403+ test suite; no API key.
- Remove the DATA-004 files and CI smoke line to roll back; pinned data and prior sampling designs are not modified.
