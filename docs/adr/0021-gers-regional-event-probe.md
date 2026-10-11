# ADR-0021: bounded regional GERS event observation without full-ID membership claims

Date: 2026-10-11. Status: proposed, DATA-015. Relates to Issue #22, follows ADR-0019 and ADR-0020.

## Context

DATA-014 preserved 128 actual GERS Places changelog footers, 1,244 row groups and a SHA-pinned metadata cost study. ID min/max statistics cannot eliminate any group; only 8 across two paths intersect the original two tiny Istanbul boxes. The cheap geographic query is NOT a complete ID-union scan. An additional ambiguity is that both September patch paths share 64 identical footer/ETag/length metadata pairs.

Overture's official 2026-09-23 release note names base and building_parts ID corrections for `.1`, not Places, but does not certify the changelog generator comparison baseline.

## Decision

1. Read only `added`/`removed` candidate row groups of the September `.0` changelog under a new explicit 16 MiB public-source application-body budget, never as a default CI job. Prioritize safely measurable, scoped event presence over unbounded global ID access.
2. Verify exact pinned metadata SHA, selected original S3 object path/ETag, byte ranges and response identity. No automatic retries/redirects or budget escalation. Reject any incomplete source read.
3. Persist only aggregates, byte/time measurements and cryptographic row fingerprint; never consumer status, private reviewer data or individual records.
4. Never treat a region-bounded changelog read as a complete record-ID lineage. Never sum `.0` and `.1` as independent adjacent transitions without publisher-controlled baseline authentication. Never promote an official data event to a physical business opening or closure.
5. Reproduce module invariants offline with synthetic/mocked fixtures and verify immutable real metadata separately, using Python 3.11/3.13 CI. Require a separate explicit manual acquisition and record failure honestly.

## Acceptance and rollback

Accept software/metadata gates once regression suite and GitHub CI pass, even if network capture fails: in that case declare the event-data portion **incomplete** rather than fabricate records. Only a completed bounded capture can support numerical regional event counts. The complete 4,872-ID official membership agreement, independent business truth and patch changelog construction baseline remain separately open.

Rollback removes DATA-015 code, three tests, research protocol, optional results and offline CI additions without changing DATA-014 footers, historical Places archives, data publication or users.
