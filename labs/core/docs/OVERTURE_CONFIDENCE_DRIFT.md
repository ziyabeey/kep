# KEP-DATA-011 | Two genuine Overture releases: confidence drift and targeted verification

**Scope:** The **exact** 2026-08-19.0 and 2026-09-23.1 Overture Places releases, only the frozen Beşiktaş/Karaköy research rectangles. This is a study of **provider-record drift**, not the real-world opening/closing of businesses. No consumer publication, no source-right changes, no calls to MiMo/Laya, no model-derived truth probabilities.

## Scientific question

When a POI source refreshes, which reported differences warrant verification? The basic independent release comparator (KEP-DATA-010) established counts. Here we distinguish (a) new/missing record IDs, (b) descriptive or geometric revisions, (c) schema-only category changes, and (d) supplier confidence changes without other field changes.

An Overture `confidence` number must **never** be interpreted as the empirically calibrated probability that a business exists. Changes may be related to sources, matching models, maintenance operations, or other provider factors. Our observational data **do not identify the cause** of any score change.

## Frozen source provenance

- August: Original Actions run [38121005943](https://github.com/ziyabeey/kep/actions/runs/38121005943), artifact 11695042455, ZIP SHA-256 `cb9ee86c128b4839a00722e1b192f460691c0f33e358f0b0b9ae458ea403ef05`. The loader checks both ZIP and internal file digests.
- September: `labs/core/data/real/overture_istanbul_2026-09-23.1` in the repo, from Actions run 38096227796, pinned and checked by `load_archive(verify=True)`.
- **Chronology:** August *release data* was fetched **after** the September release artifact. Thus the analysis contrasts **release versions**, not a chronological stream of business sightings.
- **Schema:** August v1.18 vs September v2.0; taxonomy changes are not automatically comparable as real business-category changes.
- Source SHA-256 pins bytes and proves repeatability. It is *not* a third-party source-authenticity attestation or proof of ground truth.
- Older original release artifacts are subject to Overture's retention policy. Do not copy full historical records into public artifacts without a separate rights and retention review.

## Reproduce (without live APIs)

```bash
cd labs/core
python -m unittest tests.test_overture_change_triage -v
python scripts/overture_confidence_drift.py
# Download the exact *original* August workflow artifact and place it locally:
python scripts/overture_confidence_drift.py --august-zip .local/august-original.zip
# The next command writes only a TARGETED work queue to a gitignored private file:
python scripts/overture_confidence_drift.py \
  --august-zip .local/august-original.zip \
  --private-queue-output .local/targeted-60.json
```

No external requests are made. The public JSON aggregate includes no business titles, location coordinates, contact information, personal identifiers or per-place IDs. The queue output includes opaque Overture IDs **only** and stays local.

## Targeted triage is NOT a random audit

The fixed 60-task operational queue assigns 12 *no longer listed*, 12 *newly listed*, 16 descriptive/geographic revisions, 8 schema-sensitive-only revisions, and 12 confidence-only changes with absolute delta over 0.10. Within each lane, a stable SHA-256 ordering picks records independent of human labels. This is designed for discovering useful anomalies, **not** estimating the population-wide source error rate. Reviewers must never feed this targeted sample into SCI-003's random, probability-weighted prevalence estimator. It also grants no automated browsing rights for external sources.

Candidate states:
- `no_longer_listed`: a record disappeared from the Overture release, **not** confirmed closure;
- `newly_listed`: a new supplier ID appeared, **not** confirmed opening;
- `property_or_location`: at least one source field changed, **not** independently confirmed real-world change;
- `schema_only`: changes limited to new taxonomy/basic-category fields, **not** verified recategorization;
- `confidence_only_over_0_10`: large supplier confidence changes **without** other descriptive changes, not an error label.

The QUEUE itself does not certify that verification is needed at a particular cost: value-of-information, source rights and human cost still require future calibrated evidence. Follow-ups must be consent/rights compliant.

## Next independent test

Use the official Overture GERS changelog for the appropriate release, compare `added`/`removed`/`data_changed` semantics with the locally pinned extract, and mark excluded fields (`sources`, `confidence`) separately. Do not assume official changelog validates business reality or the regional extraction. For a true field accuracy estimate, commission blinded random human audits independently of targeted triage.
