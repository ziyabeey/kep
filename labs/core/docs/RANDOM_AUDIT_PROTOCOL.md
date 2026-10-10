# KEP-SCI-003 | Stratified Random Source Audit (research-only)

**Status:** offline prototype. No actual Istanbul source error rate, manual human review, user trial, or deployed model is claimed.

## Why this exists

SCI-001 selects uncertain claims for extra research; SCI-002B collects independent human decisions. Such reviewed claims **cannot** estimate the fraction of bad claims in the *whole* source population because review selection is biased. A highly targeted inspection queue may find more defects and simultaneously badly exaggerate apparent overall risk.

**Two queues, two purposes:**

- **Targeted verification** (high uncertainty/urgency): find and fix likely critical errors, but cannot estimate the overall population error rate from the raw reviewed fraction.
- **Randomized audit**: select a prespecified stratified simple random sample from an immutable, rights-checked set of claims; disclose sampling probabilities and require complete independent adjudication before estimating population error.

Do not merge targeted and random labels to report source reliability. Individual reviewer independence is an operational and governance obligation, not proven by different ID strings.

## Statistical design

A frame is frozen at an explicit **timezone-aware** `asof`. Every `ReviewCandidate` must have a permitted `research_ingest` registry source, city and source-host match, and an immutable local `<sha256>.snapshot` with matching bytes. Reposts from the same publisher-root for the same entity/field/decision time cannot inflate the frame.

The population is divided by `(publisher_root, field)` into strata. Allocate at least two audit items per stratum where possible, then remaining items proportional to population count. If the budget cannot cover the minimum, **refuse to sample** instead of silently excluding strata. Sampling is SRS without replacement inside each stratum, based on a private seed. The original frame, sample, inclusion probabilities and a SHA-256 commitment to the private seed are recorded; **the seed itself is never logged or committed**. To report an estimate, a later reader must supply the same seed to reproduce the draw exactly, preventing post-label cherry-picking.

For stratum \(h\), population \(N_h\), random audit sample \(n_h\) and observed error proportion \(\hat p_h\):

\[
\widehat{R}=\sum_h \frac{N_h}{N}\hat p_h
\]

The corresponding inverse inclusion probabilities are \(N_h/n_h\). A very conservative, fixed-frame diagnostic error band is generated with a **within-stratum Hoeffding bound and Bonferroni union bound**:

\[
\epsilon_h = \sqrt{\frac{\log(2H/\alpha)}{2n_h}},\qquad
R\in\left[\widehat{R}-\sum_h \frac{N_h}{N}\epsilon_h,\quad
\widehat{R}+\sum_h \frac{N_h}{N}\epsilon_h\right]\cap[0,1].
\]

If an entire stratum was reviewed, its sampling uncertainty is zero. **This is not a guarantee of correctness** if humans are wrong, selections were not truly random, the frame omits important records, labels are unresolved, or the source distribution changes after the audit. The interval will often be too wide to make a decision when the sample is small. Do **not** replace it with a more optimistic interval after looking at test outcomes.

Unknown, superseded, not-yet-reviewed, or late adjudications count as **nonresponse**. With any nonresponse, the module returns no population error estimate (not even using the available labels as if they were representative). Review timestamps later than the evaluation cutoff cannot enter an earlier report.

## Offline benchmark and what it means

```bash
cd labs/core
python -m benchmarks.audit_bias_eval
python -m unittest discover -s tests -q
```

The fixed synthetic population has 1,000 claims (600 'official', 250 'editorial', 150 'community') with deliberately different, **invented** error rates. A deliberately targeted inspection of 120 community claims overstates the true population error in this particular constructed world. Forty separate 120-item randomized audits give a much closer mean point estimate, though the conservative confidence bands remain wide. No independent Istanbul human labels, Haiku model calls, live API reads or real-world reliability conclusions are involved.

## Human data entry workflow

1. Freeze a **fully enumerated** legal source observation frame and verify source-use rights (`KEP-SRC-002` is not complete yet). Keep all source bytes privately; do not commit unpublished snapshots.
2. Select a private random seed. Save it securely outside git; set it via `KEP_AUDIT_SEED` in the local research environment. Never paste it into a ticket or workflow log.
3. Make a plan **before any human outcomes** are known. Record and hash the frozen frame, sample IDs and probabilities. Do not replace the plan after reviewing a failed example.
4. Request SCI-002B human ballots **only for the sampled claims**; critical time/place/cancelled fields require dual review and adjudication when the reviews disagree. Nonrandom urgent reviews may happen separately but never enter this estimate.
5. Run the estimate at a specified evaluation cutoff, with `ReviewedClaim` rows exported through the rights/snapshot verification gate. Incomplete audit means no population estimate. Record population hash, window, label completeness, source breakdown and conservative interval.
6. Keep SCI-002 training/validation/test windows separate; an audit frame must not contain model predictions trained or calibrated on future outcomes.

```bash
# After authorized source snapshots and reviewed JSONL files have been collected:
cd labs/core
export KEP_AUDIT_SEED='<private-random-seed-kept-out-of-git>'
python scripts/audit_source_reliability.py plan \
  --candidates data/reviews_private/candidates.jsonl \
  --snapshots data/source_snapshots_private \
  --budget 40 --asof 2026-11-01T12:00:00+03:00 \
  --out data/reviews_private/plan.json

python scripts/audit_source_reliability.py evaluate \
  --candidates data/reviews_private/candidates.jsonl \
  --snapshots data/source_snapshots_private \
  --plan data/reviews_private/plan.json \
  --reviewed data/reviews_private/reviews.jsonl \
  --asof 2026-11-10T12:00:00+03:00 \
  --out data/reviews_private/estimate.json
```

These commands are intentionally **not** executed against real sources in CI and should not be used to assert `verified`/send push/activate a source. `KEP_AUDIT_SEED` must not be stored in repo secrets used by CI (CI intentionally does not sample live private source frames).

## Known limitations and follow-up

- Benchmark source errors are synthetic by construction. It is not a reproduction of a paper's headline result.
- The current SCI-002B data format does not cryptographically prove review independence or that a reviewer correctly read external evidence.
- A frame covers collected observations, not **all possible** events in a semt: the radar's *recall* and collection coverage need a distinct audit.
- Source-level errors may correlate with time, events, publishers, and hidden features; historical risk estimates are not future guarantees.
- For real operations, log what was **not collected**, source outages and inaccessible content. Investigate differential nonresponse and add a fresh untouched audit period for any new model or policy.
- The initial `min_per_stratum=2` guard may exceed affordable sample budgets when there are hundreds of publishers. Before scaling, pre-register coarser policy-controlled strata and/or a separate audit allocation study.

## Research foundations (methods, not direct implementations)

- Qing & Valliant (2025), *Extending Cochran's Sample Size Rule to Stratified Simple Random Sampling with Applications to Audit Sampling*, DOI: https://doi.org/10.1177/0282423X241277054.
- Deshpande & Kuleshov (UAI 2024), *Calibrated and Conformal Propensity Scores for Causal Effect Estimation*: https://proceedings.mlr.press/v244/deshpande24a.html.
- *Active learning with biased non-response to label requests* (2024): https://link.springer.com/article/10.1007/s10618-024-01026-x.
- Pervin, Wang & Kim (2026 preprint), *A Calibration Framework for Inference with Partially Observed Data*: https://arxiv.org/abs/2602.19203.
