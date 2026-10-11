# ADR-0016: Historical acquisition order and two-cell backfill integrity

**Decision:** Research-only; 2026-10-11. Builds on ADR-0014 and ADR-0015.

## Failure found

The original delta comparator required both the source-release dates and the local
acquisition timestamps to increase. But August 2026-08-19.0 may be downloaded on
October 11 after the pinned September 2026-09-23.1 sample was obtained on
October 10. This reverses acquisition order without reversing source-release
chronology. The first genuine historical capture could otherwise fail comparison.

A second possible error was allowing one pilot cell to have zero valid August
records while the other had records. The resulting diff could mistake a missing
regional query for a massive disappearance of Overture listings.

## Decision

1. Release publication chronology is strict (Aug → Sep). Default acquisition
   chronology remains strict. A narrowly scoped exception accepts later August
   acquisition only for exact Aug 19 operator research compared with the pinned
   Sep 23 archive, without weakening other comparators.
2. Each fixed Istanbul pilot cell must produce positive valid source row counts
   or the manual capture refuses to create a research bundle. Record explicit
   per-cell rows-read and valid-row counts. No partial dataset is accepted.
3. A successful manual capture computes a provisional offline diff. Validate
   canonical artifacts, preflight receipt / manifest / data hashes, both pilot
   cells, and exact releases. Report evidence_status must equal
   PROVISIONAL_INTERNAL_HASH_CHECK_NOT_INDEPENDENT_SOURCE_VERIFICATION.
   Never assert business openings or closures.
4. Keep normal CI entirely offline, with manual research-only acquisition
   and seven-day temporary artifact retention. Long-term storage or any
   consumer use needs separate rights and privacy review.

## Verification and counterexamples

- August acquired later than September: allowed only in exact pinned backfill.
- Reversed release order and reversed acquisition in unrelated runs: rejected.
- Beşiktaş valid, Karaköy empty, or vice versa: rejected before bundle write.
- Receipt mismatched to artifacts: provisional report rejected.
- Locally supplied fixture misrepresented as controlled public-S3 download:
  provisional report rejected.
- S3 object list or HEAD succeeds but regional query fails: no completed
  historical capture and no provisional research delta.
- Hash agreement alone cannot verify original upstream Parquet authenticity.

## Rollback

Revert the backfill comparison exception, per-cell validation, provisional
report and manual workflow step, plus their tests. Never substitute invented
historical rows when a real archive cannot be acquired.
