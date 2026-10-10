# KEP-SCI-002B: Field-level human review intake

**Research only.** Do not use these labels to automatically publish events, score real people, send notifications, contact event organizers or assert business trustworthiness.

## Prepare real observations carefully

1. Check `sources/registry.json`: a source must be **approved for `research_ingest`**. `consumer_display` is separate. Istanbul's candidate sources currently remain pending until a specific right or official feed is authorized.
2. Capture a legally retainable raw response snapshot. Its digest is `SHA256(raw_bytes)`. Save as `data/source_snapshots_private/<digest>.snapshot` (gitignored). Never fill in arbitrary digests. Capture `observed_at` when those bytes were retrieved, `predicted_at` when KEP would have made the claim, and `claimed_at` only if present in source evidence.
3. Select **one explicit field/value claim**. Do not mix “the show exists” with “the show starts at 20:00.” Each claim must include a source-root ID and the field value. Store all candidate rows in private JSONL.
4. A reviewer inspects the claim and cites supporting/contradicting evidence. For `starts_at`, `venue`, `cancelled`, two humans each submit a separate ballot, without reading the other's verdict first. For other fields, one is permissible. An ID alone does not prove different people: the review operator must enforce actual human separation.
5. Reviewers use `correct`, `incorrect`, `unknown`, or `superseded` with matching reason codes. The cited URL is an **assertion**, not machine-verified truth. Historical states must be assessed as they were knowable at the recorded decision time, not using future information.
6. Contradictory ballots require **a third human**, distinct from both, to write an adjudication. Unresolved disagreements stay out of calibration. The third human's decision may itself be `unknown`.
7. Define the as-of time. Any ballot or adjudication completed after the cutoff is ignored for that run. Two reviewers looking at the same organizer site do not count as two independent *publishers*.
8. Export only after the registry confirms permission and the script checks each retained snapshot's **actual bytes**. Then call `scripts/calibrate_source_confidence.py` on the exported label JSONL with pre-declared temporal windows.

## Strict JSONL schemas

Each line is a complete JSON object, with no extra fields.

**`ReviewCandidate`:** `claim_id`, `entity_id`, `field`, `claimed_value`, `publisher_root`, `source_id`, `source_url`, `city`, `claimed_at` (string or null), `observed_at`, `predicted_at`, `snapshot_sha256`, `rights_scope`.

**`ReviewBallot`:** `claim_id`, `snapshot_sha256`, `reviewer_id`, `outcome`, `reviewed_at`, `evidence_ref`, `reason_code`.

**`ReviewAdjudication`:** `claim_id`, `snapshot_sha256`, `adjudicator_id`, `outcome`, `reviewed_at`, `evidence_ref`, `reason_code`.

Allowed `field`: `starts_at`, `venue`, `price`, `cancelled`, `opening_hours`.

Reason codes: `primary_confirmation` or `independent_confirmation` for `correct`; `primary_contradiction` for `incorrect`; `unresolved` for `unknown`; `historical_change` for `superseded`.

All timestamps use ISO 8601 **including timezone**. Reviewer identifiers are pseudonyms; do not attach unnecessary personal information or API keys. URLs are evidence references only and are **not fetched** by this CLI.

## Commands

From `labs/core`:

```bash
# Step 1: review completeness and conflicts without accessing the network
python scripts/intake_human_reviews.py \
  --candidates data/reviews_private/candidates.jsonl \
  --ballots data/reviews_private/ballots.jsonl \
  --adjudications data/reviews_private/adjudications.jsonl \
  --asof 2026-11-01T00:00:00+03:00

# Step 2: operator-reviewed export, ONLY if registered research use
# is approved and all legal local snapshots exist with the correct SHA-256
python scripts/intake_human_reviews.py \
  --candidates data/reviews_private/candidates.jsonl \
  --ballots data/reviews_private/ballots.jsonl \
  --adjudications data/reviews_private/adjudications.jsonl \
  --asof 2026-11-01T00:00:00+03:00 \
  --snapshot-dir data/source_snapshots_private \
  --output data/reviews_private/labels-20261101.jsonl

# Step 3: calibrate only after sufficient dated labels exist;
# pre-register train/calibration/test windows before examining holdout results
python scripts/calibrate_source_confidence.py \
  --input data/reviews_private/labels-20261101.jsonl \
  --train-end 2026-12-01T00:00:00+03:00 \
  --calibration-end 2027-01-01T00:00:00+03:00 \
  --evaluation-asof 2027-02-01T00:00:00+03:00
```

`--output` only writes new `.jsonl` files below ignored `labs/core/data/reviews_private/`, with exclusive creation and restrictive filesystem permissions. Repeat runs must use a new filename; an earlier decision archive cannot be silently overwritten.

## What this cannot establish

- Publicly accessible event pages are **not** necessarily authorized for commercial reuse.
- The algorithm checks **bytes integrity**, source permission records and field review quorum; it cannot authenticate an organization or check that a reviewer really verified the claim. Third-party rights still require legal/operator review.
- This module does not create real Istanbul calibration data. Unit tests simulate human ballots on fabricated claims.
- A source-reliability estimate is **not** a probability that an event is good, popular, available, still running or attended.
- Test-calibrated risk bounds are not guaranteed to hold for new sources or under distribution drift. Do not use a research threshold as a live product cutoff.
