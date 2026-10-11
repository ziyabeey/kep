# KEP-DATA-013: source reconciliation and release compatibility

Research only. This implementation is not a business-opening/closure detector.
Related work: [Issue #22](https://github.com/ziyabeey/kep/issues/22), [PR #30](https://github.com/ziyabeey/kep/pull/30), [ADR-0019](../../../docs/adr/0019-gers-source-reconciliation.md).

## Reproduce without network or credentials

```bash
cd labs/core
python -m unittest discover -s tests -v
python scripts/reconcile_gers_releases.py --check
python scripts/reconcile_gers_releases.py --check --benchmark
```

The default CLI only reads existing Git-pinned files. `reports/KEP_DATA_013_REAL_RESULTS.json` contains the reproducible aggregate result and one local performance measurement. `--check` compares every stable result, excluding runtime-dependent timings. Python 3.11 and 3.13 CI also preserve aggregate performance JSON artifacts, never individual review queues.

An optional targeted queue can be written only to a **new** file under an existing, non-symlinked `labs/core/.local/` directory, with mode 0600:

```bash
mkdir -p .local
python scripts/reconcile_gers_releases.py --private-queue-output .local/data013-queue.json
```

Do not commit this queue, reviewer material, or private audit seeds. It is not a randomized error-rate sample.

## What is actually supported

`kepcore/gers_reconciliation.py` reuses `ResearchSnapshot` and `compare_snapshots` from `overture_delta.py`, `inspect_releases` from `overture_change_triage.py`, and the pinned ZIP loader plus independently implemented record comparator from `overture_archive_artifact.py`. Agreement between these implementations is a software consistency check on the **same source records**, not a second independent truth observation.

The module validates source integrity, maintains exclusive source/schema/metadata routing, creates bounded identity-review hypotheses without assuming equivalent categories across schemas, and preserves contradictory official observations. Identical reposts do not create independent evidence. A strict, checksum-bound event-envelope contract is exercised with explicitly synthetic fixtures. The public projection excludes identifiers, individual queues and unknown top-level fields.

**The real pair cannot currently enter direct official-event reconciliation.** Pinned STAC evidence requires an intermediate release, and the bounded live capture did not yield a completed event batch. An operator's `reviewed` flag cannot override that release-chain guard. A future verified, per-hop chain reconciler is still required; its events must not be invented or composed merely by unioning changed-column lists, because intermediate changes can reverse.

## Reproduced real source counts

| Measurement | Count |
|---|---:|
| August `2026-08-19.0`, raw Places v1.18 | 4,650 |
| September `2026-09-23.1`, raw Places v2.0 | 4,803 |
| Shared source IDs | 4,581 |
| Newly listed in the bounded September extract | 222 |
| No longer listed in that extract | 69 |
| Shared IDs with property/geometry/source revisions | 198 |
| Classification-only cross-schema revisions | 36 |
| Other property-revision cases | 162 |
| Confidence-only revisions | 3,337 |
| Any confidence revision, including overlaps | 3,513 |
| Absolute confidence change greater than 0.05 | 256 |
| Locally unchanged shared IDs | 1,046 |

Beşiktaş sampling cell: 1,806 to 1,872 records, 97 added IDs and 31 removed IDs. Karaköy sampling cell: 2,844 to 2,931, 125 added and 38 removed. These are the same small frozen rectangles, not district-wide inventories.

The exclusive routing has 291 source-membership cases, 162 property cases, 36 technical classification cases, 3,337 metadata-only cases and 1,046 unchanged cases. The full targeted queue has 489 cases, of which 36 are technical rather than requests to verify physical business change. Four nearby exact-name candidate **pairs** are retained for identity review versus three in the existing comparator. The extra pair arises after removing category equality as a prerequisite across incompatible schemas. None is an authenticated replacement ID or an automatic merge; recall and precision are unknown.

## Actual official-source access, including the unsuccessful experiment

The read-only metadata probe [run 38142040577](https://github.com/ziyabeey/kep/actions/runs/38142040577) successfully fetched the four official documentation pages, STAC and the September `.1` S3 partition listings. Listing objects does not validate event rows.

The subsequent explicitly triggered capture [run 38142687481](https://github.com/ziyabeey/kep/actions/runs/38142687481) verified this STAC predecessor chain:

```text
2026-08-19.0 -> 2026-09-23.0 -> 2026-09-23.1
```

It listed 64 Parquet objects per target release across the four change types, then queried the bounded regions and exact local ID union through a loopback proxy with a 256 MiB body-transfer budget. The run recorded **268,294,121 body bytes**, 203 HTTP requests, and `INCOMPLETE_CAPTURE`, with **zero completed event rows**. It ended with HTTP 503 from the bounded proxy near the byte limit. The exact internal proxy rejection detail was not retained, so it is not reported as a more precise transport diagnosis.

The experimental Actions workbench was green because the initial capture command serialized its failure receipt and exited normally. That is not a scientific success. The retained manual CLI now exits nonzero on an incomplete capture, protected by a regression test. The temporary push-triggered workflow is removed before merge. No further download or budget increase was performed.

Exact captured catalogs and the original compressed failure receipt are preserved in `data/real/gers_access_2026-10-11/`, checked against independent code-pinned SHA-256 values. The failed capture's original Actions ZIP digest is `0151e6d502c7a5d9c566fcfa498b72e55463ec44c31310a9197be2739124fb5a`. SHA-256 here proves consistency with captured bytes, not a publisher's cryptographic signature. No complete raw Parquet file or actual changelog event extract was preserved.

Therefore the 222/69 local differences have **not** been validated against official global changelog events. Official membership agreement is `null`, not zero or 100 percent. No probability of business existence is estimated.

## Official semantics and minimized-data limits

The [official changelog](https://docs.overturemaps.org/gers/changelog/) describes adjacent-release source membership (`added`, `removed`), compared-property changes (`data_changed`) and `unchanged`. It excludes `confidence` and `sources`; changed-column names are top-level names. Its global membership events do not establish physical opening/closure, and it does not supply explicit split/merge linkage. The [GERS stability documentation](https://docs.overturemaps.org/gers/stability/) describes identifier changes and matching limitations.

The old `categories` and new `taxonomy`/`basic_category` are not assumed semantically interchangeable. Our minimal archive retains only a primary name and first address, so absence of local changes cannot establish that full upstream `names` or `addresses` structures were unchanged. Unretained columns such as websites remain unobservable. Contradictions are kept without choosing a source winner. A local entry/exit may reflect spatial coverage or capture differences; it is not automatically a global added/removed event.

Access and provider-license references: [getting data](https://docs.overturemaps.org/getting-data/), [attribution](https://docs.overturemaps.org/attribution/). Existing provider/attribution fields are retained in the original archives; `DATA_LICENSES.md` still applies. No personal reviewer records or production/customer data are involved.

## Three methods and what the result does not prove

The intentionally unsafe naive baseline treats each of the 69 missing IDs as a closure. The existing deterministic method and this reconciliation layer both withhold that unsupported conclusion. It is **not known** how many of the 69 would actually be false. The optional expanded naive opening/closure hypothesis has 291 unsupported assertions, but that is a different definition from the removal-only baseline.

The new contribution is the checked intermediate-release boundary, evidence/coverage abstention, conflict preservation and deduplication, incomplete-capture failure signaling, and category-independent identity-review candidates. Source IDs and existing scientific counts do not change. Existing DATA-011 already isolated confidence and schema drift; this work does not claim those as newly discovered protections.

A separate review-policy ablation compares sending all 3,826 changed/membership cases to one undifferentiated queue versus 453 source-membership/property cases, 36 technical cases and 3,337 metadata-only cases. That is a routing-policy counter, **not** a measured number of unnecessary human inspections or a demonstrated monetary saving.

The committed local Python 3.13 measurement uses three warm untraced timings and one separate tracemalloc run per method, with already loaded inputs. Median times were approximately 0.0041 s naive, 0.3841 s deterministic, 1.0692 s reconciliation. Peak internal Python allocations were 426,688, 24,952,797 and 24,952,957 bytes respectively. These are not total RSS, production latencies or a quality ranking. CI machines will differ. No competitor advantage is claimed.

## Remaining experiment

Design a separately budgeted footer/row-group access study before retrying full changelog extraction. Establish pruning effectiveness and expected body bytes first, then capture and pin both verified transitions. Missing spatial-query rows must stay unknown rather than being treated as `unchanged`. Keep per-hop events, duplicates and contradictions so reversal/restoration paths are observable. Only after that can source-event agreement be measured. Independent dated human review remains a separate requirement for real business events and error rates.
