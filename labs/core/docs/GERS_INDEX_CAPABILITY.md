# KEP-DATA-017: actual GERS Parquet index capability and ID budget audit

Research only; linked to Issue #22 and ADR-0023. This is a negative-capability experiment on the original real DATA-014 September changelog footer archive, **not** a new data/event capture.

## Method and provenance

- Reuse the SHA-pinned DATA-014 original 128 footer blobs in labs/core/data/real/gers_footer_2026-10-11/footers.zip. SHA-256: 1cefe054f5b61adfa2117d43e441626ab5355fed1096aa105b397d70f619bf9d.
- Verify the complete original manifest's canonical SHA and every original footer member SHA against its pinned metadata, including exact row-group counts and physical column paths.
- Decode Parquet Thrift Compact metadata with **only the Python standard library**. Inspect ColumnChunk fields 4-7 for OffsetIndex/ColumnIndex extents, ColumnMetaData fields 14/15 for Bloom filter offset/length, and RowGroup field 4 for a declared sort order. Field 10 (legacy index_page_offset) is NOT ColumnIndex.
- Run synthetic Compact protocol cases independently of real-data immutable archive tests. Fail closed on truncation, unknown types, malformed offset pairs, renamed columns and corrupt source. No internet, new footer acquisition, Arrow install, model or paid API.
- Source chain: original Overture Maps footers already captured 2026-10-11. This test is a **software interpretation of the same publisher source**, not independent publisher/physical business validation.

## Measured findings

| Archived original metadata | Observed |
| --- | ---: |
| Original GERS files | 128 |
| Row groups | 1,244 |
| Column chunks | 7,464 |
| ID column chunks | 1,244 |
| ColumnIndex / OffsetIndex pointers | **0 / 0** |
| Bloom pointers | **0** |
| Row groups declaring sort columns | **0** |

The same results came from a separate local interpreter using the Thrift Python library; ordinary CI needs no external Thrift package. No source event pages were read. The absence of optional indexing pointers is evidence that *these particular files* do not provide Parquet page-index or Bloom-filter acceleration for ID lookups. It does not rule out other algorithms or claim that a future release lacks indexes.

### Estimated ID-column chunk reads (not actual transfer)

| Proposed candidate scan | Row groups | ID-column compressed bytes | Fits previous 16 MiB source body budget? |
| --- | ---: | ---: | --- |
| One .0 changelog path, added + removed only | 90 | **203,288,875 bytes** | No |
| One .0 path, all four change types | 622 | **1,661,600,423 bytes** | No |
| Both .0 and .1 paths, all four change types | 1,244 | **3,323,200,846 bytes** | No |

Those estimates use exact stored column compressed-chunk sizes. They exclude range-request overhead, memory, decompression, other required columns, network retries and selective page-reading innovations. They are **not** universal lower bounds or measured query transfer. Reading both September paths would not make them two independent release transitions; DATA-016 proved only equal scoped regional event projections. The changelog build ancestry and full Parquet equality remain unverified.

The original 4,872 pilot IDs remain unchanged, digest 38b248b344cb66a87228c713e74e55ec5f24124f383a3e2c077fc11ddfc73804. Snapshot differences (222 locally added IDs, 69 missing) are not real business openings/closures or certified GERS event agreement. Every truth field remains null and user publishing remains disabled.

## Better next hypothesis: mutable GERS registry, not retroactive proof

Official registry docs say it supports the place type, stores id, first_seen, last_seen, last_changed, path and bbox, but there is **only one continuously updated registry; it is not versioned**. A **separately approved and budgeted** registry-layout metadata experiment could assess whether current registered IDs can be looked up more cheaply. It cannot recover historical patch changelog ancestry merely by querying the current registry. Registry and changelog share Overture as a source root, not independent witnesses.

## Reproduce offline

From labs/core, no extra dependencies:

```bash
python scripts/audit_gers_index.py --check
python -m unittest tests.test_gers_index_gates -v
python -m unittest discover -s tests -v
```

The stable aggregate report is frozen at reports/KEP_DATA_017_INDEX_AUDIT.json, checked by both the CLI and CI. Counts from raw Thrift metadata are linked to every source file by the prior original ZIP hash. The original August/September Places captures and all DATA-013/014/015/016 reports are unchanged.

## Sources and rights

- Parquet page index, optional metadata: https://parquet.apache.org/docs/file-format/pageindex/
- Parquet Bloom filter, optional metadata: https://parquet.apache.org/docs/file-format/bloomfilter/
- Parquet thrift field definitions: https://github.com/apache/parquet-format/blob/master/src/main/thrift/parquet.thrift
- Overture GERS mutable unversioned registry: https://docs.overturemaps.org/gers/registry/
- Overture changelog: https://docs.overturemaps.org/gers/changelog/
- Overture rights and attribution: https://docs.overturemaps.org/attribution/

No consumer release, production deployment, user data, Web Push, paid API, reviewer labels or private sample seeds were changed.
