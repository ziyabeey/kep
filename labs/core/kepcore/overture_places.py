"""KEP-DATA-001: rights-attributed, OFFLINE Overture Places pilot quality lab.

Only point POIs; no users, contact fields, live hours, tickets or publication.
The v2 taxonomy and pinned release are mandatory. Bounding cells are sampling
areas, not a legal/administrative Besiktas or Karakoy district boundary.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from hashlib import sha256
from math import asin, cos, isfinite, radians, sin, sqrt
from pathlib import Path
from random import Random
from typing import Any
import json
import re
import unicodedata
import uuid

VERSION = 'KEP-DATA-001/v1'
MAX_INPUT_BYTES = 16_000_000
MAX_FEATURES = 12_000
PILOT = {
    'besiktas_center': (29.0020, 41.0400, 29.0100, 41.0455),
    'karakoy_center': (28.9700, 41.0200, 28.9810, 41.0275),
}
RELEASE_RE = re.compile(r'^20\d\d-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])\.\d+$')


def canonical(v: Any) -> bytes:
    return json.dumps(v, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')


def check_release(value: str) -> str:
    if not isinstance(value, str) or not RELEASE_RE.fullmatch(value):
        raise ValueError('Exact pinned Overture release is required')
    return value


def valid_stac_catalog(raw: bytes, *, pinned: str) -> dict:
    """Validate STAC latest before using the CLI which otherwise resolves latest.

    This makes a release change a STOP, never an invisible input change.
    """
    check_release(pinned)
    if len(raw) > 200_000:
        raise ValueError('STAC catalog exceeds bounded size')
    payload = json.loads(raw)
    if not isinstance(payload, dict) or payload.get('type') != 'Catalog' or payload.get('stac_version') is None:
        raise ValueError('Not an Overture STAC catalog')
    current = payload.get('latest')
    check_release(current)
    links = payload.get('links')
    if not isinstance(links, list) or not any(
        isinstance(link, dict) and link.get('latest') is True
        and link.get('rel') == 'child' and current in str(link.get('href', ''))
        for link in links
    ):
        raise ValueError('Latest release is not linked by STAC')
    if current != pinned:
        raise ValueError(f'STAC now points to {current}, but this experiment pins {pinned}')
    return {'release': current, 'stac_sha256': sha256(raw).hexdigest()}


def _clean(value: Any, limit: int = 250) -> str | None:
    if not isinstance(value, str):
        return None
    val = ' '.join(value.split())
    return val[:limit] if val else None


def _point(feature: dict) -> tuple[float, float]:
    geometry = feature.get('geometry')
    if not isinstance(geometry, dict) or geometry.get('type') != 'Point':
        raise ValueError('invalid_geometry')
    xy = geometry.get('coordinates')
    if not isinstance(xy, list) or len(xy) < 2 or any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in xy[:2]):
        raise ValueError('invalid_geometry')
    lng, lat = float(xy[0]), float(xy[1])
    if not all(map(isfinite, (lng, lat))) or not (-180 <= lng <= 180 and -90 <= lat <= 90):
        raise ValueError('invalid_geometry')
    return lng, lat


def _contained(lng: float, lat: float, cell: str) -> bool:
    west, south, east, north = PILOT[cell]
    return west <= lng <= east and south <= lat <= north


def _identity(feature: dict) -> str:
    props = feature.get('properties') or {}
    value = props.get('id') or feature.get('id')
    if not isinstance(value, str):
        raise ValueError('invalid_id')
    try:
        parsed = uuid.UUID(value)
    except ValueError as exc:
        raise ValueError('invalid_id') from exc
    if str(parsed) != value.lower():
        raise ValueError('invalid_id')
    return str(parsed)


def normalize_feature(feature: Any, *, cell: str) -> dict:
    """Minimal schema v2: no phone, emails, socials, reviews, images or live claims."""
    if cell not in PILOT:
        raise ValueError('unknown_cell')
    if not isinstance(feature, dict) or feature.get('type') != 'Feature':
        raise ValueError('invalid_feature')
    props = feature.get('properties')
    if not isinstance(props, dict):
        raise ValueError('invalid_feature')
    if 'categories' in props:
        raise ValueError('obsolete_categories_schema')
    if props.get('theme') not in (None, 'places') or props.get('type') not in (None, 'place'):
        raise ValueError('not_a_place')
    lng, lat = _point(feature)
    if not _contained(lng, lat, cell):
        raise ValueError('outside_sampling_cell')
    fid = _identity(feature)
    names = props.get('names')
    names = names if isinstance(names, dict) else {}
    taxonomy = props.get('taxonomy')
    taxonomy = taxonomy if isinstance(taxonomy, dict) else {}
    category = _clean(taxonomy.get('primary') or props.get('basic_category'), 100)
    basic = _clean(props.get('basic_category'), 100)
    conf = props.get('confidence')
    if conf is not None and (isinstance(conf, bool) or not isinstance(conf, (int, float)) or not isfinite(conf) or not (0 <= conf <= 1)):
        raise ValueError('invalid_confidence')
    operating = props.get('operating_status')
    if operating not in (None, 'open', 'temporarily_closed', 'permanently_closed'):
        raise ValueError('invalid_operating_status')
    raw_addresses = props.get('addresses')
    first_address = next((x for x in raw_addresses if isinstance(x, dict)), {}) if isinstance(raw_addresses, list) else {}
    raw_sources = props.get('sources')
    provenance = []
    if isinstance(raw_sources, list):
        for src in raw_sources[:8]:
            if isinstance(src, dict):
                provenance.append({
                    'dataset': _clean(src.get('dataset'), 100),
                    'provider': _clean(src.get('provider'), 100),
                    'license': _clean(src.get('license'), 120),
                })
    return {
        'overture_id': fid,  # stable feature key, NOT independently verified GERS registry membership
        'name': _clean(names.get('primary')),
        'taxonomy_primary': category,
        'basic_category': basic,
        'lon': lng,
        'lat': lat,
        'cell': cell,  # sample selection, NOT administrative district membership
        'confidence': None if conf is None else float(conf),
        'operating_status': operating,  # NOT open now
        'address': _clean(first_address.get('freeform'), 300),
        'locality': _clean(first_address.get('locality'), 100),
        'country': _clean(first_address.get('country'), 3),
        'source_provenance': provenance,
        'open_now': None,
        'opening_hours': None,
        'live_price': None,
        'active_event': None,
        'consumer_verified': False,
        'administrative_district': None,
    }


def _name_key(value: str | None) -> str:
    if not value:
        return ''
    # Unicode-aware, intentionally conservative: close-name matching is only a REVIEW hint.
    decomposed = unicodedata.normalize('NFKD', value.casefold().replace('ı', 'i'))
    base = ''.join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]+', '', base)


def metres_between(a: dict, b: dict) -> float:
    r = 6371008.8
    lat1, lat2 = radians(a['lat']), radians(b['lat'])
    dlat, dlon = lat2 - lat1, radians(b['lon'] - a['lon'])
    h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * r * asin(min(1, sqrt(h)))


def potential_duplicates(records: list[dict], *, max_pairs: int = 2500) -> list[dict]:
    """Strictly human-review candidates, never automatic entity merging."""
    groups = defaultdict(list)
    for r in records:
        key = (_name_key(r['name']), r['basic_category'] or r['taxonomy_primary'])
        if key[0] and key[1]:
            groups[key].append(r)
    pairs = []
    for key in sorted(groups):
        group = sorted(groups[key], key=lambda r: r['overture_id'])
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                if metres_between(a, b) <= 45:
                    pairs.append({'left': a['overture_id'], 'right': b['overture_id'],
                                  'distance_m': round(metres_between(a, b), 2),
                                  'action': 'human_review_only'})
                    if len(pairs) > max_pairs:
                        raise ValueError('Too many suspected duplicates; reduce pilot area')
    return pairs


def ingest_geojson(paths: dict[str, str | Path], *, pinned_release: str, max_features: int = MAX_FEATURES) -> dict:
    """Read bounded local GeoJSON extracts. No HTTP and no user publication."""
    check_release(pinned_release)
    if not isinstance(max_features, int) or isinstance(max_features, bool) or not (1 <= max_features <= MAX_FEATURES):
        raise ValueError('Invalid maximum feature count')
    if not paths or not set(paths).issubset(PILOT):
        raise ValueError('Only documented pilot cells are allowed')
    records = {}
    rejected = Counter()
    identical_id_reposts = 0
    read_count = 0
    source_files = []
    for cell in sorted(paths):
        path = Path(paths[cell])
        if path.is_symlink() or not path.is_file():
            raise ValueError('Missing or unsafe source file')
        if path.stat().st_size > MAX_INPUT_BYTES:
            raise ValueError('Input geojson file is too large')
        raw_bytes = path.read_bytes()
        raw = json.loads(raw_bytes)
        if not isinstance(raw, dict) or raw.get('type') != 'FeatureCollection' or not isinstance(raw.get('features'), list):
            raise ValueError('Expected GeoJSON FeatureCollection')
        source_files.append({'cell': cell, 'sha256': sha256(raw_bytes).hexdigest(), 'bytes': len(raw_bytes)})
        for feature in raw['features']:
            read_count += 1
            if read_count > max_features:
                raise ValueError('Feature count exceeded; never silently sample or truncate')
            try:
                result = normalize_feature(feature, cell=cell)
            except ValueError as exc:
                rejected[str(exc)] += 1
                continue
            rid = result['overture_id']
            if rid in records:
                old = records[rid]
                # Across overlapping bboxes an identical record may appear in both.
                # Ignore cell to compare semantic identity. Contradictions stop the import.
                if {k: v for k, v in old.items() if k != 'cell'} != {k: v for k, v in result.items() if k != 'cell'}:
                    raise ValueError('Conflicting rows share one Overture feature ID')
                identical_id_reposts += 1
                continue
            records[rid] = result
    data = sorted(records.values(), key=lambda x: x['overture_id'])
    duplicates = potential_duplicates(data)
    return {
        'study': VERSION,
        'release': pinned_release,
        'origin': 'overture_raw_geojson',
        'real_data_proof': 'input bytes supplied by separate acquisition step; inspect provenance manifest',
        'research_only': True,
        'consumer_publish': False,
        'source_files': source_files,
        'population_sha256': sha256(canonical(data)).hexdigest(),
        'normalized_places': data,
        'audit': {
            'rows_read': read_count,
            'accepted': len(data),
            'rejected': dict(sorted(rejected.items())),
            'duplicate_identical_ids': identical_id_reposts,
            'potential_duplicate_pairs': duplicates,
            'unknown_name': sum(r['name'] is None for r in data),
            'unknown_taxonomy': sum(r['taxonomy_primary'] is None for r in data),
            'unknown_address': sum(r['address'] is None for r in data),
            'missing_confidence': sum(r['confidence'] is None for r in data),
            'unknown_source_provenance': sum(not r['source_provenance'] for r in data),
            'mean_overture_confidence_not_truth': (round(sum(r['confidence'] for r in data if r['confidence'] is not None) /
                                                          sum(r['confidence'] is not None for r in data), 5)
                                                     if any(r['confidence'] is not None for r in data) else None),
            'claim_verified_place_count': 0,
            'claim_verified_open_now_count': 0,
            'human_audited_count': 0,
        },
    }


def pilot_audit_plan(dataset: dict, *, budget: int, seed: str) -> dict:
    """Stratified random place audit, allocation from SCI-003; NO outcomes.

    Review tasks only. This is not a measured place-error rate and does not
    claim to run event-field SCI-003 reliability inference on POI observations.
    """
    from .audit_sampling import _allocated
    records = dataset.get('normalized_places')
    if not isinstance(records, list) or not records:
        raise ValueError('Empty population')
    if len(seed) < 16:
        raise ValueError('Private sampling seed of 16+ characters required')
    if sha256(canonical(sorted(records, key=lambda x: x['overture_id']))).hexdigest() != dataset['population_sha256']:
        raise ValueError('Population content no longer matches its frozen hash')
    strata = defaultdict(list)
    for r in records:
        strata[(r['cell'], 'place')].append(r)
    allocation = _allocated(strata, budget, 1)
    picked, details = [], []
    for stratum in sorted(strata):
        group = sorted(strata[stratum], key=lambda x: x['overture_id'])
        local_salt = sha256((seed + '|' + dataset['population_sha256'] + '|' + '|'.join(stratum)).encode()).hexdigest()
        chosen = Random(int(local_salt, 16)).sample(group, allocation[stratum])
        inclusion = len(chosen) / len(group)
        details.append({'cell': stratum[0], 'N': len(group), 'n': len(chosen), 'inclusion_probability': inclusion})
        picked.extend({'overture_id': r['overture_id'], 'cell': r['cell'], 'name': r['name'],
                       'inclusion_probability': inclusion, 'review_outcome': None}
                      for r in chosen)
    return {'study': 'KEP-DATA-001-place-audit-plan', 'research_only': True,
            'verified_labels': 0, 'population_sha256': dataset['population_sha256'],
            'seed_commitment_sha256': sha256(seed.encode()).hexdigest(),
            'source_release': dataset['release'], 'strata': details,
            'selected': sorted(picked, key=lambda r: r['overture_id'])}
