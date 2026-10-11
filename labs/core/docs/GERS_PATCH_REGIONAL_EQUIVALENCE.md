# KEP-DATA-016: Regional GERS cross-patch equivalence

Research-only continuation of DATA-013/014/015; Issue #22, PR #33, ADR-0022.

## Preregistered question

DATA-014 observed 64 pairs of matching Places changelog footers, object sizes and ETags between the September 2026 .0 and .1 release paths. This is NOT full object equality or proof of which predecessor was used to generate either changelog.

DATA-015 read the two geographically selected added/removed Parquet groups in September .0 for the frozen Beşiktaş and Karaköy pilot boxes. Does the same regional added/removed projection from .1 contain identical (change_type, ID, projected fields) tuples? Pre-register the same bounding boxes and 4,872 previously pinned union IDs, 16 MiB source HTTP response body allowance, 12 MiB maximum range, 128 HTTP range requests, pinned Arrow 21.0.0 for separately authorized manual capture only, no redirects or automatic retries.

## Method and safety

The offline patch-pair planner reuses DATA-014's SHA-pinned original footer manifest. It selects precisely two immutable DATA-015 .0 membership groups, then checks exact matching .1 source keys, size, ETag, footer hashes and row-group metadata. DATA-015's RemoteRanges defaults to .0 as before. The .1 option exists only through an explicit allowlisted research caller.

The separately authorized source job decodes just the corresponding .1 groups, validates GERS row format and bbox overlap, then hashes the sorted canonical set of (change_type, UUID, row SHA-256). It emits an aggregate receipt with no raw IDs, contact information, reviewer labels, seeds or user data. The original DATA-015 aggregate receipt is loaded only after its exact SHA-256 check. Identical regional fingerprints mean equality of this limited captured projection under the same normalization, NOT full Parquet file equality, authenticated generation lineage, or independence of two sources.

## Real observations (October 11, 2026)

The explicitly scoped Actions research capture completed successfully. The returned original JSON was preserved and its inner SHA-256 compared against the pinned Git result. It did NOT redownload August Places.

| Real source observation | September .0, DATA-015 | September .1, DATA-016 |
| --- | ---: | ---: |
| Source rows scanned in selected membership groups | 207,733 | 207,733 |
| Regional added | 218 | 218 |
| Regional removed | 67 | 67 |
| Regional unique IDs | 285 | 285 |
| Canonical regional fingerprint SHA-256 | 524aeb660c7be71ddcd4fcd67f54c0c9af5bc15828ffe6208a85f81991d204c3 | Identical |
| Source response body bytes | 8,022,067 | 8,022,067 |
| HTTP range requests | 14 | 14 |

The .1 acquisition took 5.293186 seconds with an upper bound of 16,777,216 source body bytes. Header/TLS bytes, optional dependency installation and runner networking are not included in that amount. Recorded acquisition outer Actions artifact ZIP SHA-256: 82a6dc93283e5e3c01feb68cd3a3cc66da69506d41438b576a236cf6df98274f. Exact inner canonical JSON SHA-256: a1bfed37f2fa0f83bbd3bf395297cbd01f4a47e054c25b767db37ccf3cf2ea64. Previous .0 source receipt SHA-256: 8796914fb07117ddd5551c7480def866d17e8e7c8b04df8ed42af52d79598a10. Checksums are reproducible byte-integrity evidence, not independent publisher authentication.

## Scientific boundaries

- The September .1 patch release note specifically names base and building_parts UUID fixes, not Places. This supports a re-publication hypothesis, NOT an attestation of changelog build comparison baseline.
- The two reads are from the SAME Overture source root and are NOT independent validation votes.
- Only the two selected added/removed regional row groups were read. Data_changed/unchanged and other spatial row groups were not decoded here.
- DATA-014's 1,236 region-excluded groups cannot be ruled out by ID, and full 4,872-ID coverage remains FALSE.
- Full object SHA equality, publisher-certified predecessor, official membership agreement, human-ground-truth business openings/closures, and measurable consumer accuracy remain unknown. All relevant truth metrics remain null.
- Neither 218/67 official regional events nor 222/69 local snapshot membership changes are real shop openings/closures. Do not compute 218/222 or 67/69 as global agreement.

## Reproduction and rollback

From labs/core, without internet, credentials, models or Arrow:

    python scripts/review_gers_patch.py --check
    python -m unittest discover -s tests -v

Optional new source capture requires --fetch --research-confirmation PATCH_REGIONAL_EQUIVALENCE_16MIB --output NEW_DIRECTORY with the optional pinned Arrow dependency. This is never a default CI action. The temporary push-triggered source workbench was removed before merge. Ordinary Python 3.11/3.13 CI runs offline.

Rollback: revert the DATA-016 pair module, source/review CLIs, three new test files, pinned aggregate receipt, ADR/protocol and small explicit .1 reader option and offline CI gate. Preserve the August Places ZIP, DATA-013/014 artifacts and original DATA-015 report. No production, DB, consumer or push migration.

## Authoritative references

- September patch scope: https://docs.overturemaps.org/blog/2026/09/23/release-notes/
- Changelog contract: https://docs.overturemaps.org/gers/changelog/
- ID stability: https://docs.overturemaps.org/gers/stability/
- Data rights/attribution: https://docs.overturemaps.org/attribution/
- Data retention: https://docs.overturemaps.org/release-calendar/

NEXT: obtain publisher-controlled changelog generator lineage, then separately preregister a cost-controlled index-aware complete-ID experiment. Issue #22 remains open.
