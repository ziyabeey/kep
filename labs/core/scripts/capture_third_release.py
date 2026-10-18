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
import os
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
    PROTOCOL_SHA256, STUDY, check_candidate_release, load_protocol,
    regional_membership_reconciliation, select_regional_groups, three_release_trajectories,
    verify_release_chain,
)

S3 = 'https://overturemaps-us-west-2.s3.us-west-2.amazonaws.com/'
STAC_ROOT = 'https://stac.overturemaps.org/catalog.json'
ARROW_VERSION = '21.0.0'
ORIGINS = {'captured_overture_cli': 'REAL_OVERTURE_CAPTURE',
           'synthetic_rehearsal': 'SYNTHETIC_REHEARSAL_NOT_A_REAL_RELEASE'}
GERS_ORIGIN_FOR = {'captured_overture_cli': 'captured_public_GERS_rows',
                   'synthetic_rehearsal': 'synthetic_rehearsal'}


def _provenance() -> dict:
    """Which frozen protocol and which code commit produced a capture."""
    return {'protocol_sha256': PROTOCOL_SHA256, 'code_commit': os.environ.get('GITHUB_SHA')}


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


def check_schema_against_stac(release_raw: bytes, publisher_schema_version: str) -> str | None:
    """Operator input must agree with STAC schema:version when STAC has one."""
    stac_schema = json.loads(release_raw).get('schema:version')
    if stac_schema is not None and _schema_core(stac_schema) != _schema_core(publisher_schema_version):
        raise ValueError(f'Operator schema {publisher_schema_version} contradicts STAC schema:version {stac_schema}')
    return stac_schema


def run_places(release: str, output: Path, *, publisher_schema_version: str) -> dict:
    protocol = load_protocol()
    check_candidate_release(release, protocol)
    _schema_core(publisher_schema_version)
    out = _fresh(output)
    chain = capture_chain(release, protocol, out)
    # Stop before any Places data is read if the operator's schema is wrong.
    stac_schema = check_schema_against_stac((out / 'stac_release.json').read_bytes(),
                                            publisher_schema_version)
    from scripts.overture_istanbul import execute
    result = execute(output=out / 'places', inputs=None, fetch=True, seed_file=None,
                     release=release)
    manifest = json.loads((out / 'places' / 'manifest.json').read_bytes())
    receipt = {'study': STUDY, 'release': release, 'origin': 'captured_overture_cli',
               'chain': chain, 'rows_accepted': result['rows_accepted'],
               'publisher_schema_version': publisher_schema_version,
               'stac_schema_version': stac_schema,
               'normalized_sha256': manifest['normalized_sha256'],
               'population_sha256': manifest['population_sha256'],
               'downloaded_at_utc': manifest['acquisition']['downloaded_at_utc'],
               'consumer_publish': False, 'human_verified_labels': 0, **_provenance()}
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
    from kepcore.gers_access_cost import BodyBudget
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
               'physical_business_closures': None, 'independent_human_labels': 0,
               **_provenance()}
    footer_reader = Reader()
    footer_reader.budget = BodyBudget(gers['max_footer_body_bytes'])
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


def _schema_core(version: object) -> str:
    if not isinstance(version, str) or not version.strip():
        raise ValueError('Schema version must be a non-empty string such as v2.0.0')
    v = version.strip()
    return v[1:] if v.startswith('v') else v


def normalization_audit(manifest: dict, accepted: int) -> dict:
    """Records dropped by the normalizer would masquerade as 'no longer listed'."""
    audit = manifest.get('audit') if isinstance(manifest, dict) else None
    if not isinstance(audit, dict):
        raise ValueError('Third-release manifest lacks its normalization audit')
    rejected = audit.get('rejected')
    if (not isinstance(rejected, dict)
            or any(not isinstance(k, str) or type(v) is not int or v < 0 for k, v in rejected.items())
            or audit.get('accepted') != accepted
            or audit.get('rows_read') != accepted + audit.get('duplicate_identical_ids', -1)
            + sum(rejected.values())):
        raise ValueError('Third-release normalization audit does not add up')
    in_cell = {k: v for k, v in sorted(rejected.items()) if k != 'outside_sampling_cell' and v}
    return {'rows_read': audit['rows_read'], 'accepted': accepted,
            'duplicate_identical_ids': audit['duplicate_identical_ids'],
            'rejected': dict(sorted(rejected.items())),
            'in_cell_rejections': sum(in_cell.values()), 'in_cell_rejection_reasons': in_cell}


def _regional_abstain(reason: str, status: str = 'ABSTAIN_GERS_CAPTURE_INVALID') -> dict:
    return {'study': STUDY, 'status': status, 'reason': reason[:300],
            'M6_regional_membership_agreement': None, 'added_agreement': None,
            'removed_agreement': None, 'physical_business_openings': None,
            'physical_business_closures': None, 'consumer_publish': False}


def _regional(gers_dir: Path, *, release: str, receipt: dict, chain: dict,
              second: list[dict], third: list[dict]) -> dict:
    g, _ = _read_json(gers_dir / 'gers_receipt.json', 200_000)
    if not isinstance(g, dict):
        raise ValueError('Malformed GERS receipt')
    if g.get('protocol_sha256') != PROTOCOL_SHA256:
        raise ValueError('GERS capture was made under another protocol version')
    events, events_raw = _read_json(gers_dir / 'gers_regional_events.json', 16_000_000)
    if g.get('release') != release or g.get('events_sha256') != sha256(events_raw).hexdigest():
        raise ValueError('GERS capture does not belong to this release or was altered')
    if GERS_ORIGIN_FOR.get(receipt['origin']) != g.get('origin'):
        raise ValueError('GERS capture origin does not match the Places capture origin')
    g_chain = g.get('chain') if isinstance(g.get('chain'), dict) else {}
    if g_chain.get('observed_predecessor') != chain['observed_predecessor']:
        raise ValueError('GERS and Places captures saw different release predecessors')
    if not isinstance(events, list) or any(not isinstance(e, dict) for e in events):
        raise ValueError('Malformed GERS event file')
    complete = g.get('status') == 'REGIONAL_ROWS_CAPTURED_NOT_COMPLETE_ID_UNION'
    pairs = [(e.get('change_type'), {k: e.get(k) for k in ('id', 'bbox', 'columns_changed')})
             for e in events]
    result = regional_membership_reconciliation(second, third, pairs, chain=chain,
                                                capture_complete=complete)
    result['capture'] = {k: g.get(k) for k in (
        'status', 'scanned_rows', 'regional_rows', 'event_body_bytes', 'event_requests',
        'footer_body_bytes', 'failure_type', 'failure_detail', 'code_commit')}
    return result


def compare(places_dir: Path, *, gers_dir: Path | None,
            publisher_schema_version: str | None = None) -> dict:
    """OFFLINE. Same-run hashes are internal consistency, not upstream attestation."""
    from kepcore.gers_reconciliation import load_pinned_pair
    from kepcore.overture_delta import load_operator_research_bundle
    protocol = load_protocol()
    receipt, _ = _read_json(places_dir / 'places_receipt.json', 200_000)
    if not isinstance(receipt, dict):
        raise ValueError('Malformed Places receipt')
    release = check_candidate_release(receipt['release'], protocol)
    if receipt.get('origin') not in ORIGINS:
        raise ValueError('Unknown third-release origin')
    if receipt.get('protocol_sha256') != PROTOCOL_SHA256:
        raise ValueError('Places capture was made under another protocol version')
    chain = receipt['chain']
    root_raw = _read_bytes(places_dir / 'stac_root.json', 200_000)
    release_raw = _read_bytes(places_dir / 'stac_release.json', 200_000)
    replay = verify_release_chain(root_raw, release_raw, release=release, protocol=protocol)
    if replay != {k: v for k, v in chain.items() if k != 'retrieved_at'}:
        raise ValueError('Stored release chain does not replay')
    recorded = receipt.get('publisher_schema_version')
    _schema_core(recorded)
    if publisher_schema_version is not None and _schema_core(publisher_schema_version) != _schema_core(recorded):
        raise ValueError(f'Schema {publisher_schema_version} differs from {recorded} recorded at capture; '
                         'the capture-time value is fixed')
    stac_schema = check_schema_against_stac(release_raw, recorded)
    if receipt.get('stac_schema_version') != stac_schema:
        raise ValueError('Receipt STAC schema does not match the stored catalog')
    publisher_schema_version = recorded
    schema_ok = _schema_core(recorded) == _schema_core(protocol['reference_schema_version'])
    third = load_operator_research_bundle(places_dir / 'places', expected_release=release,
                                          expected_normalized_sha256=receipt['normalized_sha256'],
                                          expected_observed_at=receipt['downloaded_at_utc'])
    manifest, _ = _read_json(places_dir / 'places' / 'manifest.json', 1_000_000)
    synthetic = (manifest.get('acquisition') or {}).get('synthetic_rehearsal') is True
    if synthetic != (receipt['origin'] == 'synthetic_rehearsal'):
        raise ValueError('Receipt origin contradicts the acquisition manifest')
    audit = normalization_audit(manifest, len(third.records))
    first, second = load_pinned_pair()
    report = {'study': STUDY, 'release': release, 'chain': chain,
              'third_origin': ORIGINS[receipt['origin']],
              'publisher_schema_version': publisher_schema_version,
              'stac_schema_version': stac_schema,
              'category_semantics_comparable': schema_ok,
              'third_population_n': len(third.records),
              'third_population_sha256': third.population_sha256,
              'third_hash_source': 'SAME_RUN_RECEIPT_NOT_INDEPENDENT',
              'protocol_sha256': PROTOCOL_SHA256,
              'capture_code_commit': receipt.get('code_commit'),
              # None outside GitHub Actions: an offline re-run is visible as one.
              'compare_code_commit': os.environ.get('GITHUB_SHA'),
              'preregistration_note': protocol['preregistration_note'],
              'third_normalization_audit': audit,
              'status': 'COMPARED', 'trajectories': None,
              'regional_gers': None, 'research_only': True, 'consumer_publish': False}
    if audit['in_cell_rejections']:
        report['status'] = 'ABSTAIN_NORMALIZATION_REJECTED_IN_CELL_RECORDS'
        return report
    report['trajectories'] = three_release_trajectories(
        list(first.records), list(second.records), list(third.records),
        schema_comparable=schema_ok, protocol=protocol)
    # A missing or bad GERS capture must not cost the one-shot M1-M5 report,
    # and M6 must never be silently empty: it always carries a status.
    receipt_path = None if gers_dir is None else gers_dir / 'gers_receipt.json'
    if receipt_path is None or not (receipt_path.is_file() or receipt_path.is_symlink()):
        report['regional_gers'] = _regional_abstain(
            'No GERS capture receipt (step skipped or failed before writing one)',
            status='ABSTAIN_GERS_CAPTURE_MISSING')
        return report
    try:
        report['regional_gers'] = _regional(gers_dir, release=release, receipt=receipt,
                                            chain=chain, second=list(second.records),
                                            third=list(third.records))
    except (ValueError, KeyError, TypeError, RecursionError, ArithmeticError) as exc:
        report['regional_gers'] = _regional_abstain(f'{type(exc).__name__}: {exc}')
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
        if name == 'places':
            p.add_argument('--publisher-schema-version', required=True,
                           help='From the release notes, e.g. v2.0.0; recorded in the receipt')
    c = sub.add_parser('compare')
    c.add_argument('--places-dir', type=Path, required=True)
    c.add_argument('--gers-dir', type=Path,
                   help='GERS capture directory; if absent, M6 abstains as ABSTAIN_GERS_CAPTURE_MISSING')
    c.add_argument('--publisher-schema-version',
                   help='Optional; must equal the value recorded at capture time')
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
        result = run_places(args.release, args.output,
                            publisher_schema_version=args.publisher_schema_version)
    elif args.command == 'gers':
        result = run_gers(args.release, args.output)
        if result['status'] != 'REGIONAL_ROWS_CAPTURED_NOT_COMPLETE_ID_UNION':
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
            raise SystemExit(3)
    else:
        result = compare(args.places_dir, gers_dir=args.gers_dir,
                         publisher_schema_version=args.publisher_schema_version)
        if args.output is not None:
            if args.output.exists() or args.output.is_symlink():
                parser.error('Report output must be a new file')
            args.output.write_bytes(canonical(result))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
