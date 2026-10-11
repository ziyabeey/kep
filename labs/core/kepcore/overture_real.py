"""KEP-DATA-003: pinned, offline, real Overture Istanbul POI replay.

The 4,803 POIs are ACTUAL Overture dataset records, but the underlying
businesses and live operating conditions are NOT independently verified.
This module never opens a network connection, grants content-display rights,
or feeds unchecked Overture confidence into the KEP recommendation score.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from gzip import GzipFile
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import json

from .core import Query, decide, stable_hash
from .overture_audit import (
    verify_artifact, design_existence_audit, confidence_band,
)
from .overture_places import canonical

DATA_DIR = Path(__file__).resolve().parents[1] / 'data/real/overture_istanbul_2026-09-23.1'
MAX_COMPRESSED_BYTES = 1_000_000
MAX_UNCOMPRESSED_BYTES = 4_000_000
MAX_MANIFEST_BYTES = 20_000
EXPECTED_COUNT = 4803


def _pinned_file(root: Path, name: str, max_bytes: int) -> bytes:
    """Do not accept symlinked or oversized datasets, including archive bombs."""
    path = root / name
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= max_bytes:
        raise ValueError(f'Missing, unsafe, empty or oversized pinned file: {name}')
    return path.read_bytes()


def load_archive(directory: Path | str = DATA_DIR, *, verify: bool = True) -> tuple[dict, dict, dict]:
    """Return validated, fully pinned real records and research provenance.

    Decompresses at most 4 MB and verifies exact canonical bytes and digests.
    This guarantees internal consistency with this repo's pinned manifest, NOT
    independent upstream/authenticity or physical venue existence.
    """
    root = Path(directory)
    meta_bytes = _pinned_file(root, 'archive_metadata.json', MAX_MANIFEST_BYTES)
    manifest_bytes = _pinned_file(root, 'manifest.json', MAX_MANIFEST_BYTES)
    packed = _pinned_file(root, 'places_minimal.json.gz', MAX_COMPRESSED_BYTES)
    meta = json.loads(meta_bytes)
    if canonical(meta) != meta_bytes:
        raise ValueError('Archive metadata is not canonical')
    if set(meta) != {
        'study', 'research_only', 'consumer_display_approved', 'source', 'release',
        'schema', 'github_repo', 'original_actions_run_id', 'original_actions_run_url',
        'original_actions_artifact_id', 'original_actions_artifact_sha256',
        'artifact_expires_at', 'original_raw_geojson_in_repo',
        'raw_source_sha256_independently_verified', 'normalized_sha256',
        'normalized_uncompressed_bytes', 'compressed_sha256', 'compressed_bytes',
        'manifest_sha256', 'record_count', 'sampling_cells', 'rights_source',
        'licenses_observed', 'provenance_statement', 'not_proof_of',
    }:
        raise ValueError('Unknown or missing archive provenance fields')
    if (meta['study'] != 'KEP-DATA-003' or meta['release'] != '2026-09-23.1'
        or meta['research_only'] is not True or meta['consumer_display_approved'] is not False
        or meta['original_raw_geojson_in_repo'] is not False
        or meta['raw_source_sha256_independently_verified'] is not False
        or meta['record_count'] != EXPECTED_COUNT):
        raise ValueError('Archive research boundary or pinned release violated')
    if meta['compressed_bytes'] != len(packed) or meta['compressed_sha256'] != sha256(packed).hexdigest():
        raise ValueError('Compressed archive SHA-256 mismatch')
    if meta['manifest_sha256'] != sha256(manifest_bytes).hexdigest():
        raise ValueError('Manifest SHA-256 mismatch')
    try:
        with GzipFile(fileobj=BytesIO(packed), mode='rb') as handle:
            content = handle.read(MAX_UNCOMPRESSED_BYTES + 1)
            if len(content) > MAX_UNCOMPRESSED_BYTES or handle.read(1):
                raise ValueError('Expanded archive exceeds the size limit')
    except (OSError, EOFError) as exc:
        raise ValueError('Compressed snapshot is damaged') from exc
    if meta['normalized_uncompressed_bytes'] != len(content) or meta['normalized_sha256'] != sha256(content).hexdigest():
        raise ValueError('Uncompressed normalized snapshot SHA-256 mismatch')
    doc = json.loads(content)
    manifest = json.loads(manifest_bytes)
    if canonical(doc) != content or canonical(manifest) != manifest_bytes:
        raise ValueError('Noncanonical Overture snapshot / manifest')
    if not isinstance(doc.get('records'), list) or len(doc['records']) != EXPECTED_COUNT:
        raise ValueError('Frozen record count changed')
    if doc.get('study_only') is not True or doc.get('release') != meta['release']:
        raise ValueError('Unexpected data release or safety scope')
    if manifest.get('normalized_sha256') != meta['normalized_sha256'] or manifest.get('pinned_release') != meta['release']:
        raise ValueError('Overture manifest contradicts pinned archive')
    if verify:
        # Full existing DATA-002 checks for each record, licence and data counts.
        # verify_artifact takes a directory; use a bounded temporary directory and
        # avoid publishing its contents after the run.
        from tempfile import TemporaryDirectory
        with TemporaryDirectory(prefix='kep-real-overture-') as tmp:
            path = Path(tmp)
            (path / 'places_minimal.json').write_bytes(content)
            (path / 'manifest.json').write_bytes(manifest_bytes)
            evidence = verify_artifact(path, require_live=True)
            if evidence['population_n'] != EXPECTED_COUNT:
                raise ValueError('Internal audit population differs from pinned count')
    return doc, manifest, meta


def quality_report(directory: Path | str = DATA_DIR) -> dict:
    """Descriptive DATA quality only. No precision or business-existence rate."""
    data, manifest, meta = load_archive(directory)
    records = data['records']
    by_cell = Counter(r['cell'] for r in records)
    by_category = Counter(r['basic_category'] or '<unknown>' for r in records)
    by_band = Counter(confidence_band(r['confidence']) for r in records)
    by_provenance = Counter((entry['provider'], entry['license'])
                            for r in records for entry in r['source_provenance'])
    unavailable = ('open_now', 'opening_hours', 'live_price', 'active_event')
    if any(r[k] is not None for r in records for k in unavailable):
        raise ValueError('A real-time claim appeared in frozen historical POI data')
    if any(r['consumer_verified'] is not False for r in records):
        raise ValueError('An unreviewed record was marked verified')
    return {
        'study': 'KEP-DATA-003', 'dataset':'real_overture_snapshot_not_ground_truth',
        'research_only':True, 'consumer_display_approved':False,
        'archive_release':meta['release'], 'github_run_id':meta['original_actions_run_id'],
        'normalized_sha256':meta['normalized_sha256'],
        'population_sha256':manifest['population_sha256'],
        'n':len(records), 'by_cell':dict(sorted(by_cell.items())),
        'missing_address':sum(r['address'] is None for r in records),
        'missing_name':sum(r['name'] is None for r in records),
        'missing_taxonomy':sum(r['taxonomy_primary'] is None for r in records),
        'candidate_duplicate_pairs_conservative':len(manifest['audit']['potential_duplicate_pairs']),
        'confidence_bands':dict(sorted(by_band.items())),
        'basic_categories_top_15':[
            {'name':k, 'n':v} for k,v in sorted(by_category.items(),key=lambda p:(-p[1],p[0]))[:15]
        ],
        'provider_license_rows':[{'provider':k[0], 'license':k[1], 'n':v}
                                 for k,v in sorted(by_provenance.items())],
        'human_confirmed_businesses':0,
        'live_open_now_observations':0,
        'source_files_stored':False,
        'upstream_authenticated_independently':False,
        'warning':'Source release and file hashes are pinned; no claim of actual business existence, open-now, events, fresh pricing or consumer publication.'
    }


def core_research_candidates(directory: Path | str = DATA_DIR, *, limit: int = 30,
                             basic_category: str | None = None, cell: str | None = None) -> list[dict]:
    """Convert Overture records only to *blocked* Core research candidates.

    The existing Core rights gate MUST exclude these from consumer discovery.
    No Overture row is promoted to consumer_display/open_attribution by this code.
    """
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 50:
        raise ValueError('Choose 1..50 research candidate records')
    data, manifest, meta = load_archive(directory)
    out = []
    for r in data['records']:
        if basic_category is not None and r['basic_category'] != basic_category:
            continue
        if cell is not None and r['cell'] != cell:
            continue
        if r['name'] is None:
            continue
        out.append({
            'id':'overture_place:'+r['overture_id'], 'kind':'place', 'name':r['name'],
            'city':'İstanbul', 'category':r['basic_category'] or 'other',
            'lat':r['lat'], 'lon':r['lon'], 'source_url':'https://docs.overturemaps.org/guides/places/',
            'source_id':'overture_places_2026-09-23.1',
            'source_record_hash':stable_hash(r), 'source_release':meta['release'],
            'publisher_root':'overture', 'rights_scope':'research_ingest',
            'evidence_status':'source_recorded', 'lifecycle':'listed_claim',
            'origin_live_verified':False, 'source_observed_at':None,
            'opening_hours':None, 'price':None, 'currency':'TRY', 'crowd':None,
            'synthetic':False, 'flags':['NOT_HUMAN_VERIFIED','OPEN_NOW_UNKNOWN','CONSUMER_DISPLAY_NOT_APPROVED'],
        })
        if len(out)==limit: break
    return out


def check_core_publish_gate(directory: Path | str = DATA_DIR) -> dict:
    candidates=core_research_candidates(directory,limit=25)
    decision=decide(candidates,Query(city='İstanbul',kind='place'))
    blocked_all=(decision.action=='ABSTAIN' and not decision.selected and
                 all('RIGHTS_NOT_APPROVED' in v for v in decision.blocked.values()))
    if not blocked_all:
        raise AssertionError('Research-only Overture places breached Core display gate')
    return {'n_tested':len(candidates),'blocked':len(decision.blocked),
            'action':decision.action,'no_consumer_display':blocked_all}


def prepare_private_audit(directory: Path | str, *, budget: int,
                          seed: str, sampled_at: str) -> dict:
    """Draw a genuine random sample over real records (not a truth survey)."""
    load_archive(directory)
    from tempfile import TemporaryDirectory
    doc, manifest, _ = load_archive(directory, verify=False)
    with TemporaryDirectory(prefix='kep-real-audit-') as tmp:
        path=Path(tmp)
        (path/'places_minimal.json').write_bytes(canonical(doc))
        (path/'manifest.json').write_bytes(canonical(manifest))
        plan=design_existence_audit(path,budget=budget,seed=seed,sampled_at=sampled_at)
    record_by_id={r['overture_id']:r for r in doc['records']}
    # The review sheet is unlabelled and does not declare any place verified.
    sheet=[{
        'overture_id':s['overture_id'],
        'name':record_by_id[s['overture_id']]['name'],
        'address':record_by_id[s['overture_id']]['address'],
        'lat':record_by_id[s['overture_id']]['lat'],
        'lon':record_by_id[s['overture_id']]['lon'],
        'category':record_by_id[s['overture_id']]['basic_category'],
        'cell':s['cell'],'confidence_band':s['confidence_band'],
        'inclusion_probability':s['inclusion_probability'],
        'reviewer_a':'PENDING','reviewer_b':'PENDING','evidence_urls':[],
        'physical_existence_label':'UNREVIEWED',
    } for s in plan['selected']]
    return {'plan':plan,'unlabeled_review_sheet':sheet,
            'research_only':True,'observed_label_count':0}
