"""KEP-DATA-010: independent offline replay of the original August Actions ZIP.

Only source-record changes. No source authentication, current opening-hours
verification, real business closures, network, model calls, or publishing.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
from pathlib import Path
from zipfile import BadZipFile, ZipFile
import json

from .overture_places import canonical
from .overture_real import load_archive

ORIGINAL_GITHUB_RUN = 38121005943
ORIGINAL_GITHUB_ARTIFACT = 11695042455
FROZEN_SHA = {
    'zip': 'cb9ee86c128b4839a00722e1b192f460691c0f33e358f0b0b9ae458ea403ef05',
    'places_minimal.json': 'ba22c8d7e52c7d6e7067fb67b16e623932dfbbf301b28bf55dd8d9e0e07a1664',
    'manifest.json': '7b291e03f37782be5657b99ef700411dd238cad57ce233c6b9502cf68903ca90',
    'historical_public_preflight.json': '6bb806047899cdf92d24d7d281ce2dd6464ab67c3fba63f6d39a2ac7da976bb4',
    'source_delta_provisional.json': 'a972bcd04aa01c70cf46a60a9c399104fa9d5238dbea41daff2ea0114de544ce',
}
ALLOWED = set(FROZEN_SHA)-{'zip'}
FIELDS = ('name','address','basic_category','taxonomy_primary',
          'operating_status','locality','country','source_provenance')


def compare_source_records(old: list[dict], new: list[dict]) -> dict:
    """Independent source-only ID/field counts; no physical-business inference."""
    a={r['overture_id']:r for r in old}
    b={r['overture_id']:r for r in new}
    if len(a)!=len(old) or len(b)!=len(new):
        raise ValueError('Duplicate Overture identifier')
    shared=a.keys()&b.keys()
    fields=Counter()
    modified=confidence_only=unchanged=0
    for rid in shared:
        x,y=a[rid],b[rid]
        factual=False
        for field in FIELDS:
            left,right=x.get(field),y.get(field)
            if field=='source_provenance':
                left=sorted(canonical(s) for s in left or [])
                right=sorted(canonical(s) for s in right or [])
            if left!=right:
                fields[field]+=1
                factual=True
        if (x.get('lon'),x.get('lat'))!=(y.get('lon'),y.get('lat')):
            fields['geometry']+=1
            factual=True
        if x.get('cell')!=y.get('cell'):
            fields['sample_cell']+=1
            factual=True
        confidence_changed=x.get('confidence')!=y.get('confidence')
        if confidence_changed:
            fields['confidence']+=1
        if factual:
            modified+=1
        elif confidence_changed:
            confidence_only+=1
        else:
            unchanged+=1
    return {
        'retained_ids':len(shared),
        'newly_listed_ids':len(set(b)-set(a)),
        'no_longer_listed_ids':len(set(a)-set(b)),
        'field_or_geometry_revised_ids':modified,
        'confidence_only_revised_ids':confidence_only,
        'unchanged_ids':unchanged,
        'field_change_counts':dict(sorted(fields.items())),
    }


def load_original_research_zip(path: str | Path) -> tuple[list[dict],dict,dict]:
    """Pin original run #38121005943 ZIP and per-member bytes; no network."""
    p=Path(path)
    if p.is_symlink() or not p.is_file() or not 0 < p.stat().st_size < 1_000_000:
        raise ValueError('Missing/unsafe historical ZIP')
    if sha256(p.read_bytes()).hexdigest()!=FROZEN_SHA['zip']:
        raise ValueError('Historical ZIP is not the captured GitHub artifact')
    try:
        with ZipFile(p) as archive:
            entries=archive.infolist()
            if (len(entries)!=len(ALLOWED) or set(x.filename for x in entries)!=ALLOWED
                or sum(x.file_size for x in entries)>10_000_000
                or any(x.file_size>10_000_000 or x.filename.startswith('/')
                       or '..' in x.filename for x in entries)):
                raise ValueError('Unexpected ZIP members')
            blobs={name:archive.read(name) for name in ALLOWED}
    except (BadZipFile,KeyError) as exc:
        raise ValueError('Corrupt historical artifact') from exc
    if any(sha256(body).hexdigest()!=FROZEN_SHA[name] for name,body in blobs.items()):
        raise ValueError('Historical component SHA-256 mismatch')
    source=json.loads(blobs['places_minimal.json'])
    manifest=json.loads(blobs['manifest.json'])
    receipt=json.loads(blobs['historical_public_preflight.json'])
    report=json.loads(blobs['source_delta_provisional.json'])
    rows=source.get('records')
    if (source.get('release')!='2026-08-19.0'
        or source.get('dataset')!='KEP-DATA-007'
        or source.get('study_only') is not True
        or not isinstance(rows,list) or len(rows)!=4650
        or manifest.get('source_release')!='2026-08-19.0'
        or manifest.get('normalized_sha256')!=FROZEN_SHA['places_minimal.json']
        or receipt.get('normalized_sha256')!=FROZEN_SHA['places_minimal.json']
        or receipt.get('manifest_sha256')!=FROZEN_SHA['manifest.json']
        or manifest.get('consumer_display_approved') is not False
        or receipt.get('one_parquet_head_verified') is not True
        or receipt.get('all_release_parts_verified') is not False
        or report.get('synthetic_second_release') is not False
        or report.get('real_world_business_changes_estimated') is not False
        or manifest.get('acquisition',{}).get('method')!='historical_duckdb_public_s3'):
        raise ValueError('Historical release, rights, or source provenance mismatch')
    if [x['overture_id'] for x in rows]!=sorted(set(x['overture_id'] for x in rows)):
        raise ValueError('Historical IDs repeated or unordered')
    return rows,manifest,report


def replay_artifact(path: str | Path) -> dict:
    older, august_manifest,original_report=load_original_research_zip(path)
    september,september_manifest,_=load_archive(verify=True)
    delta=compare_source_records(older,september['records'])
    expected=original_report['source_record_churn']
    if any(expected.get(k)!=v for k,v in delta.items()):
        raise ValueError('Independent replay differs from original workflow report')
    if (original_report.get('old_population_n')!=len(older)
        or original_report.get('new_population_n')!=len(september['records'])):
        raise ValueError('Historical population counts disagree')
    return {
        'study':'KEP-DATA-010',
        'comparison':'TWO_REAL_OVERTURE_SOURCE_RELEASES',
        'old_release':'2026-08-19.0',
        'new_release':'2026-09-23.1',
        'old_source_rows':len(older),
        'new_source_rows':len(september['records']),
        'record_delta':delta,
        'historical_zip_sha256':FROZEN_SHA['zip'],
        'historical_run_id':ORIGINAL_GITHUB_RUN,
        'historical_artifact_id':ORIGINAL_GITHUB_ARTIFACT,
        'september_source_sha256':september_manifest['population_sha256'],
        'historical_acquisition_time':august_manifest['acquisition']['observed_at'],
        'september_acquisition_time':september_manifest['acquisition']['downloaded_at_utc'],
        'capture_order_reversed':august_manifest['acquisition']['observed_at']>september_manifest['acquisition']['downloaded_at_utc'],
        'consumer_publish':False,
        'independent_upstream_s3_attestation':False,
        'category_semantics_comparable':False,
        'physical_business_openings':None,
        'physical_business_closures':None,
    }
