# KEP SCI-002 · Reviewer and calibration protocol

This is a **research tool**, not the KEP consumer publish policy.

## Unit of evaluation

The unit is a *single publisher-root claim about one field, at one captured time*:
`claim_id`, `entity_id`, `field`, `publisher_root`, `source_id`, `city`,
`claimed_at` (optional), `observed_at`, `predicted_at`, `checked_at`,
`snapshot_sha256`, `rights_scope`, `outcome`, `reviewer_id`, `evidence_ref`, `origin`.

- `claimed_at`: date stated by the publisher, if known; never set to capture time by default.
- `observed_at`: source contents were retrieved/snapshotted.
- `predicted_at`: when KEP would have made a decision from that observation.
- `checked_at`: when a reviewer finished checking it.
- `snapshot_sha256`: hash of a stored, permissible observation snapshot. This is evidence *integrity*, not evidence correctness.
- `publisher_root`: ownership/original publishing origin. Syndicated content from a shared origin is not counted as independent verification.
- `origin`: `human_review` or `synthetic`, never mixed in one experiment.

`outcome`: `correct` / `incorrect` / `unknown` / `superseded`.
Only `correct` and `incorrect` count toward Brier, source reliability and risk. `superseded` means an otherwise historical claim changed later, **not automatically incorrect**. If a time-specific claim cannot be reconstructed, use `unknown`.

## Human adjudication procedure

1. Confirm registry source access and license allow **research ingestion**; do not reuse permissions to assert **consumer display** rights.
2. Capture origin URL, response/version hash and timestamps before labeling.
3. Reviewer must not be the same person who authored the publisher claim; use pseudonymous IDs, no account credentials or unnecessary personal data.
4. Judge the **snapshot-time** statement independently using available evidence and record the citation URL. When primary and secondary sources conflict, retain both and mark unresolvable facts `unknown`.
5. For critical `starts_at`, `venue`, `cancelled` contradictions: require second human review and reconcile before importing a final label. A model-generated explanation is not independent corroboration.
6. Freeze cutoff dates in advance. Train only on labels known before `train_end`; pick every hyperparameter/threshold from training+calibration; report held-out test as observed, including failures.
7. Audit what was **not** observed: missing/denied pages, unresolvable venue, expired or canceled events, and language/district coverage. Label distribution from voluntarily submitted events may be biased.

## Off-line entry point

Place JSONL in a local ignored directory such as `labs/core/data/reviews_private/` (pseudonyms still count as personal data if linkable). The loader rejects extra keys, invalid dates, duplicate root observations, missing SHA-256, invalid use scope, and mixed synthetic/real origins.

```bash
cd labs/core
python -m benchmarks.calibration_eval  # deterministic synthetic replay, no network or API
python scripts/calibrate_source_confidence.py --input data/reviews_private/labels.jsonl \
  --train-end 2026-11-01T00:00:00+03:00 \
  --calibration-end 2026-12-01T00:00:00+03:00 \
  --evaluation-asof 2027-01-01T00:00:00+03:00
```

The command computes a lab report only. **No score is written back to Core, no source changes status and no notification is sent**. Code does not fetch any URL.

## Statistical caveats

- Source histories are clustered by publisher, time and event. The prototype's Wilson interval presumes independent Bernoulli outcomes; it is an **internal calibration heuristic**, not a coverage guarantee.
- An unseen publisher or poorly sampled field falls back to pooled correctness with uncertainty. Avoid “trusted” badges based only on this rate.
- Model output reliability and source field correctness are different probabilities; this module estimates the latter, not the former.
- Drift detection uses **labels observed after the event**. It identifies that previous assumptions became unreliable; it cannot time-travel to prevent already issued errors.
- Brier/ECE and ranking metrics should be reported along with coverage, abstention, field counts and unknown statuses, not as one weighted score.
- Test risk should not be used to adjust the threshold without creating a new untouched holdout period.

## Human-review enforcement (SCI-002B)

Use `docs/REVIEW_INTAKE_PROTOCOL.md` and `scripts/intake_human_reviews.py` before producing `ReviewedClaim` labels. Critical time, venue and cancellation claims need two human ballots; disputes need a separate third adjudicator. Real label export is gated by the research source registry and pinned source snapshot bytes. This is not automatic factual or publisher verification.
