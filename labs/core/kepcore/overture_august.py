"""KEP-DATA-007: 2026-08-19.0 schema-v1.18 preservation and safe comparison.

This module never fetches the network, authenticates remote S3 bytes, merges
GERS identities, or verifies real-world business status. Only explicitly
pinned August source observations may be compared against September.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json

from .calibration import aware
from .overture_places import (PILOT, MAX_INPUT_BYTES, MAX_FEATURES, canonical,
                              normalize_feature, potential_duplicates)
from .overture_audit import _validated_record
from .overture_delta import (ResearchSnapshot, SCHEMA, compare_snapshots,
                             snapshot_from_frozen_archive)

AUGUST = '2026-08-19.0'
SCHEMA_AUGUST = 'Overture Places schema v1.18.0'
STAC_URL = 'https://stac.overturemaps.org/catalog.json'
STAC_CHILD = 'https://stac.overturemaps.org/2026-08-19.0/catalog.json'
S3_PREFIX = 's3://overturemaps-us-west-2/release/2026-08-19.0/theme=places/type=place/'
MAX_STAC_BYTES = 200_000
MAX_MANIFEST_BYTES = 20_000
MAX_NORMALIZED_BYTES = 16_000_000


def validate_august_stac(raw: bytes) -> dict:
    """STAC lists August, but a catalog entry alone cannot prove S3 retention."""
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_STAC_BYTES:
        raise ValueError('Missing or oversized STAC catalog')
    doc = json.loads(raw)
    if not isinstance(doc, dict) or doc.get('type') != 'Catalog':
        raise ValueError('Not an Overture release catalog')
    links = doc.get('links')
    if not isinstance(links, list) or not any(
        isinstance(link, dict) and link.get('rel') == 'child'
        and link.get('href') == STAC_CHILD for link in links
    ):
        raise ValueError('August release is not listed as an exact STAC child')
    return {'release': AUGUST, 'catalog_sha256': sha256(raw).hexdigest(),
            'listed_in_stac': True, 's3_objects_verified': False}


def normalize_august_feature(feature: dict, *, cell: str) -> tuple[dict, dict]:
    """Use only native v1.18 basic_category/taxonomy, NEVER map legacy categories.

    Overture changed taxonomy semantics between v1.18 and v2; guessing a
    category mapping would turn migration noise into supposed city churn.
    """
    if not isinstance(feature, dict) or not isinstance(feature.get('properties'), dict):
        raise ValueError('invalid_feature')
    props = feature['properties']
    old = props.get('categories')
    if old is not None and not isinstance(old, dict):
        raise ValueError('invalid_legacy_categories')
    if isinstance(old, dict) and old.get('primary') is not None and not isinstance(old['primary'], str):
        raise ValueError('invalid_legacy_categories')
    if props.get('taxonomy') is not None and not isinstance(props['taxonomy'], dict):
        raise ValueError('invalid_taxonomy')
    if props.get('basic_category') is not None and not isinstance(props['basic_category'], str):
        raise ValueError('invalid_basic_category')
    clone = dict(feature)
    clone['properties'] = {k: v for k, v in props.items() if k != 'categories'}
    row = normalize_feature(clone, cell=cell)
    # Preserve only aggregate migration diagnostics, not an invented remapping.
    flags = {
        'legacy_primary_present': isinstance(old, dict) and bool(old.get('primary')),
        'native_taxonomy_primary_present': isinstance(props.get('taxonomy'), dict)
                                         and bool(props['taxonomy'].get('primary')),
        'native_basic_category_present': bool(props.get('basic_category')),
    }
    return row, flags


def ingest_august_files(paths: dict[str, str | Path]) -> dict:
    """Read strictly bounded v1.18 GeoJSON FeatureCollections, no network."""
    if not isinstance(paths, dict) or set(paths) != set(PILOT):
        raise ValueError('Both original September geographic cells are mandatory')
    source_files = []
    by_id = {}
    rejected = Counter()
    flags = Counter()
    rows_seen = 0
    identical = 0
    for cell in sorted(PILOT):
        p = Path(paths[cell])
        if p.is_symlink() or not p.is_file() or not 0 < p.stat().st_size <= MAX_INPUT_BYTES:
            raise ValueError('Unsafe, empty or oversized August source file')
        raw = p.read_bytes()
        content = json.loads(raw)
        if not isinstance(content, dict) or content.get('type') != 'FeatureCollection' or not isinstance(content.get('features'), list):
            raise ValueError('August GeoJSON FeatureCollection required')
        source_files.append({'cell': cell, 'sha256': sha256(raw).hexdigest(), 'bytes': len(raw)})
        for feature in content['features']:
            rows_seen += 1
            if rows_seen > MAX_FEATURES:
                raise ValueError('Raw feature count exceeded, do not silently truncate')
            try:
                row, flag = normalize_august_feature(feature, cell=cell)
            except ValueError as err:
                rejected[str(err)] += 1
                continue
            existing = by_id.get(row['overture_id'])
            if existing is not None:
                if {k:v for k,v in existing.items() if k!='cell'} != {k:v for k,v in row.items() if k!='cell'}:
                    raise ValueError('Contradictory August records share Overture ID')
                identical += 1
                continue
            by_id[row['overture_id']] = row
            flags.update({name: int(flag[name]) for name in flag})
            if flag['legacy_primary_present'] and not flag['native_taxonomy_primary_present'] and not flag['native_basic_category_present']:
                flags['legacy_only_unmapped'] += 1
    records = sorted(by_id.values(), key=lambda x:x['overture_id'])
    if not records:
        raise ValueError('No valid August places in the two pilot windows')
    for row in records:
        _validated_record(row)
    duplicates = potential_duplicates(records)
    return {
        'records': records, 'source_files': source_files,
        'population_sha256': sha256(canonical(records)).hexdigest(),
        'migration': {
            'source_schema': SCHEMA_AUGUST,
            'target_schema': SCHEMA,
            'legacy_category_mapping_performed': False,
            'legacy_category_only_unmapped': flags['legacy_only_unmapped'],
            'native_taxonomy_present': flags['native_taxonomy_primary_present'],
            'native_basic_category_present': flags['native_basic_category_present'],
        },
        'audit': {
            'rows_read': rows_seen, 'accepted': len(records),
            'rejected': dict(sorted(rejected.items())),
            'duplicate_identical_ids': identical,
            'potential_duplicate_pairs': duplicates,
            'missing_taxonomy': sum(x['taxonomy_primary'] is None for x in records),
            'missing_address': sum(x['address'] is None for x in records),
        }
    }


def prepare_august_bundle(paths: dict[str, str | Path], *, output: Path,
                          stac_bytes: bytes, observed_at: str,
                          acquisition: str, stac_after_bytes: bytes | None = None) -> dict:
    """Write a new minimized, research-only bundle. No overwritten directories."""
    if acquisition not in {'historical_duckdb_public_s3', 'operator_supplied_local_files'}:
        raise ValueError('Unknown acquisition origin')
    when = aware(observed_at)
    if when.date() < datetime(2026,8,19).date() or when > datetime.now(timezone.utc):
        raise ValueError('Historical acquisition timestamp cannot predate release or lie in future')
    stac = validate_august_stac(stac_bytes)
    after = validate_august_stac(stac_bytes if stac_after_bytes is None else stac_after_bytes)
    result = ingest_august_files(paths)
    data = {'dataset':'KEP-DATA-007', 'release': AUGUST, 'study_only': True,
            'records': result['records']}
    data_bytes = canonical(data)
    if len(data_bytes) > MAX_NORMALIZED_BYTES:
        raise ValueError('Normalized historical dataset exceeds bound')
    manifest = {
        'study': 'KEP-DATA-007', 'source_release': AUGUST,
        'source_schema': SCHEMA_AUGUST, 'normalized_schema': SCHEMA,
        'research_only': True, 'consumer_display_approved': False,
        'sampling_cells': {k:list(v) for k,v in PILOT.items()},
        'stac_catalog_sha256': stac['catalog_sha256'],
        'stac_catalog_sha256_after': after['catalog_sha256'],
        'stac_release_listed_not_s3_proof': True,
        'acquisition': {'method': acquisition, 'observed_at': observed_at,
                        'upstream_authenticated_independently': False},
        'source_files': result['source_files'],
        'normalized_sha256': sha256(data_bytes).hexdigest(),
        'population_sha256': result['population_sha256'],
        'migration': result['migration'],
        'audit': result['audit'],
        'human_verified_business_changes': 0,
        'consumer_publish': False,
        'attribution_url': 'https://docs.overturemaps.org/attribution/',
    }
    manifest_bytes = canonical(manifest)
    if len(manifest_bytes) > MAX_MANIFEST_BYTES:
        raise ValueError('August metadata exceeds bound')
    output.mkdir(parents=True, exist_ok=False)
    (output / 'places_minimal.json').write_bytes(data_bytes)
    (output / 'manifest.json').write_bytes(manifest_bytes)
    return {'release': AUGUST, 'records': len(result['records']),
            'normalized_sha256': manifest['normalized_sha256'],
            'manifest_sha256': sha256(manifest_bytes).hexdigest(),
            'population_sha256': manifest['population_sha256'],
            'consumer_publish': False, 'upstream_authenticated_independently': False}


def load_august_snapshot(directory: Path | str, *, expected_sha256: str,
                         expected_manifest_sha256: str, expected_stac_sha256: str,
                         expected_observed_at: str) -> tuple[ResearchSnapshot, dict]:
    """Load externally pinned output. Hashes alone do NOT authenticate S3 origin."""
    root = Path(directory)
    raw = {}
    for filename, limit in (('places_minimal.json',MAX_NORMALIZED_BYTES),('manifest.json',MAX_MANIFEST_BYTES)):
        p = root / filename
        if p.is_symlink() or not p.is_file() or not 0 < p.stat().st_size <= limit:
            raise ValueError('Missing/unsafe/oversized August artifact')
        raw[filename] = p.read_bytes()
    b, m = raw['places_minimal.json'], raw['manifest.json']
    obj,meta = json.loads(b),json.loads(m)
    if not isinstance(obj,dict) or not isinstance(meta,dict) or canonical(obj)!=b or canonical(meta)!=m:
        raise ValueError('Noncanonical August research artifact')
    expected_manifest_keys={'study','source_release','source_schema','normalized_schema',
        'research_only','consumer_display_approved','sampling_cells',
        'stac_catalog_sha256','stac_catalog_sha256_after',
        'stac_release_listed_not_s3_proof','acquisition',
        'source_files','normalized_sha256','population_sha256','migration','audit',
        'human_verified_business_changes','consumer_publish','attribution_url'}
    if (set(meta)!=expected_manifest_keys or sha256(m).hexdigest()!=expected_manifest_sha256):
        raise ValueError('Historical manifest missing fields or SHA-256 differs')
    if (set(obj) != {'dataset','release','study_only','records'} or obj['dataset']!='KEP-DATA-007'
       or obj['release']!=AUGUST or obj['study_only'] is not True
       or meta.get('study')!='KEP-DATA-007' or meta.get('source_release')!=AUGUST
       or meta.get('source_schema')!=SCHEMA_AUGUST or meta.get('normalized_schema')!=SCHEMA
       or meta.get('research_only') is not True or meta.get('consumer_display_approved') is not False
       or meta.get('consumer_publish') is not False or meta.get('human_verified_business_changes')!=0
       or meta.get('sampling_cells')!={k:list(v) for k,v in PILOT.items()}
       or meta.get('attribution_url')!='https://docs.overturemaps.org/attribution/'
       or meta.get('stac_catalog_sha256')!=expected_stac_sha256
       or not isinstance(meta.get('stac_catalog_sha256_after'),str)
       or len(meta['stac_catalog_sha256_after'])!=64
       or meta.get('stac_release_listed_not_s3_proof') is not True
       or meta.get('acquisition',{}).get('method') not in {'historical_duckdb_public_s3','operator_supplied_local_files'}
       or meta.get('acquisition',{}).get('upstream_authenticated_independently') is not False
       or meta.get('normalized_sha256')!=expected_sha256
       or sha256(b).hexdigest()!=expected_sha256
       or meta.get('population_sha256')!=sha256(canonical(obj['records'])).hexdigest()
       or meta.get('acquisition',{}).get('observed_at')!=expected_observed_at
       or meta.get('migration',{}).get('legacy_category_mapping_performed') is not False):
        raise ValueError('August release/version/rights/migration/hash mismatch')
    sources=meta.get('source_files')
    if (not isinstance(sources,list) or len(sources)!=len(PILOT) or
        sorted(s.get('cell') for s in sources if isinstance(s,dict))!=sorted(PILOT)):
        raise ValueError('August source provenance entries missing')
    for s in sources:
        if (not isinstance(s,dict) or set(s)!={'cell','sha256','bytes'}
            or not isinstance(s['sha256'],str) or len(s['sha256'])!=64
            or type(s['bytes']) is not int or not 0 < s['bytes']<=MAX_INPUT_BYTES):
            raise ValueError('Invalid August raw file hash declaration')
    data=tuple(obj['records'])
    snapshot=ResearchSnapshot(release=AUGUST, observed_at=expected_observed_at,
        normalized_sha256=expected_sha256, population_sha256=meta['population_sha256'],
        origin='operator_supplied_research', records=data,
        sampling_cells=tuple(sorted(PILOT)),schema=SCHEMA)
    return snapshot, meta


def compare_august_september(directory: Path | str, *, expected_sha256: str,
                             expected_manifest_sha256: str, expected_stac_sha256: str,
                             expected_observed_at: str,
                             september_dir: Path | str | None = None) -> dict:
    old, metadata = load_august_snapshot(directory, expected_sha256=expected_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_stac_sha256=expected_stac_sha256, expected_observed_at=expected_observed_at)
    sep = snapshot_from_frozen_archive() if september_dir is None else snapshot_from_frozen_archive(september_dir)
    report = compare_snapshots(old, sep)
    # A missing old taxonomy is not evidence of a real category change.
    aug = {r['overture_id']:r for r in old.records}
    september = {r['overture_id']:r for r in sep.records}
    retained = set(aug)&set(september)
    ambiguous = sum(aug[rid]['taxonomy_primary'] is None and september[rid]['taxonomy_primary'] is not None for rid in retained)
    report['study']='KEP-DATA-007'
    report['cross_schema_migration']={
        'august_schema': SCHEMA_AUGUST, 'september_schema': SCHEMA,
        'legacy_category_mapping_performed': False,
        'august_legacy_only_unmapped': metadata['migration']['legacy_category_only_unmapped'],
        'retained_ids_with_unknown_august_category_and_known_september_category': ambiguous,
        'category_differences_are_semantically_comparable': False,
        'required_action':'Review original taxonomy and migration mapping before interpreting category drift',
    }
    report['august_acquisition_method']=metadata['acquisition']['method']
    report['may_infer_business_openings_closures']=False
    report['source_publisher_authenticated_by_hash_alone']=False
    return report
