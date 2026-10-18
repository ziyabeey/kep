"""KEP-DATA-018: manual third Overture release capture and offline comparison.

Default run makes no network calls. Network access needs an explicit
subcommand, --fetch, a research confirmation and a fresh output directory:

  places   STAC chain check + the two preregistered cells via overturemaps CLI
  gers     bounded regional added/removed rows from the release's changelog
  compare  OFFLINE: Aug/Sep pinned archives + the captured third release

Nothing here publishes to consumers, calls a model or labels a business.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys
from time import perf_counter
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kepcore.gers_region_probe import RangeBudget
from kepcore.overture_places import PILOT, canonical
from kepcore.overture_third_release import (
    STUDY, check_candidate_release, load_protocol, regional_membership_reconciliation,
    select_regional_groups, three_release_trajectories, verify_release_chain,
)

S3 = 'https://overturemaps-us-west-2.s3.us-west-2.amazonaws.com/'
STAC_ROOT = 'https://stac.overturemaps.org/catalog.json'
ARROW_VERSION = '21.0.0'
ORIGINS = {'captured_overture_cli': 'REAL_OVERTURE_CAPTURE',
           'synthetic_rehearsal': 'SYNTHETIC_REHEARSAL_NOT_A_REAL_RELEASE'}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def fetch_catalog(url: str, *, maximum: int = 200_000) -> bytes:
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != 'https' or parsed.hostname != 'stac.overturemaps.org'
            or parsed.username or parsed.password or parsed.port not in {None, 443}):
        raise ValueError('Unapproved catalog endpoint')
    req = urllib.request.Request(url, headers={'User-Agent': 'KEP-Core-Research/0.1',
                                               'Cache-Control': 'no-cache'})
    with urllib.request.build_opener(NoRedirect()).open(req, timeout=15) as response:
        if response.status != 200 or response.geturl() != url:
            raise ValueError('Unexpected catalog response or redirect')
        body = response.read(maximum + 1)
    if not 0 < len(body) <= maximum:
        raise ValueError('Catalog empty or too large')
    return body


def _fresh(path: Path) -> Path:
    if path.is_symlink() or path.exists():
        raise ValueError('Research output must be a fresh directory')
    path.mkdir(parents=True)
    return path


def capture_chain(release: str, protocol: dict, output: Path) -> dict:
    root_raw = fetch_catalog(STAC_ROOT)
    release_raw = fetch_catalog(f'https://stac.overturemaps.org/{release}/catalog.json')
    chain = verify_release_chain(root_raw, release_raw, release=release, protocol=protocol)
    (output / 'stac_root.json').write_bytes(root_raw)
    (output / 'stac_release.json').write_bytes(release_raw)
    chain['retrieved_at'] = datetime.now(timezone.utc).isoformat()
    (output / 'release_chain.json').write_bytes(canonical(chain))
    return chain


def run_places(release: str, output: Path) -> dict:
    protocol = load_protocol()
    check_candidate_release(release, protocol)
    out = _fresh(output)
    chain = capture_chain(release, protocol, out)
    from scripts.overture_istanbul import execute
    result = execute(output=out / 'places', inputs=None, fetch=True, seed_file=None,
                     release=release)
    manifest = json.loads((out / 'places' / 'manifest.json').read_bytes())
    receipt = {'study': STUDY, 'release': release, 'origin': 'captured_overture_cli',
               'chain': chain, 'rows_accepted': result['rows_accepted'],
               'normalized_sha256': manifest['normalized_sha256'],
               'population_sha256': manifest['population_sha256'],
               'downloaded_at_utc': manifest['acquisition']['downloaded_at_utc'],
               'consumer_publish': False, 'human_verified_labels': 0}
    (out / 'places_receipt.json').write_bytes(canonical(receipt))
    return receipt


def parse_listing(raw: bytes, *, prefix: str, release: str, kind: str) -> list[dict]:
    """Strict S3 ListObjectsV2 parse; truncated or foreign keys stop the run."""
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise ValueError('Unsafe source inventory')
    ns = {'s': 'http://s3.amazonaws.com/doc/2006-03-01/'}
    doc = ET.fromstring(raw)
    if (doc.findtext('s:IsTruncated', namespaces=ns) != 'false'
            or doc.findtext('s:Prefix', namespaces=ns) != prefix):
        raise ValueError('Incomplete or wrong source listing')
    items = []
    for e in doc.findall('s:Contents', ns):
        key = e.findtext('s:Key', namespaces=ns)
        etag = e.findtext('s:ETag', namespaces=ns)
        size_text = e.findtext('s:Size', namespaces=ns) or ''
        if (not key or not key.startswith(prefix) or '/' in key[len(prefix):]
                or not key.endswith('.parquet') or '..' in key or not size_text.isdigit()
                or int(size_text) <= 12 or not etag or not etag.startswith('"')
                or not etag.endswith('"')):
            raise ValueError('Invalid public object metadata')
        items.append({'key': key, 'release': release, 'change_type': kind, 'etag': etag,
                      'size': int(size_text),
                      'last_modified': e.findtext('s:LastModified', namespaces=ns),
                      'listing_sha256': sha256(raw).hexdigest()})
    if not items:
        raise ValueError('Missing change partition; no empty-success assumption')
    return items


def _event_reader(release: str, protocol: dict):
    from scripts.probe_gers_region import RemoteRanges

    class ThirdReleaseRanges(RemoteRanges):
        def __init__(self):
            self.release = release
            self.budget = RangeBudget(limit=protocol['gers']['max_event_body_bytes'],
                                      requests=protocol['gers']['max_event_requests'])
            self.bytes_read = 0
            self.opener = urllib.request.build_opener(NoRedirect())
            self.failed = False
    return ThirdReleaseRanges()


def run_gers(release: str, output: Path) -> dict:
    import pyarrow as pa
    import pyarrow.parquet as pq
    if pa.__version__ != ARROW_VERSION:
        raise ValueError('Pinned optional Arrow version required')
    from scripts.gers_footer_study import Reader, decode_footer
    from scripts.probe_gers_region import RemoteFile, source_item
    protocol = load_protocol()
    check_candidate_release(release, protocol)
    out = _fresh(output)
    chain = capture_chain(release, protocol, out)
    gers = protocol['gers']
    receipt = {'study': STUDY, 'release': release, 'origin': 'captured_public_GERS_rows',
               'status': 'INCOMPLETE_EVENT_CAPTURE', 'chain': chain,
               'captured_change_types': gers['captured_change_types'],
               'scope': gers['scope'], 'complete_for_all_union_ids': False,
               'consumer_publish': False, 'physical_business_openings': None,
               'physical_business_closures': None, 'independent_human_labels': 0}
    footer_reader = Reader()
    events_reader = _event_reader(release, protocol)
    began = perf_counter()
    rows_read = 0
    regional = []
    try:
        objects = []
        for kind in gers['captured_change_types']:
            prefix = gers['changelog_prefix_template'].format(release=release, kind=kind)
            query = urllib.parse.urlencode({'list-type': '2', 'prefix': prefix, 'max-keys': '200'})
            raw, _, status = footer_reader.read(S3 + '?' + query, maximum=256 * 1024)
            if status != 200:
                raise ValueError('Unsuccessful source inventory')
            for item in parse_listing(raw, prefix=prefix, release=release, kind=kind):
                if footer_reader.range(item, 0, 3) != b'PAR1':
                    raise ValueError('Unsupported Parquet header')
                from kepcore.gers_access_cost import footer_span
                tail = footer_reader.range(item, item['size'] - 8, item['size'] - 1)
                start, end = footer_span(tail, item['size'])
                footer = footer_reader.range(item, start, end) + tail
                objects.append(decode_footer(item, footer, (release,)))
        plan = select_regional_groups(objects, release=release, protocol=protocol)
        receipt['plan'] = {k: v for k, v in plan.items() if k != 'selected'}
        receipt['footer_sha256'] = sorted(o['footer_sha256'] for o in objects)
        for item in plan['selected']:
            remote = RemoteFile(events_reader, source_item(item))
            parquet = pq.ParquetFile(remote, pre_buffer=False)
            if parquet.metadata.row_group(item['row_group']).num_rows != item['rows']:
                raise ValueError('Row group changed between footer and data read')
            table = parquet.read_row_group(item['row_group'], columns=gers['projected_columns'],
                                           use_threads=False)
            if table.num_rows != item['rows']:
                raise ValueError('Partial column row-group read')
            for batch in table.to_batches(max_chunksize=8192):
                for row in batch.to_pylist():
                    rows_read += 1
                    bb = row['bbox']
                    if any(bb['xmin'] <= box[2] and bb['xmax'] >= box[0]
                           and bb['ymin'] <= box[3] and bb['ymax'] >= box[1]
                           for box in PILOT.values()):
                        regional.append({'change_type': item['change_type'], **row})
            remote.close()
        if rows_read != plan['candidate_rows']:
            raise ValueError('Not every selected row group was examined')
        receipt['status'] = 'REGIONAL_ROWS_CAPTURED_NOT_COMPLETE_ID_UNION'
    except Exception as exc:
        receipt['failure_type'] = type(exc).__name__
        receipt['failure_detail'] = str(exc)[:1200]
    regional.sort(key=lambda r: (r['change_type'], r['id']))
    events_raw = canonical(regional)
    (out / 'gers_regional_events.json').write_bytes(events_raw)
    receipt.update(observed_at=datetime.now(timezone.utc).isoformat(),
                   seconds=round(perf_counter() - began, 6), scanned_rows=rows_read,
                   regional_rows=len(regional), events_sha256=sha256(events_raw).hexdigest(),
                   footer_body_bytes=footer_reader.body_bytes,
                   footer_requests=footer_reader.budget.requests,
                   event_body_bytes=events_reader.bytes_read,
                   event_reserved_bytes=events_reader.budget.bytes_reserved,
                   event_requests=events_reader.budget.requests,
                   byte_scope='application response bodies only; headers, TLS and package installs excluded')
    (out / 'gers_receipt.json').write_bytes(canonical(receipt))
    return receipt


def _read_bytes(path: Path, limit: int) -> bytes:
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= limit:
        raise ValueError(f'Missing or unsafe research file: {path.name}')
    return path.read_bytes()


def _read_json(path: Path, limit: int) -> tuple[dict | list, bytes]:
    raw = _read_bytes(path, limit)
    obj = json.loads(raw)
    if canonical(obj) != raw:
        raise ValueError(f'Noncanonical research file: {path.name}')
    return obj, raw


def compare(places_dir: Path, *, publisher_schema_version: str, gers_dir: Path | None) -> dict:
    """OFFLINE. Same-run hashes are internal consistency, not upstream attestation."""
    from kepcore.gers_reconciliation import load_pinned_pair
    from kepcore.overture_delta import load_operator_research_bundle
    protocol = load_protocol()
    receipt, _ = _read_json(places_dir / 'places_receipt.json', 200_000)
    release = check_candidate_release(receipt['release'], protocol)
    if receipt.get('origin') not in ORIGINS:
        raise ValueError('Unknown third-release origin')
    chain = receipt['chain']
    root_raw = _read_bytes(places_dir / 'stac_root.json', 200_000)
    release_raw = _read_bytes(places_dir / 'stac_release.json', 200_000)
    if verify_release_chain(root_raw, release_raw, release=release, protocol=protocol)['status'] != chain['status']:
        raise ValueError('Stored release chain does not replay')
    third = load_operator_research_bundle(places_dir / 'places', expected_release=release,
                                          expected_normalized_sha256=receipt['normalized_sha256'],
                                          expected_observed_at=receipt['downloaded_at_utc'])
    first, second = load_pinned_pair()
    schema_ok = publisher_schema_version == protocol['reference_schema_version']
    report = {'study': STUDY, 'release': release, 'chain': chain,
              'third_origin': ORIGINS[receipt['origin']],
              'publisher_schema_version': publisher_schema_version,
              'third_population_n': len(third.records),
              'third_population_sha256': third.population_sha256,
              'third_hash_source': 'SAME_RUN_RECEIPT_NOT_INDEPENDENT',
              'trajectories': three_release_trajectories(list(first.records), list(second.records),
                                                         list(third.records),
                                                         schema_comparable=schema_ok),
              'regional_gers': None, 'research_only': True, 'consumer_publish': False}
    if gers_dir is not None:
        g, _ = _read_json(gers_dir / 'gers_receipt.json', 200_000)
        events, events_raw = _read_json(gers_dir / 'gers_regional_events.json', 16_000_000)
        if g.get('release') != release or g.get('events_sha256') != sha256(events_raw).hexdigest():
            raise ValueError('GERS capture does not belong to this release or was altered')
        complete = g.get('status') == 'REGIONAL_ROWS_CAPTURED_NOT_COMPLETE_ID_UNION'
        pairs = ((e['change_type'], {k: e[k] for k in ('id', 'bbox', 'columns_changed')})
                 for e in events)
        report['regional_gers'] = regional_membership_reconciliation(
            list(second.records), list(third.records), pairs, chain=chain, capture_complete=complete)
        report['regional_gers']['capture'] = {k: g.get(k) for k in (
            'status', 'scanned_rows', 'regional_rows', 'event_body_bytes', 'event_requests',
            'footer_body_bytes', 'failure_type')}
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command')
    for name, confirmation in (('places', 'RESEARCH_ONLY'), ('gers', 'REGIONAL_MEMBERSHIP_16MIB')):
        p = sub.add_parser(name)
        p.add_argument('--fetch', action='store_true', required=True)
        p.add_argument('--research-confirmation', required=True, choices=[confirmation])
        p.add_argument('--release', required=True)
        p.add_argument('--output', type=Path, required=True)
    c = sub.add_parser('compare')
    c.add_argument('--places-dir', type=Path, required=True)
    c.add_argument('--gers-dir', type=Path)
    c.add_argument('--publisher-schema-version', required=True,
                   help='From the release notes, e.g. v2.0.0; a different value excludes category fields')
    c.add_argument('--output', type=Path, help='New file for the aggregate report')
    args = parser.parse_args()
    if args.command is None:
        protocol = load_protocol()
        print(json.dumps({'status': 'OFFLINE_DEFAULT', 'network_calls': 0, 'study': STUDY,
                          'planned_release': protocol['planned_release'],
                          'expected_predecessor': protocol['expected_predecessor']},
                         ensure_ascii=False, indent=2))
        return
    if args.command == 'places':
        result = run_places(args.release, args.output)
    elif args.command == 'gers':
        result = run_gers(args.release, args.output)
        if result['status'] != 'REGIONAL_ROWS_CAPTURED_NOT_COMPLETE_ID_UNION':
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
            raise SystemExit(3)
    else:
        result = compare(args.places_dir, publisher_schema_version=args.publisher_schema_version,
                         gers_dir=args.gers_dir)
        if args.output is not None:
            if args.output.exists() or args.output.is_symlink():
                parser.error('Report output must be a new file')
            args.output.write_bytes(canonical(result))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
