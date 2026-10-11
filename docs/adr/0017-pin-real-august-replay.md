# ADR-0017: Freeze a reproducible real August-to-September source-diff receipt

Status: Research only. Date: 2026-10-11.

The August 2026 Overture release was acquired by manual GitHub Actions run 38121005943, creating historical ZIP artifact 11695042455. Its 4,650 POI source records have been compared with the already pinned September 4,803 records. The historical artifact expires under seven-day retention.

Decision: pin the original ZIP SHA and its four member SHA hashes, commit an independent offline replay tool and a machine-readable findings receipt, and reject modified or substituted archives. Keep the full original research ZIP outside Git (not included in this PR); GitHub CI does not use external network or API secrets.

Research interpretation: 4,581 retained Overture IDs, 222 new listed IDs, 69 no longer listed. There were 3,337 confidence-only changes among retained IDs. This is NOT a measurement of physical business openings, closures, moves or verified hours. v1.18 and v2 categories require reviewed semantic mapping. Historical August was downloaded after September, so release chronology and capture chronology differ.

Evidence limits: GitHub artifact integrity is not independent signature of original S3 partitions. No independent field checks or raw historical global Parquet saved. No consumer publishing or automated notification. Keep Issue #22 open for official GERS changelog and physical human checks.

Rollback: revert these standalone source-only replay files and receipt; no production migrations or customer data are affected.
