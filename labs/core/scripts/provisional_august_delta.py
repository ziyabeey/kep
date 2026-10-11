"""Offline PROVISIONAL August->September source-delta for a completed manual capture.

Uses internally consistent local hashes, NOT independent upstream attestation.
Never calls S3/STAC, publishes consumer data, or estimates business closures.
Only the original research operator can review/retain the resulting artifact.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kepcore.overture_august import AUGUST, compare_august_september
from kepcore.overture_historical_probe import PINNED_PREFIX
from kepcore.overture_places import PILOT, canonical

MAX_RECEIPT_BYTES = 20_000
MAX_MANIFEST_BYTES = 20_000
MAX_REPORT_BYTES = 8_000_000


def _read_json(path: Path, limit: int) -> tuple[bytes, dict]:
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= limit:
        raise ValueError('Missing, unsafe or oversized local research evidence')
    raw = path.read_bytes()
    obj = json.loads(raw)
    if not isinstance(obj, dict) or canonical(obj) != raw:
        raise ValueError('Research evidence is not canonical JSON')
    return raw, obj


def build_provisional_report(root: Path) -> dict:
    """Require both data files, a bound preflight receipt, and two nonempty cells."""
    manifest_bytes, manifest = _read_json(root/'manifest.json', MAX_MANIFEST_BYTES)
    _, receipt = _read_json(root/'historical_public_preflight.json', MAX_RECEIPT_BYTES)
    normalized = root/'places_minimal.json'
    if normalized.is_symlink() or not normalized.is_file():
        raise ValueError('Missing or unsafe August normalized file')
    if (receipt.get('study') != 'KEP-DATA-008'
        or receipt.get('exact_release') != AUGUST
        or receipt.get('s3_prefix') != PINNED_PREFIX
        or receipt.get('one_parquet_head_verified') is not True
        or receipt.get('all_release_parts_verified') is not False
        or receipt.get('regional_istanbul_download_completed') is not False
        or receipt.get('consumer_publish_approved') is not False):
        raise ValueError('Unverified or inconsistent historical preflight receipt')
    if (receipt.get('manifest_sha256') != sha256(manifest_bytes).hexdigest()
        or receipt.get('normalized_sha256') != manifest.get('normalized_sha256')
        or manifest.get('source_release') != AUGUST
        or manifest.get('acquisition',{}).get('method') != 'historical_duckdb_public_s3'):
        raise ValueError('Historical receipt / manifest / pinned acquisition mismatch')
    # Record counts have to be source-derived, not assumed from the September pilot.
    by_cell = manifest.get('audit',{}).get('per_cell')
    if not isinstance(by_cell,dict) or set(by_cell)!=set(PILOT):
        raise ValueError('Missing exact historical pilot cell coverage')
    if any(not isinstance(c,dict) or type(c.get('valid_rows')) is not int
           or c['valid_rows']<=0 for c in by_cell.values()):
        raise ValueError('Historical research cell is empty or not measured')
    result = compare_august_september(root,
        expected_sha256=receipt['normalized_sha256'],
        expected_manifest_sha256=receipt['manifest_sha256'],
        expected_stac_sha256=manifest['stac_catalog_sha256'],
        expected_observed_at=manifest['acquisition']['observed_at'])
    if (result['old_release']!=AUGUST or result['new_release']!='2026-09-23.1'
        or result['old_population_n']<=0 or result['new_population_n']<=0
        or result['synthetic_second_release'] is not False
        or result['consumer_publish'] is not False):
        raise ValueError('Not a bounded, non-publishing source-only release comparison')
    result['evidence_status'] = 'PROVISIONAL_INTERNAL_HASH_CHECK_NOT_INDEPENDENT_SOURCE_VERIFICATION'
    result['historical_cell_counts'] = by_cell
    result['historical_preflight_scope'] = 'ONE_REMOTE_PARQUET_OBJECT_HEAD_NOT_ALL_PARTS'
    result['regional_extraction_artifact_checked'] = True
    result['upstream_raw_parquet_preserved'] = False
    result['source_record_delta_not_business_open_close'] = True
    return result


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--august-dir',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    report=canonical(build_provisional_report(args.august_dir))
    if len(report)>MAX_REPORT_BYTES:
        raise ValueError('Provisional report exceeds safety size cap')
    # Exclusive output: no accidental replacement of a reviewed report.
    with args.output.open('xb') as f:
        f.write(report)
    print(json.dumps({
        'report':str(args.output),
        'report_sha256':sha256(report).hexdigest(),
        'source_only':True,
        'old_population_n':json.loads(report)['old_population_n'],
        'new_population_n':json.loads(report)['new_population_n'],
    },ensure_ascii=False,sort_keys=True))


if __name__=='__main__':
    main()
