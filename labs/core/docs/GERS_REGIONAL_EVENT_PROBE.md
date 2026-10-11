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

## Real bounded acquisition and source receipt (2026-10-11)

[Experimental source job 38153722714](https://github.com/ziyabeey/kep/actions/runs/38153722714) succeeded **at the source read** but its subsequent GitHub commit step failed because an overbroad key-name check mistakenly rejected the harmless `complete_for_all_union_ids` field. The exact successful JSON was preserved by `upload-artifact`; its outer ZIP SHA-256 matched GitHub's `3bb653cee8d6d244c1278687d2a8895718c01b4e79d62102cedc16e1cb98a411`. The inner canonical JSON SHA-256 is **`8796914fb07117ddd5551c7480def866d17e8e7c8b04df8ed42af52d79598a10`**. The receipt was pinned in Git without re-requesting source bytes. A failed post-read reporting gate is NOT a successful whole-workflow result.

Actual `2026-09-23.0` Places GERS `added` and `removed` row group scan: **207,733** source rows scanned; **218 added** and **67 removed**, **285 distinct regional IDs**, **285** also in the union of previously captured August/September local place IDs; no conflicting IDs and no duplicates in the captured bounded projection. Reading used **14 HTTP Range requests**, **8,022,067 application-response-body bytes**, **7.998247 seconds**, under the fixed **16 MiB**/128 requests cap. Column chunk metadata predicted 7,890,995 compressed bytes. The 8MB is measured read traffic, **not** all network traffic (Arrow install and response headers excluded). No raw IDs or contact data were published. These are *publisher changelog rows* for bounded geometry, NOT verified independent business events or complete all-ID history.

Local snapshot diff remains **222 locally newly-listed IDs / 69 locally no-longer-listed IDs**. The observed 218/67 GERS rows do **not** establish 218/222 or 67/69 official membership agreement: patch predecessor unverified, bbox membership differs, and 1,236 excluded row groups cannot be ruled out by ID. The already stored `official_membership_agreement_fraction` remains `null`, not a computed rate. Neither the metadata read nor the 285 observed rows establishes physical openings/closures. This experiment is research-only.

Source capture preceding this success initially stopped at zero body bytes on `'size'` / `object_bytes` field mismatch. A synthetic-plus-pinned-metadata regression was introduced first and the minimal source adapter fixed; no budget increase. Retain both failed-run and successful-read audit records.

The committed `reports/KEP_DATA_015_REGIONAL_EVENTS.json` is **aggregate-only and byte-pinned**; `python scripts/review_gers_region_events.py --check` checks its digest and guard invariants fully offline, but does NOT re-download or independently reconstruct source rows. Any new GERS event reading is a separately approved study. The temporary push-triggered source workbench is removed before PR merge.

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
