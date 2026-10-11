# KEP-DATA-014: measured footer access cost and patch-baseline caution

Research only. Related: [PR #31](https://github.com/ziyabeey/kep/pull/31), [Issue #22](https://github.com/ziyabeey/kep/issues/22), [ADR-0020](../../../docs/adr/0020-gers-footer-cost-study.md).

## Reproduce without network, Arrow or credentials

```bash
cd labs/core
python scripts/review_gers_footer.py --check
python -m unittest tests.test_gers_access_cost tests.test_gers_footer_transport tests.test_gers_footer_real -v
python -m unittest discover -s tests -v
```

The check compares the full original cost result/capture receipt with `reports/KEP_DATA_014_FOOTER_RESULTS.json` and the newly separated patch-alias diagnostic with `reports/KEP_DATA_014_ALIAS_REVIEW.json`. It never downloads the August Places archive or any GERS data page.

## Preregistered and executed experiment

PR #31 specified a **16 MiB source response-body allowance**, 2 MiB maximum footer, 512 requests, no redirects/retries, and metadata-only access. Source access was explicitly triggered on the isolated research branch. The temporary push-triggered acquisition/authoring workflow is removed before merge; the optional capture CLI still requires `--fetch --research-confirmation METADATA_ONLY_16MIB --output <fresh-directory>`.

The first workflow attempt had a YAML parse error and executed no acquisition. The first actual source attempt, [38149968929](https://github.com/ziyabeey/kep/actions/runs/38149968929), stopped on response-length validation after one listing request and zero returned body bytes. The exact receipt is retained. Thirteen mocked regression cases were added; three reproduced the old transport defects. Lengthless listing bodies are now read only up to the pre-reserved cap, whereas range bodies still require exact length and identity. Unexpected status or content encoding stops before reading. No budget was raised.

The successful capture [38150426830](https://github.com/ziyabeey/kep/actions/runs/38150426830) read the 128 actual objects' four-byte headers, eight-byte trailers and bounded footers. All eight release/change-type partitions were listed completely. The experiment used optional `pyarrow==21.0.0` solely to decode footer metadata. Ordinary CI uses only the standard library.

| Actual acquisition measurement | Result |
| --- | ---: |
| S3 objects, two release paths combined | 128 |
| Row groups in their metadata | 1,244 |
| Application response body bytes read | 1,072,094 |
| Conservatively reserved body allowance | 2,063,202 |
| Hard body allowance | 16,777,216 |
| HTTP requests, no retries | 392 |
| Acquisition elapsed seconds | 17.202505 |
| Event rows / data page bytes read | 0 / 0 |

Requests comprise 8 listings plus 3 ranges per object. The budget does **not** include HTTP/TLS headers or software installation. The successful job separately downloaded a 42.8 MB Arrow wheel; no claim of 1.07 MB total job networking is made. Reserved allowance is conservative and is not a measurement of actual body transfer.

## Measured metadata, estimated future query cost

The same immutable August/September samples supply 4,872 union IDs and the exact two frozen sampling rectangles. No new source ID is manufactured. All six stored column chunks are included in the estimate: ID, four bbox leaves, and columns_changed.

| Read plan | Candidate groups | Compressed chunk bytes | Complete scope for arbitrary movement of the tracked IDs? |
| --- | ---: | ---: | --- |
| No pruning | 1,244 | 5,789,190,970 | Yes, as a plan only |
| Exact ID-union min/max pruning | 1,244 | 5,789,190,970 | Yes, as a plan only |
| Geographic bbox pruning | 8 | 35,805,264 | **No** |
| Bbox AND ID pruning | 8 | 35,805,264 | **No** |

`complete_for_id_union` describes the **scope of a hypothetical plan**, not a completed scan. No ID was matched and no official membership agreement was calculated. Unknown, null, nonfinite or unsupported-order statistics keep the row group rather than hiding it. The real ID ranges overlap the query union in every group, so ID min/max statistics save **zero groups**. Bbox pruning excludes 1,236 groups that still cannot be excluded by ID. This is not proof that those groups contain a desired ID, but dropping them would not be a complete ID-tracking query.

These are sums of compressed column chunks, not measured HTTP query traffic, exact engine memory, or a lower bound on every possible algorithm. Page indexes, bloom filters, batching, selective second-stage columns, readahead, caches and retries can change actual costs. Reading only candidate ID chunks would total 3,323,200,846 bytes for the ID plan or 19,065,862 for the regional plan. Neither is a measured execution. Per-release reads are counted separately; there is no cross-release cache deduplication in these figures.

## Unexpected finding: patch metadata is duplicated

Across the two September release paths, all 128 objects form **64 cross-release pairs with equal footer SHA-256, ETag, object size and change-type partition**. Only 64 unique footer hashes exist. This supports an alias/republication hypothesis, but we did not hash full Parquet objects or read their event rows. Therefore full event-content equality is unverified.

Most importantly, the DATA-013 STAC chain `August -> September .0 -> September .1` describes release navigation; it does **not independently authenticate the comparison baseline used to build each changelog**. The generic documentation describes previous-release changes, but duplicated patch metadata is reason to verify how patch changelogs are generated before composing them as distinct adjacent transitions. DATA-013 already refused the direct unverified comparison; it is left unchanged. The new diagnostic is `PATCH_BASELINE_REQUIRES_PUBLISHER_VERIFICATION`, with no numerical official agreement.

## Evidence, performance and scientific boundaries

The original successful capture archive is Git-pinned; its exact digest is `1cefe054f5b61adfa2117d43e441626ab5355fed1096aa105b397d70f619bf9d`. The downloaded outer Actions ZIP was independently checked against GitHub's digest, and the original August ZIP remains `cb9ee86c128b4839a00722e1b192f460691c0f33e358f0b0b9ae458ea403ef05`. Hash checking means local byte consistency, not independent publisher authentication. Raw footer bytes permit a future independent decoder check; the ordinary replay validates and uses the captured normalized metadata, not a second Parquet implementation.

The sum of metadata row counts is 165,169,686 across both release paths, **not that many unique places or independent events**. The new 64-pair observation makes this distinction especially important. No source becomes a second independent witness by being republished.

Local Python 3.13.5 end-to-end review, including archive loading, measured three untraced timings of 0.483216, 0.532046 and 0.483538 seconds. A separate tracemalloc run peaked at 63,296,491 Python allocation bytes. This is not total RSS, a production SLA, or a cross-machine speed claim. The original source capture took 17.202505 seconds, a different operation.

Baseline was 664 tests. DATA-014 adds 57 cases: 32 synthetic cost/range contracts, 13 mocked transport/CLI cases and 12 separate pinned-real metadata tests. Full Python 3.11/3.13 CI and exact reference replay are required before merge. The tests do not prove business existence, opening/closure accuracy, source timeliness, actually saved money, or competitor superiority.

## Next experiment

First establish the actual comparison baseline of September patch changelogs using publisher-controlled release/generation evidence. Then design a read-only bounded regional event capture from the eight identified candidate row groups, with ID gaps explicitly unknown. A separate index-aware or ID-first study is needed before claiming global coverage of all 4,872 tracked IDs. A 35.8 MB estimate is not authorization to silently enlarge this metadata experiment's 16 MiB body budget. No new event download was started here.

## Primary sources and rights

- Overture changelog semantics, schema and exclusions: https://docs.overturemaps.org/gers/changelog/
- GERS identifier limitations: https://docs.overturemaps.org/gers/stability/
- Public access guidance: https://docs.overturemaps.org/getting-data/
- Overture attribution and provider licenses: https://docs.overturemaps.org/attribution/
- Parquet footer layout: https://parquet.apache.org/docs/file-format/
- Arrow metadata reader: https://arrow.apache.org/docs/python/generated/pyarrow.parquet.read_metadata.html

No consumer, Web Push, production, customer, paid API, reviewer or private sampling-seed state was changed. Targeted review and random human audit remain separate.
