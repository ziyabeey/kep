# ADR-0021: bounded regional GERS event observation without full-ID membership claims

Date: 2026-10-11. Status: proposed; research-only acceptance on merge, source evidence captured but full-ID reconciliation incomplete. Relates to Issue #22, follows ADR-0019 and ADR-0020.

## Context

DATA-014 preserved 128 actual GERS Places changelog footers, 1,244 row groups and a SHA-pinned metadata cost study. ID min/max statistics cannot eliminate any group; only 8 across two paths intersect the original two tiny Istanbul boxes. The cheap geographic query is NOT a complete ID-union scan. An additional ambiguity is that both September patch paths share 64 identical footer/ETag/length metadata pairs.

Overture's official 2026-09-23 release note names base and building_parts ID corrections for `.1`, not Places, but does not certify the changelog generator comparison baseline.

## Decision

1. Read only `added`/`removed` candidate row groups of the September `.0` changelog under a new explicit 16 MiB public-source application-body budget, never as a default CI job. Prioritize safely measurable, scoped event presence over unbounded global ID access.
2. Verify exact pinned metadata SHA, selected original S3 object path/ETag, byte ranges and response identity. No automatic retries/redirects or budget escalation. Reject any incomplete source read.
3. Persist only aggregates, byte/time measurements and cryptographic row fingerprint; never consumer status, private reviewer data or individual records.
4. Never treat a region-bounded changelog read as a complete record-ID lineage. Never sum `.0` and `.1` as independent adjacent transitions without publisher-controlled baseline authentication. Never promote an official data event to a physical business opening or closure.
5. Reproduce module invariants offline with synthetic/mocked fixtures and verify immutable real metadata separately, using Python 3.11/3.13 CI. Require a separate explicit manual acquisition and record failure honestly.

## Measured event data and immutable receipt

The fixed-budget `2026-09-23.0` public Places GERS bounded read yielded **218 added**, **67 removed**, 285 unique regional IDs, 207,733 scanned candidate rows, 14 range requests, 8,022,067 HTTP source response-body bytes, and 7.998247 seconds. The byte budget was 16 MiB; the 42.8 MB optional Arrow package download and HTTP/TLS headers are excluded. Original receipt SHA-256 `8796914fb07117ddd5551c7480def866d17e8e7c8b04df8ed42af52d79598a10` is frozen without raw record identifiers. Artifact outer ZIP digest `3bb653cee8d6d244c1278687d2a8895718c01b4e79d62102cedc16e1cb98a411` was checked against GitHub.

The source-read step finished; its initial reporting/commit gate failed on an overbroad ban on `id` appearing in **field names**, rejecting harmless scope metadata `complete_for_all_union_ids`. Preserve this as a failed workflow with a successful source step, then pin the original uploaded receipt separately. Another initial attempt stopped on a `size` / `object_bytes` adapter mismatch before source bytes. A regression test was written before the adapter fix. Do not rerun reads solely to repair reporting.

This is **not** a completed GERS membership reconciliation of 222/69 local changes: changelog patch baseline is unverified, geographic event observation does not recover movement outside bounded boxes, and no ground-truth business labels exist. Both `official_membership_agreement_fraction` and physical-event accuracy stay null. Publication remains disabled.

## Acceptance and rollback

Accept software/metadata gates once regression suite and GitHub CI pass, even if network capture fails: in that case declare the event-data portion **incomplete** rather than fabricate records. Only a completed bounded capture can support numerical regional event counts. The complete 4,872-ID official membership agreement, independent business truth and patch changelog construction baseline remain separately open.

Rollback removes DATA-015 code, three tests, research protocol, optional results and offline CI additions without changing DATA-014 footers, historical Places archives, data publication or users.
