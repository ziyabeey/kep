# ADR-0023: Reject imagined Parquet index acceleration on pinned GERS changelogs

2026-10-11. Status: proposed research-only; accepted after full Python 3.11/3.13 CI and merge. Relates Issue #22. Prior decisions ADR-0019 to ADR-0022 remain unchanged.

## Problem

DATA-014's real source metadata showed that min/max ID statistics could not eliminate any of 1,244 GERS row groups. DATA-016 verified equal regional added/removed event projections across two September paths, but no certified comparison ancestor or full source identity. Before attempting full 4,872-ID tracking with low source I/O cost, we must check whether actual archived Parquet pages expose Bloom filters or page indexes.

## Decision

1. Inspect only the **original** already SHA-pinned DATA-014 footer bytes. Never re-download August or September Places or GERS Parquet source data for this experiment.
2. Implement an offline and bounds-checked Python stdlib Thrift Compact parser. Read ColumnChunk ColumnIndex and OffsetIndex pointers, ColumnMetaData Bloom filter pointers, physical column paths and RowGroup sorting declarations. Unknown, incomplete, inconsistent or corrupted metadata must stop the algorithm. Test synthetically encoded optional pointer fields and separately test the exact original real source archive.
3. Compare three clearly labelled ID-column chunk scanning plans: one release's membership-only rows, one release all change types, and both September paths all change types. These plans estimate compressed-chunk costs but **do not** measure actual transfer, represent universal lower bounds or authenticate the patch build predecessor.
4. Preserve a strict research-only/no-consumer decision. The old 16 MiB response-body cap is not enlarged by a planning calculation. Do not trigger automatic source fetching, paid calls, production writes or physical shop status inference.
5. Future alternatives: evaluate the Overture GERS registry as a *current-state* lookup possibility only, observing that it is mutable and unversioned. The registry/changelog remains one publisher root, not independent evidence. Future registry access requires a newly approved immutable, explicitly budgeted experiment.

## Real result

128 original Parquet footers represent 1,244 row groups, 7,464 column chunks and 1,244 ID chunks. The original Thrift fields contain zero ColumnIndex pointers, zero OffsetIndex pointers, zero Bloom-filter pointers and zero declared row-group sort lists. All chunks were assessed; this is not an inference from missing normalized metadata. A separate local Apache Thrift package interpreter agreed with the stdlib parser counts; CI uses no package.

Compressed ID-only whole-chunk sums, **unexecuted**: 203,288,875 bytes for one September .0 added/removed path (90 groups); 1,661,600,423 bytes for one September .0 four-kind path (622 groups); 3,323,200,846 bytes for both September paths (1,244 groups). None fits 16 MiB. The result rules out claiming *existing Parquet-provided page/Bloom indexes* as a proven low-I/O path, not all possible lookup optimizations.

Real-world shop openings, closures, event agreement, the patch changelog comparison baseline, external accuracy and cost savings are not measured. No consumer status may be assigned.

## Rollback

Revert only DATA-017 parser, offline replay CLI, synthetic/real regression tests, frozen aggregate report, research protocol, this ADR and added CI check. Retain DATA-013 through DATA-016, source archives, event receipts and user-facing production unchanged.

## Primary documents

Apache Parquet page index: https://parquet.apache.org/docs/file-format/pageindex/

Apache Parquet Bloom filters: https://parquet.apache.org/docs/file-format/bloomfilter/

Parquet Compact Thrift field contract: https://github.com/apache/parquet-format/blob/master/src/main/thrift/parquet.thrift

Overture registry nonversioned: https://docs.overturemaps.org/gers/registry/

Overture attribution: https://docs.overturemaps.org/attribution/

Detailed method: labs/core/docs/GERS_INDEX_CAPABILITY.md.
