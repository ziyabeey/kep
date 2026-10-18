"""DATA-018 dress rehearsal: run the third-release pipeline on a SYNTHETIC release.

The fake release is derived deterministically from the pinned real September
archive plus a few August-only rows. Its numbers say nothing about Istanbul;
they only prove the offline compare path works end to end before 2026-10-21.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import uuid

from kepcore.gers_reconciliation import load_pinned_pair
from kepcore.overture_places import PILOT, canonical

RELEASE = '2026-10-21.0'
OBSERVED_AT = '2026-10-22T06:00:00+00:00'
PREV = 'https://stac.overturemaps.org/2026-09-23.1/catalog.json'


def stac_pair(release: str = RELEASE, prev_href: str = PREV,
              schema_version: str | None = None) -> tuple[bytes, bytes]:
    root = {'type': 'Catalog', 'stac_version': '1.1.0', 'id': 'overture-releases', 'latest': release,
            'links': [{'rel': 'child', 'latest': True,
                       'href': f'https://stac.overturemaps.org/{release}/catalog.json'}]}
    cat = {'type': 'Catalog', 'stac_version': '1.1.0', 'id': release, 'release:version': release,
           'links': [{'rel': 'self', 'href': f'https://stac.overturemaps.org/{release}/catalog.json'},
                     {'rel': 'child', 'href': f'https://stac.overturemaps.org/{release}/places/catalog.json'},
                     {'rel': 'prev', 'href': prev_href}]}
    if schema_version is not None:
        cat['schema:version'] = schema_version
    return canonical(root), canonical(cat)


def synthetic_third(first: list[dict], second: list[dict]) -> list[dict]:
    """Deterministic: drop 1/40, rename 1/50, raise confidence 1/7, relist 1/3 of
    August-only IDs, and add 30 invented IDs inside the cells."""
    rows = []
    for i, row in enumerate(sorted(second, key=lambda r: r['overture_id'])):
        if i % 40 == 0:
            continue
        row = dict(row)
        if i % 50 == 1:
            row['name'] = (row['name'] or '') + ' (sentetik)'
        if i % 7 == 2 and row['confidence'] is not None:
            row['confidence'] = round(min(1.0, row['confidence'] + 0.1), 6)
        rows.append(row)
    sep_ids = {r['overture_id'] for r in second}
    aug_only = sorted((r for r in first if r['overture_id'] not in sep_ids),
                      key=lambda r: r['overture_id'])
    rows.extend(dict(r) for r in aug_only[::3])
    template = dict(sorted(second, key=lambda r: r['overture_id'])[1])
    for n in range(30):
        cell = sorted(PILOT)[n % 2]
        west, south, east, north = PILOT[cell]
        rows.append({**template, 'overture_id': str(uuid.uuid5(uuid.NAMESPACE_URL, f'kep-data-018/{n}')),
                     'name': f'Sentetik yer {n}', 'cell': cell,
                     'lon': round(west + (east - west) * (n + 1) / 32, 6),
                     'lat': round(south + (north - south) * (n + 1) / 32, 6)})
    return sorted(rows, key=lambda r: r['overture_id'])


def write_places_dir(target: Path, rows: list[dict], *, prev_href: str = PREV,
                     schema_version: str | None = None,
                     publisher_schema_version: str = 'v2.0.0') -> None:
    places = target / 'places'
    places.mkdir(parents=True)
    data = canonical({'dataset': 'KEP-DATA-001', 'release': RELEASE, 'study_only': True,
                      'records': rows})
    (places / 'places_minimal.json').write_bytes(data)
    normalized = sha256(data).hexdigest()
    population = sha256(canonical(rows)).hexdigest()
    manifest = {'study': 'KEP-DATA-001', 'pinned_release': RELEASE,
                'schema': 'Overture Places schema 2.0 (taxonomy / basic_category)',
                'research_only': True, 'consumer_display_approved': False,
                'license_evidence_url': 'https://docs.overturemaps.org/attribution/',
                'sample_cell_bounds_not_district_boundary': {k: list(v) for k, v in PILOT.items()},
                'acquisition': {'method': 'manual_overturemaps_cli_stac_pinned',
                                'downloaded_at_utc': OBSERVED_AT,
                                'stac_catalog_sha256_before': '0' * 64,
                                'stac_catalog_sha256_after': '0' * 64,
                                'synthetic_rehearsal': True},
                'source_files': [{'cell': c, 'sha256': '0' * 64, 'bytes': 1} for c in sorted(PILOT)],
                'normalized_sha256': normalized, 'population_sha256': population,
                'audit': {'rows_read': len(rows) + 3, 'accepted': len(rows),
                          'duplicate_identical_ids': 0, 'rejected': {'outside_sampling_cell': 3}},
                'human_verified_labels': 0, 'no_automatic_entity_merge': True}
    (places / 'manifest.json').write_bytes(canonical(manifest))
    root, cat = stac_pair(prev_href=prev_href, schema_version=schema_version)
    (target / 'stac_root.json').write_bytes(root)
    (target / 'stac_release.json').write_bytes(cat)
    from kepcore.overture_third_release import load_protocol, verify_release_chain
    chain = verify_release_chain(root, cat, release=RELEASE, protocol=load_protocol())
    receipt = {'study': 'KEP-DATA-018', 'release': RELEASE, 'origin': 'synthetic_rehearsal',
               'chain': chain, 'rows_accepted': len(rows), 'normalized_sha256': normalized,
               'publisher_schema_version': publisher_schema_version,
               'stac_schema_version': schema_version,
               'population_sha256': population, 'downloaded_at_utc': OBSERVED_AT,
               'consumer_publish': False, 'human_verified_labels': 0}
    (target / 'places_receipt.json').write_bytes(canonical(receipt))


def write_gers_dir(target: Path, second: list[dict], third: list[dict], *, complete: bool = True,
                   prev_href: str = PREV) -> None:
    target.mkdir(parents=True)
    old = {r['overture_id']: r for r in second}
    new = {r['overture_id']: r for r in third}

    def ev(kind, row):
        x, y = row['lon'], row['lat']
        return {'change_type': kind, 'id': row['overture_id'], 'columns_changed': None,
                'bbox': {'xmin': x, 'xmax': x, 'ymin': y, 'ymax': y}}
    added = [ev('added', new[r]) for r in sorted(new.keys() - old.keys())][3:]
    removed = [ev('removed', old[r]) for r in sorted(old.keys() - new.keys())][2:]
    outside = {'change_type': 'added', 'id': str(uuid.uuid5(uuid.NAMESPACE_URL, 'kep-data-018/outside')),
               'columns_changed': None, 'bbox': {'xmin': 30.5, 'xmax': 30.5, 'ymin': 40.0, 'ymax': 40.0}}
    events = sorted(added + removed + [outside], key=lambda e: (e['change_type'], e['id']))
    raw = canonical(events)
    (target / 'gers_regional_events.json').write_bytes(raw)
    from kepcore.overture_third_release import load_protocol, verify_release_chain
    root, cat = stac_pair(prev_href=prev_href)
    chain = verify_release_chain(root, cat, release=RELEASE, protocol=load_protocol())
    receipt = {'study': 'KEP-DATA-018', 'release': RELEASE, 'origin': 'synthetic_rehearsal',
               'chain': chain,
               'status': ('REGIONAL_ROWS_CAPTURED_NOT_COMPLETE_ID_UNION' if complete
                          else 'INCOMPLETE_EVENT_CAPTURE'),
               'events_sha256': sha256(raw).hexdigest(), 'scanned_rows': len(events),
               'regional_rows': len(events), 'event_body_bytes': 0, 'event_requests': 0,
               'footer_body_bytes': 0, 'failure_type': None}
    (target / 'gers_receipt.json').write_bytes(canonical(receipt))


def rehearse() -> dict:
    from scripts.capture_third_release import compare
    first, second = load_pinned_pair()
    third = synthetic_third(list(first.records), list(second.records))
    with TemporaryDirectory(prefix='kep-data-018-rehearsal-') as tmp:
        root = Path(tmp)
        write_places_dir(root / 'run', third)
        write_gers_dir(root / 'gers', list(second.records), third)
        return compare(root / 'run', gers_dir=root / 'gers')


if __name__ == '__main__':
    print(json.dumps(rehearse(), ensure_ascii=False, indent=2, sort_keys=True))
