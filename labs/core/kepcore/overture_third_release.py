"""KEP-DATA-018: preregistered third real Overture release comparison.

Offline and standard-library-only. Everything here was frozen before any
third-release data existed (protocol: sources/overture_third_release.json).
The network acquisition lives in scripts/capture_third_release.py and runs
only by an explicit manual trigger.

What this module measures are SOURCE RECORD trajectories across three
releases inside two fixed sampling cells. A record that disappears and comes
back is a publisher listing pattern, not a business that closed and reopened.
"""
from __future__ import annotations

from collections import Counter
from datetime import date
from hashlib import sha256
from math import sqrt
from pathlib import Path
from typing import Iterable
import json
import re

from .gers_region_probe import _bbox_intersects, validate_event
from .overture_archive_artifact import compare_source_records
from .overture_change_triage import _changed
from .overture_places import PILOT, canonical, check_release, valid_stac_catalog

STUDY = 'KEP-DATA-018'
ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / 'sources/overture_third_release.json'
# Frozen 2026-10-18, before the third release existed. Editing the protocol
# after seeing data must fail loudly, not silently change the study.
PROTOCOL_SHA256 = '254e38761aebc1744f710888cbc3bc23dc21129f11b20e5da280786f1350f7e4'
STAC_BASE = 'https://stac.overturemaps.org/'
MAX_CATALOG_BYTES = 200_000
CATEGORY_FIELDS = frozenset({'basic_category', 'taxonomy_primary'})
# M4's field list lives in the hashed protocol (m4_factual_fields), not here,
# so it cannot change after data arrives without failing load_protocol.
KNOWN_CHANGE_FIELDS = frozenset({'name', 'address', 'basic_category', 'taxonomy_primary',
                                 'operating_status', 'locality', 'country',
                                 'source_provenance', 'geometry', 'cell'})
CONFIDENCE_STEP = 0.05
_CATALOG_HREF = re.compile(r'^https://stac\.overturemaps\.org/([0-9]{4}-[0-9]{2}-[0-9]{2}\.[0-9]+)/catalog\.json$')


def load_protocol(path: str | Path = PROTOCOL_PATH, *,
                  expected_sha256: str = PROTOCOL_SHA256) -> dict:
    p = Path(path)
    if p.is_symlink() or not p.is_file() or not 0 < p.stat().st_size <= 32_000:
        raise ValueError('Missing or unsafe preregistered protocol')
    raw = p.read_bytes()
    if sha256(raw).hexdigest() != expected_sha256:
        raise ValueError('Preregistered DATA-018 protocol changed after freezing')
    protocol = json.loads(raw)
    if (protocol.get('study') != STUDY or protocol.get('research_only') is not True
            or protocol.get('consumer_display_approved') is not False
            or protocol.get('frozen_before_any_third_release_data') is not True
            or {k: tuple(v) for k, v in protocol['cells'].items()} != PILOT):
        raise ValueError('Protocol boundary or sampling cells changed')
    fields = protocol.get('m4_factual_fields')
    if (not isinstance(fields, list) or not fields or len(set(fields)) != len(fields)
            or not set(fields) <= KNOWN_CHANGE_FIELDS - CATEGORY_FIELDS):
        raise ValueError('M4 factual fields must be known, non-category change fields')
    return protocol


def check_candidate_release(release: str, protocol: dict) -> str:
    """Accept only a release inside the frozen window, after the predecessor."""
    check_release(release)
    window = protocol['accepted_release_window']
    day = date.fromisoformat(release[:10])
    if not (date.fromisoformat(window['earliest_release_date']) <= day
            <= date.fromisoformat(window['latest_release_date'])):
        raise ValueError(f'{release} is outside the preregistered third-release window')
    if release in protocol['reference_releases']:
        raise ValueError('The third release must differ from both reference releases')
    return release


def _catalog_release(href: object) -> str | None:
    match = _CATALOG_HREF.fullmatch(href) if isinstance(href, str) else None
    return match.group(1) if match else None


def verify_release_chain(root_raw: bytes, release_raw: bytes, *, release: str,
                         protocol: dict) -> dict:
    """STAC root must point at the requested release; record its predecessor.

    A prev link is publisher navigation evidence. It does not attest which
    baseline the changelog build compared against (see DATA-014).
    """
    check_candidate_release(release, protocol)
    root = valid_stac_catalog(root_raw, pinned=release)
    if not isinstance(release_raw, bytes) or not 0 < len(release_raw) <= MAX_CATALOG_BYTES:
        raise ValueError('Missing or oversized release catalog')
    cat = json.loads(release_raw)
    links = cat.get('links') if isinstance(cat, dict) else None
    if (not isinstance(links, list) or cat.get('type') != 'Catalog'
            or cat.get('id') != release or cat.get('release:version') != release):
        raise ValueError('Release catalog identity mismatch')
    rels = Counter(link.get('rel') for link in links if isinstance(link, dict))
    selfs = [l for l in links if isinstance(l, dict) and l.get('rel') == 'self']
    prevs = [l for l in links if isinstance(l, dict) and l.get('rel') == 'prev']
    if (len(selfs) != 1 or _catalog_release(selfs[0].get('href')) != release
            or rels['prev'] != 1):
        raise ValueError('Release catalog must have exactly one self and one prev link')
    places = STAC_BASE + release + '/places/catalog.json'
    if not any(isinstance(l, dict) and l.get('rel') == 'child' and l.get('href') == places
               for l in links):
        raise ValueError('Release catalog does not link a places theme')
    predecessor = _catalog_release(prevs[0].get('href'))
    if predecessor is None:
        raise ValueError('Unparseable predecessor link')
    expected = protocol['expected_predecessor']
    consecutive = predecessor == expected
    return {
        'release': release,
        'status': 'CONSECUTIVE_PAIR' if consecutive else 'REQUIRES_INTERMEDIATE_RELEASE',
        'observed_predecessor': predecessor,
        'expected_predecessor': expected,
        'regional_reconciliation_allowed': consecutive,
        'root_catalog_sha256': root['stac_sha256'],
        'release_catalog_sha256': sha256(release_raw).hexdigest(),
        'predecessor_evidence': 'STAC_PREV_LINK_NAVIGATION_ONLY',
        'changelog_build_baseline_publisher_attested': False,
    }


def wilson(successes: int, n: int, z: float = 1.96) -> dict:
    if type(successes) is not int or type(n) is not int or not 0 <= successes <= n:
        raise ValueError('Invalid binomial counts')
    if n == 0:
        return {'k': 0, 'n': 0, 'fraction': None, 'wilson95': None}
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return {'k': successes, 'n': n, 'fraction': round(p, 6),
            'wilson95': [round(max(0.0, centre - half), 6), round(min(1.0, centre + half), 6)]}


def _index(rows: Iterable[dict], label: str) -> dict[str, dict]:
    out = {}
    for row in rows:
        rid = row['overture_id']
        if rid in out:
            raise ValueError(f'Repeated Overture ID in {label}')
        if row.get('cell') not in PILOT:
            raise ValueError(f'Record outside preregistered cells in {label}')
        out[rid] = row
    if not out:
        raise ValueError(f'Empty {label} population')
    return out


def three_release_trajectories(first: list[dict], second: list[dict], third: list[dict], *,
                               schema_comparable: bool, protocol: dict | None = None) -> dict:
    """M1-M5 from the preregistered protocol. Aggregates only, never IDs."""
    if type(schema_comparable) is not bool:
        raise ValueError('Schema comparability must be explicit')
    factual = frozenset((protocol or load_protocol())['m4_factual_fields'])

    def _factual_change(x: dict, y: dict) -> bool:
        return bool(set(_changed(x, y)) & factual)
    a, b, c = _index(first, 'first'), _index(second, 'second'), _index(third, 'third')
    union = a.keys() | b.keys() | c.keys()
    pattern = Counter(''.join('1' if rid in s else '0' for s in (a, b, c)) for rid in union)
    names = {'111': 'listed_in_all_three', '110': 'no_longer_listed_in_third',
             '011': 'new_in_second_kept', '101': 'relisted_in_third',
             '100': 'removed_in_second_still_absent', '010': 'listed_only_in_second',
             '001': 'new_in_third'}
    trajectories = {names[k]: pattern.get(k, 0) for k in sorted(names)}
    if sum(trajectories.values()) != len(union):
        raise AssertionError('Exclusive trajectory accounting failed')

    stable = sorted(a.keys() & b.keys() & c.keys())
    persistence = Counter()
    reversal = Counter()
    for rid in stable:
        hop1, hop2 = _factual_change(a[rid], b[rid]), _factual_change(b[rid], c[rid])
        persistence[(hop1, hop2)] += 1
        c1, c2, c3 = a[rid]['confidence'], b[rid]['confidence'], c[rid]['confidence']
        if None in (c1, c2, c3):
            reversal['missing_confidence'] += 1
            continue
        d1, d2 = c2 - c1, c3 - c2
        if abs(d1) > CONFIDENCE_STEP:
            reversal['large_first_hop'] += 1
            if abs(d2) > CONFIDENCE_STEP and (d1 > 0) != (d2 > 0):
                reversal['reversed'] += 1

    delta = compare_source_records(list(b.values()), list(c.values()))
    if not schema_comparable:
        # Re-classify every ID with category fields blanked on both sides, so a
        # taxonomy migration cannot turn unchanged IDs into "revised" ones.
        raw_counts = delta['field_change_counts']
        blank = {k: None for k in CATEGORY_FIELDS}
        delta = compare_source_records([{**r, **blank} for r in b.values()],
                                       [{**r, **blank} for r in c.values()])
        delta['category_fields_excluded_technical_schema_review'] = {
            k: raw_counts[k] for k in sorted(CATEGORY_FIELDS) if k in raw_counts}
    return {
        'study': STUDY,
        'scope': 'two_fixed_sampling_cells_not_districts',
        'trajectory_counts': trajectories,
        'M1_relisting_after_removal': wilson(pattern.get('101', 0),
                                             pattern.get('101', 0) + pattern.get('100', 0)),
        'M2_transient_additions': wilson(pattern.get('010', 0),
                                         pattern.get('010', 0) + pattern.get('011', 0)),
        'M3_consecutive_source_delta': delta,
        'M4_revision_persistence': {
            'after_first_hop_revision': wilson(persistence[(True, True)],
                                               persistence[(True, True)] + persistence[(True, False)]),
            'without_first_hop_revision': wilson(persistence[(False, True)],
                                                 persistence[(False, True)] + persistence[(False, False)]),
            'fields_counted': sorted(factual),
            'field_list_source': 'protocol.m4_factual_fields',
        },
        'M5_confidence_reversal': {
            **wilson(reversal['reversed'], reversal['large_first_hop']),
            'threshold': CONFIDENCE_STEP,
            'missing_confidence_ids': reversal['missing_confidence'],
        },
        'category_semantics_comparable_second_to_third': schema_comparable,
        'relisting_is_business_reopening': False,
        'removal_is_business_closure': False,
        'physical_business_openings': None,
        'physical_business_closures': None,
        'consumer_publish': False,
    }


def _id_digest(ids: set[str]) -> str:
    return sha256(canonical(sorted(ids))).hexdigest()


def regional_membership_reconciliation(second: list[dict], third: list[dict],
                                       events: Iterable[tuple[str, dict]], *,
                                       chain: dict, capture_complete: bool) -> dict:
    """M6. Compare local cell membership changes with official regional events.

    `events` are (change_type, row) pairs for added/removed rows read from
    the third release's changelog. Only rows whose bbox touches a cell count.
    Output holds counts and ID-set digests, never raw IDs.
    """
    if type(capture_complete) is not bool:
        raise ValueError('Capture completeness must be explicit')
    old, new = _index(second, 'second'), _index(third, 'third')
    local_added, local_removed = new.keys() - old.keys(), old.keys() - new.keys()
    official = {'added': set(), 'removed': set()}
    scanned = 0
    for kind, row in events:
        scanned += 1
        if scanned > 1_000_000:
            raise ValueError('Unbounded regional observation set')
        if kind not in official:
            raise ValueError('Only added/removed rows belong to M6')
        rid = validate_event(row, kind)
        if any(_bbox_intersects(row['bbox'], box) for box in PILOT.values()):
            official[kind].add(rid)
    both = official['added'] & official['removed']
    allowed = chain.get('regional_reconciliation_allowed') is True
    status = ('ABSTAIN_REQUIRES_INTERMEDIATE_RELEASE' if not allowed
              else 'ABSTAIN_INCOMPLETE_CAPTURE' if not capture_complete
              else 'ABSTAIN_CONFLICTING_OFFICIAL_ROWS' if both
              else 'REGIONAL_SCOPE_RECONCILED')
    added_ok = len(local_added & official['added'])
    removed_ok = len(local_removed & official['removed'])
    counts = {
        'local_newly_listed': len(local_added),
        'local_no_longer_listed': len(local_removed),
        'official_regional_added': len(official['added']),
        'official_regional_removed': len(official['removed']),
        'conflicting_official_ids': len(both),
        'added_confirmed': added_ok,
        'removed_confirmed': removed_ok,
        'local_added_without_official_event': len(local_added - official['added']),
        'local_removed_without_official_event': len(local_removed - official['removed']),
        'official_added_missing_from_third_snapshot': len(official['added'] - new.keys()),
        'official_removed_still_in_third_snapshot': len(official['removed'] & new.keys()),
        'official_added_already_in_second_snapshot': len(official['added'] & old.keys()),
    }
    reconciled = status == 'REGIONAL_SCOPE_RECONCILED'
    total = len(local_added) + len(local_removed)
    return {
        'study': STUDY,
        'status': status,
        'scanned_rows': scanned,
        'counts': counts,
        'M6_regional_membership_agreement': (wilson(added_ok + removed_ok, total)
                                             if reconciled else None),
        'added_agreement': wilson(added_ok, len(local_added)) if reconciled else None,
        'removed_agreement': wilson(removed_ok, len(local_removed)) if reconciled else None,
        'id_set_sha256': {'local_added': _id_digest(local_added),
                          'local_removed': _id_digest(local_removed),
                          'official_added': _id_digest(official['added']),
                          'official_removed': _id_digest(official['removed'])},
        'predecessor': chain.get('observed_predecessor'),
        'predecessor_evidence': 'STAC_PREV_LINK_NAVIGATION_ONLY',
        'changelog_build_baseline_publisher_attested': False,
        'scope': 'bbox_intersecting_rows_only_not_global_id_union',
        'same_publisher_not_independent_evidence': True,
        'physical_business_openings': None,
        'physical_business_closures': None,
        'consumer_publish': False,
    }


def select_regional_groups(objects: list[dict], *, release: str, protocol: dict) -> dict:
    """Pick added/removed row groups whose footer bbox may touch a cell.

    Unknown statistics keep a group (conservative). An over-budget plan stops
    the run; it is never silently truncated to fit.
    """
    from .gers_access_cost import _interval, validate_objects
    gers = protocol['gers']
    kinds = tuple(gers['captured_change_types'])
    validate_objects(objects, (release,))
    if any(o['change_type'] not in kinds for o in objects):
        raise ValueError('Only preregistered change types may be planned')
    missing = set(kinds) - {o['change_type'] for o in objects}
    if missing:
        raise ValueError('Missing changelog partition; no empty-success assumption')
    selected, excluded = [], 0
    for obj in sorted(objects, key=lambda o: o['key']):
        for i, group in enumerate(obj['row_groups']):
            cols = {c['path']: c for c in group['columns']}
            bb = {k: _interval(cols['bbox.' + k]) for k in ('xmin', 'xmax', 'ymin', 'ymax')}
            unknown = any(v is None for v in bb.values())
            possible = unknown or any(
                bb['xmin'][0] <= box[2] and bb['xmax'][1] >= box[0]
                and bb['ymin'][0] <= box[3] and bb['ymax'][1] >= box[1]
                for box in PILOT.values())
            if not possible:
                excluded += 1
                continue
            selected.append({
                'key': obj['key'], 'etag': obj['etag'], 'object_bytes': obj['size'],
                'footer_sha256': obj['footer_sha256'], 'row_group': i,
                'change_type': obj['change_type'], 'rows': group['rows'],
                'estimated_compressed_column_bytes': sum(c['compressed_bytes'] for c in group['columns']),
                'metadata_statistics_unknown': unknown,
            })
    total = sum(x['estimated_compressed_column_bytes'] for x in selected)
    rows = sum(x['rows'] for x in selected)
    if total > gers['max_event_body_bytes'] or rows > gers['max_event_rows_scanned']:
        raise ValueError('Regional plan exceeds the preregistered read budget; redesign, do not truncate')
    return {
        'study': STUDY, 'release': release, 'selected': selected,
        'selected_row_groups': len(selected), 'excluded_row_groups': excluded,
        'selected_by_change_type': dict(Counter(x['change_type'] for x in selected)),
        'estimated_candidate_column_bytes': total, 'candidate_rows': rows,
        'scope': gers['scope'], 'complete_id_union_scan': False,
    }
