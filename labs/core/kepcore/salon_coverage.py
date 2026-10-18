"""KEP-DATA-019 (Faz 0): Overture salon coverage of Randevu salons, offline.

Pure standard library. Implements the frozen rules in
benchmarks/salon_coverage_protocol.json; every threshold is read from that
file, never hard-coded twice. Inputs are a private Overture extract (JSONL,
written by scripts/salon_coverage.py) and a private Randevu CSV export.
Nothing here touches the network.
"""
from __future__ import annotations

from datetime import date
from difflib import SequenceMatcher
from hashlib import sha256
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from typing import Any, Iterable
import json
import re
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / 'benchmarks/salon_coverage_protocol.json'

FOLD = str.maketrans({'ç': 'c', 'ğ': 'g', 'ı': 'i', 'ö': 'o', 'ş': 's', 'ü': 'u'})
STREET_MARK = re.compile(r'\b([a-z0-9]+)\s+(?:cad|cd|caddesi|cadde|sok|sk|sokak|sokagi|bulvari|bulvar|blv|bulv)\b')


def load_protocol(path: Path = PROTOCOL_PATH) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def protocol_sha256(path: Path = PROTOCOL_PATH) -> str:
    return sha256(path.read_bytes()).hexdigest()


def generic_tokens(protocol: dict) -> frozenset[str]:
    step = next(s for s in protocol['matching']['name_normalisation'] if s.startswith('drop generic tokens:'))
    return frozenset(step.split(':', 1)[1].split())


def fold(text: str | None) -> str:
    """Turkish-aware casefold to plain [a-z0-9 ] words.

    Python's 'İ'.lower() is 'i' + U+0307 and 'I'.lower() is 'i', so the
    Turkish pairs are mapped before lower().
    """
    if not text:
        return ''
    text = text.replace('İ', 'i').replace('I', 'ı').lower().translate(FOLD)
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r'[^a-z0-9]+', ' ', text).strip()


def name_tokens(name: str | None, generic: frozenset[str]) -> list[str]:
    tokens = fold(name).split()
    kept = [t for t in tokens if t not in generic]
    return kept or tokens


def name_similarity(a: str | None, b: str | None, generic: frozenset[str]) -> float:
    ta, tb = name_tokens(a, generic), name_tokens(b, generic)
    if not ta or not tb:
        return 0.0
    sa, sb = set(ta), set(tb)
    small, big = (sa, sb) if len(''.join(sorted(sa))) <= len(''.join(sorted(sb))) else (sb, sa)
    if len(''.join(small)) >= 4 and small <= big:
        return 1.0
    return SequenceMatcher(None, ' '.join(sorted(ta)), ' '.join(sorted(tb))).ratio()


def phone_key(phone: str | None) -> str | None:
    digits = re.sub(r'\D', '', phone or '')
    return digits[-10:] if len(digits) >= 10 else None


def street_tokens(address: str | None) -> set[str]:
    return {m.group(1) for m in STREET_MARK.finditer(fold(address)) if not m.group(1).isdigit()}


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = radians(lat1), radians(lat2)
    h = sin((p2 - p1) / 2) ** 2 + cos(p1) * cos(p2) * sin(radians(lon2 - lon1) / 2) ** 2
    return 2 * 6_371_008.8 * asin(sqrt(h))


def wilson(found: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = found / n
    den = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / den
    half = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, mid - half), min(1.0, mid + half))


# --- Overture side -------------------------------------------------------

def latest_update(update_times: Iterable[str | None]) -> date | None:
    best = None
    for value in update_times:
        try:
            day = date.fromisoformat(str(value)[:10])
        except (TypeError, ValueError):
            continue
        best = day if best is None or day > best else best
    return best


def is_salon(place: dict, protocol: dict) -> bool:
    wanted = set(protocol['overture']['salon_categories']['list'])
    cats = {place.get('category')} | set(place.get('alternates') or [])
    return bool(cats & wanted)


def funnel_stage(place: dict, protocol: dict) -> int:
    """How many freshness steps the place passes: 0 status, 1 confidence, 2 update time, 3 = fresh."""
    rules = protocol['overture']['freshness_filter']
    if place.get('operating_status') in ('permanently_closed', 'temporarily_closed'):
        return 0
    if (place.get('confidence') or 0.0) < rules['min_confidence']:
        return 1
    latest = latest_update(place.get('update_times') or [])
    if latest is None or latest < date.fromisoformat(rules['min_latest_source_update_time']):
        return 2
    return 3


# --- Randevu side --------------------------------------------------------

def is_test_business(row: dict, protocol: dict) -> bool:
    rule = protocol['randevu']['exclusions'][0]
    pattern = re.compile(re.search(r'\(\?i\)\([^)]*\)', rule).group(0))
    return any(pattern.search(str(row.get(k) or '')) for k in ('name', 'slug'))


def usable_coordinate(row: dict, protocol: dict, *, allow_google: bool) -> tuple[float, float] | None:
    policy = protocol['randevu']['coordinate_policy']
    allowed = set(policy['usable_in_primary']) | (set(policy['not_usable_in_primary']) if allow_google else set())
    if (row.get('location_source') or '') not in allowed:
        return None
    try:
        lat, lon = float(row['latitude']), float(row['longitude'])
    except (KeyError, TypeError, ValueError):
        return None
    return (lat, lon) if -90 <= lat <= 90 and -180 <= lon <= 180 and (lat, lon) != (0.0, 0.0) else None


def in_district(row: dict, district: str) -> bool:
    return re.search(rf'\b{re.escape(fold(district))}\b', fold(row.get('address_text'))) is not None


def eligible(rows: list[dict], protocol: dict) -> list[dict]:
    out = []
    for row in rows:
        if is_test_business(row, protocol):
            continue
        if not (row.get('address_text') or '').strip() and usable_coordinate(row, protocol, allow_google=False) is None:
            continue
        out.append(row)
    return out


def choose_district(rows: list[dict], protocol: dict, districts: Iterable[str]) -> tuple[str | None, dict[str, int]]:
    minimum = protocol['gate']['min_eligible_salons']
    primary = protocol['district_choice']['primary']
    counts = {d: sum(in_district(r, d) for r in rows) for d in sorted(set(districts) | {primary})}
    if counts[primary] >= minimum:
        return primary, counts
    best = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return (best[0][0] if best and best[0][1] >= minimum else None), counts


# --- Matching ------------------------------------------------------------

def candidate_edges(salon: dict, places: list[dict], protocol: dict, generic: frozenset[str],
                    *, allow_google: bool) -> list[dict]:
    """Every Overture place that satisfies one of the frozen match rules for this salon."""
    m = protocol['matching']
    coord = usable_coordinate(salon, protocol, allow_google=allow_google)
    phone = phone_key(salon.get('public_phone'))
    streets = street_tokens(salon.get('address_text'))
    sims = [(name_similarity(salon.get('name'), p.get('name'), generic), p) for p in places]
    strong = [p for s, p in sims if s >= 0.80]
    edges = []
    for sim, place in sims:
        dist = haversine_m(coord[0], coord[1], place['lat'], place['lon']) if coord else None
        kind = None
        if phone and phone in {phone_key(x) for x in place.get('phones') or []}:
            kind = 'PHONE'
        elif sim >= 0.80 and coord is not None and dist <= 150:
            kind = 'NAME_DISTANCE'
        elif sim >= 0.80 and coord is None and streets and any(streets & street_tokens(a) for a in place.get('freeform') or []):
            kind = 'NAME_STREET'
        elif sim >= 0.90 and coord is None and not (place.get('freeform') or []) and len(strong) == 1:
            kind = 'NAME_UNIQUE'
        if kind:
            edges.append({'business_id': salon['business_id'], 'place_id': place['id'], 'kind': kind,
                          'similarity': round(sim, 6), 'distance_m': None if dist is None else round(dist, 1)})
    assert m['candidate_pool_primary'].startswith('the filtered universe')
    return edges


def near_misses(salon: dict, places: list[dict], generic: frozenset[str]) -> list[dict]:
    return [{'business_id': salon['business_id'], 'place_id': p['id'], 'overture_name': p.get('name'),
             'similarity': round(s, 6)}
            for p in places if 0.60 <= (s := name_similarity(salon.get('name'), p.get('name'), generic)) < 0.80]


def assign_one_to_one(edges: list[dict]) -> dict[str, dict]:
    order = sorted(edges, key=lambda e: (-e['similarity'], float('inf') if e['distance_m'] is None else e['distance_m'],
                                         e['business_id'], e['place_id']))
    taken_place, chosen = set(), {}
    for edge in order:
        if edge['business_id'] in chosen or edge['place_id'] in taken_place:
            continue
        chosen[edge['business_id']] = edge
        taken_place.add(edge['place_id'])
    return chosen


def coverage(salons: list[dict], places: list[dict], protocol: dict, *, allow_google: bool) -> dict:
    generic = generic_tokens(protocol)
    edges = [e for s in salons for e in candidate_edges(s, places, protocol, generic, allow_google=allow_google)]
    chosen = assign_one_to_one(edges)
    found, n = len(chosen), len(salons)
    low, high = wilson(found, n)
    kinds: dict[str, int] = {}
    for edge in chosen.values():
        kinds[edge['kind']] = kinds.get(edge['kind'], 0) + 1
    return {'eligible': n, 'found': found, 'coverage': round(found / n, 6) if n else None,
            'wilson95': [round(low, 6), round(high, 6)], 'match_kinds': dict(sorted(kinds.items())),
            'matches': sorted(chosen.values(), key=lambda e: e['business_id'])}


def gate(result: dict, protocol: dict) -> str:
    g = protocol['gate']
    if result['eligible'] < g['min_eligible_salons']:
        return 'ABSTAIN_SMALL_N'
    if result['coverage'] >= 0.70 and result['wilson95'][0] >= 0.50:
        return 'GO_FAZ1'
    if result['coverage'] < 0.50:
        return 'NO_GO_CHANGE_DISTRICT_OR_SECTOR'
    return 'GRAY_EXTEND'


def evaluate(randevu_rows: list[dict], overture_places: list[dict], protocol: dict, *,
             allow_google: bool = False) -> dict[str, Any]:
    """overture_places: every extracted place, each with a 'district' field from the polygon join."""
    rows = eligible(randevu_rows, protocol)
    districts = {p['district'] for p in overture_places if p.get('district')}
    district, counts = choose_district(rows, protocol, districts)
    report: dict[str, Any] = {'study': protocol['study'], 'release': protocol['overture']['release'],
                              'randevu_rows': len(randevu_rows), 'randevu_eligible_rows': len(rows),
                              'randevu_district_counts': {k: v for k, v in counts.items() if v},
                              'district': district}
    if district is None:
        report['status'] = 'ABSTAIN_SMALL_N'
        return report
    in_poly = [p for p in overture_places if p.get('district') == district]
    salons_all = [p for p in in_poly if is_salon(p, protocol)]
    stages = [funnel_stage(p, protocol) for p in salons_all]
    universe = [p for p, s in zip(salons_all, stages) if s == 3]
    salons = [r for r in rows if in_district(r, district)]
    report['funnel'] = {
        'salon_places_in_polygon': len(salons_all),
        'after_operating_status': sum(s >= 1 for s in stages),
        'after_min_confidence': sum(s >= 2 for s in stages),
        'after_freshness_Y_universe': len(universe),
    }
    primary = coverage(salons, universe, protocol, allow_google=False)
    report['X_randevu_salons'] = primary['eligible']
    report['Y_found'] = primary['found']
    report['Z_coverage'] = primary['coverage']
    report['wilson95'] = primary['wilson95']
    report['match_kinds'] = primary['match_kinds']
    unfiltered = coverage(salons, in_poly, protocol, allow_google=False)
    report['Z_unfiltered'] = unfiltered['coverage']
    report['status'] = gate(primary, protocol)
    if allow_google:
        report['SENSITIVITY_GOOGLE_COORDS'] = {k: v for k, v in coverage(salons, universe, protocol, allow_google=True).items()
                                              if k != 'matches'}
    generic = generic_tokens(protocol)
    matched = {m['business_id'] for m in primary['matches']}
    report['_private'] = {
        'matches': primary['matches'],
        'unfiltered_matches': unfiltered['matches'],
        'near_misses': [nm for s in salons if s['business_id'] not in matched for nm in near_misses(s, universe, generic)],
        'unmatched_business_ids': sorted(s['business_id'] for s in salons if s['business_id'] not in matched),
    }
    return report
