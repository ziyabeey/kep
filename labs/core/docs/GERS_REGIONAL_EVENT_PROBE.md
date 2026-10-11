# KEP-DATA-015: patch-source provenance and bounded regional event probe

Research only. Follows DATA-013 / DATA-014, ADR-0019 / ADR-0020, and Issue #22.

## Pre-registered question and scope

1. Can the **real** September `.0` `added` / `removed` GERS Parquet row groups intersecting Beşiktaş/Karaköy pilot boxes be decoded within **16 MiB of public-source application response bodies**?
2. How many official rows intersect those boxes, and how many use an ID already present in the **4,872-ID union** of the immutable August/September Places extracts?
3. Can we avoid incorrectly describing regionally visible changelog rows as the **complete** tracking history of all existing IDs?

This is a **geographic event observation**, not official full-ID membership reconciliation. The 1,236 excluded row groups still cannot be ruled out by ID, and the source does not publish a separate business opening/closure truth label.

From DATA-014's *real pinned metadata*, exactly four row groups across added/removed/data_changed/unchanged intersect the pilot boxes for `2026-09-23.0`; this experiment reads **added** and **removed only**, two candidate groups, 207,733 row-group records (before row-level bbox filtering), and **7,890,995 estimated compressed column bytes**. Even a successful read does not establish complete ID-union coverage.

## Publisher patch note: a scope statement, not a baseline certificate

The Overture 2026-09-23 release note explicitly says the `.1` patch corrects generated UUIDs in **base** and **building_parts**. It does *not* name Places as a patch target. Together with 64 matching `.0`/`.1` Places footer+ETag+size pairs, that supports a republished-Places hypothesis. It does not certify full byte equality, per-object published checksums, or the changelog's generation baseline. Do not add `.0` and `.1` as independent adjacent changes. The patch-lineage assessment remains `null` until explicit publication/generation evidence is available.

Sources:
- https://docs.overturemaps.org/blog/2026/09/23/release-notes/
- https://docs.overturemaps.org/gers/changelog/
- https://docs.overturemaps.org/gers/stability/
- https://docs.overturemaps.org/attribution/
- https://docs.overturemaps.org/getting-data/

## Limits and rights

Optional acquisition is explicit: `python scripts/probe_gers_region.py --fetch --research-confirmation REGIONAL_MEMBERSHIP_16MIB --output <fresh-path>`.

It requires the already pinned `footers.zip`, validates the original canonical manifest digest, and only opens preselected September `.0` public changelog object paths with `Range`, `If-Match`, exact ETag, Content-Length and Content-Range. It never automatically retries, follows redirects, or makes paid API calls. Hard limits are 16 MiB source response bodies, 12 MiB per response, 128 HTTP requests; failure leaves an incomplete research receipt and exits nonzero. Optional `pyarrow==21.0.0` is for explicit acquisition only, never offline CI. Source-body totals exclude HTTP/TLS overhead and optional dependency installation.

The public receipt contains only aggregate event counts, a reproducibility fingerprint, timing/byte costs, and abstention reasons. **No raw IDs, private human reviews, seeds, customer data, source secrets or predicted business labels** should be written to GitHub. Attribution to Overture and upstream providers remains necessary. No consumer use.

## Reproduction and tests

```bash
cd labs/core
python -m unittest tests.test_gers_probe_contracts tests.test_gers_probe_real tests.test_gers_probe_transport -v
python scripts/probe_gers_region.py
python scripts/review_gers_footer.py --check
python -m unittest discover -s tests -v
```

An offline replay of a published aggregate receipt is an **integrity check**, not an independent reconstruction from live Parquet bytes. Re-running optional bounded acquisition with exact object identity could compare new aggregate fingerprints, but versioned public objects may be retired. The real source snapshot archives are preserved.

## Safety and rollback

All development is isolated under `labs/core/`, documentation and an offline CI gate. A temporary opt-in source capture workflow must be removed before merge. To revert, remove only DATA-015 modules/tests/CLI/report and offline CI additions; retain the original Places and DATA-014 metadata archives. No production DB, consumer, Web Push or paid integration changes.
