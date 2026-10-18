"""DATA-018: third-release preregistration, offline compare and fail-closed gates."""
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import re
import shutil
import subprocess
import sys
import unittest

from benchmarks.third_release_rehearsal import (PREV, RELEASE, stac_pair, synthetic_third,
                                                write_gers_dir, write_places_dir)
from kepcore.gers_reconciliation import load_pinned_pair
from kepcore.overture_places import PILOT, canonical
from kepcore.overture_third_release import (
    PROTOCOL_PATH, check_candidate_release, load_protocol, regional_membership_reconciliation,
    select_regional_groups, three_release_trajectories, verify_release_chain, wilson,
)
from scripts.capture_third_release import compare, fetch_catalog, parse_listing

ROOT = Path(__file__).resolve().parents[1]
UUID_RE = re.compile(rb'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')


class Shared:
    _pair = None

    @classmethod
    def pair(cls):
        if cls._pair is None:
            a, b = load_pinned_pair()
            cls._pair = (list(a.records), list(b.records))
        return cls._pair


class ProtocolFreeze(unittest.TestCase):
    def test_protocol_is_frozen_and_bounded(self):
        p = load_protocol()
        self.assertEqual(p['expected_predecessor'], '2026-09-23.1')
        self.assertEqual(p['planned_release']['release'], '2026-10-21.0')
        self.assertTrue(p['frozen_before_any_third_release_data'])
        self.assertFalse(p['consumer_display_approved'])

    def test_post_hoc_protocol_edit_is_rejected(self):
        with TemporaryDirectory() as tmp:
            copy = Path(tmp) / 'p.json'
            copy.write_bytes(PROTOCOL_PATH.read_bytes().replace(b'0.05', b'0.10'))
            with self.assertRaises(ValueError):
                load_protocol(copy)

    def test_release_window(self):
        p = load_protocol()
        self.assertEqual(check_candidate_release('2026-10-21.0', p), '2026-10-21.0')
        self.assertEqual(check_candidate_release('2026-10-28.1', p), '2026-10-28.1')
        for bad in ('2026-11-18.0', '2026-09-23.1', '2026-10-21', 'latest', '2026-10-13.0'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                check_candidate_release(bad, p)


class ReleaseChain(unittest.TestCase):
    def setUp(self):
        self.p = load_protocol()

    def test_consecutive_pair(self):
        root, cat = stac_pair()
        chain = verify_release_chain(root, cat, release=RELEASE, protocol=self.p)
        self.assertEqual(chain['status'], 'CONSECUTIVE_PAIR')
        self.assertTrue(chain['regional_reconciliation_allowed'])
        self.assertFalse(chain['changelog_build_baseline_publisher_attested'])

    def test_intermediate_release_blocks_reconciliation(self):
        root, cat = stac_pair(prev_href='https://stac.overturemaps.org/2026-10-14.0/catalog.json')
        chain = verify_release_chain(root, cat, release=RELEASE, protocol=self.p)
        self.assertEqual(chain['status'], 'REQUIRES_INTERMEDIATE_RELEASE')
        self.assertFalse(chain['regional_reconciliation_allowed'])

    def test_stac_latest_must_match_requested_release(self):
        root, _ = stac_pair(release='2026-10-28.0')
        _, cat = stac_pair()
        with self.assertRaises(ValueError):
            verify_release_chain(root, cat, release=RELEASE, protocol=self.p)

    def test_malformed_release_catalogs_fail_closed(self):
        root, cat = stac_pair()
        doc = json.loads(cat)
        variants = []
        no_places = json.loads(cat); no_places['links'] = [l for l in no_places['links'] if l['rel'] != 'child']
        two_prev = json.loads(cat); two_prev['links'].append(dict(two_prev['links'][-1]))
        wrong_id = dict(doc, id='2026-09-23.1')
        foreign_prev = json.loads(cat); foreign_prev['links'][-1]['href'] = 'https://evil.example/2026-09-23.1/catalog.json'
        variants += [no_places, two_prev, wrong_id, foreign_prev]
        for v in variants:
            with self.subTest(v=v), self.assertRaises(ValueError):
                verify_release_chain(root, canonical(v), release=RELEASE, protocol=self.p)


class Trajectories(unittest.TestCase):
    def test_identity_third_release_reproduces_known_real_counts(self):
        a, b = Shared.pair()
        r = three_release_trajectories(a, b, b, schema_comparable=True)
        t = r['trajectory_counts']
        self.assertEqual((t['listed_in_all_three'], t['removed_in_second_still_absent'],
                          t['new_in_second_kept']), (4581, 69, 222))
        self.assertEqual(r['M1_relisting_after_removal']['n'], 69)
        self.assertEqual(r['M2_transient_additions']['n'], 222)
        self.assertEqual(r['M4_revision_persistence']['after_first_hop_revision']['n'], 162)
        self.assertEqual(r['M5_confidence_reversal']['n'], 256)
        self.assertIsNone(r['physical_business_closures'])
        self.assertFalse(r['removal_is_business_closure'])

    def test_schema_change_excludes_category_fields(self):
        a, b = Shared.pair()
        c = [dict(x, basic_category='changed') for x in b]
        r = three_release_trajectories(a, b, c, schema_comparable=False)
        delta = r['M3_consecutive_source_delta']
        self.assertNotIn('basic_category', delta['field_change_counts'])
        self.assertEqual(delta['category_fields_excluded_technical_schema_review']['basic_category'], len(b))

    def test_repeated_ids_and_foreign_cells_rejected(self):
        a, b = Shared.pair()
        with self.assertRaises(ValueError):
            three_release_trajectories(a, b, b + b[:1], schema_comparable=True)
        with self.assertRaises(ValueError):
            three_release_trajectories(a, b, [dict(b[0], cell='kadikoy')], schema_comparable=True)
        with self.assertRaises(ValueError):
            three_release_trajectories(a, b, b, schema_comparable='yes')

    def test_wilson_edges(self):
        self.assertIsNone(wilson(0, 0)['fraction'])
        self.assertEqual(wilson(5, 5)['wilson95'][1], 1.0)
        with self.assertRaises(ValueError):
            wilson(3, 2)


def _event(kind, row):
    x, y = row['lon'], row['lat']
    return kind, {'id': row['overture_id'], 'columns_changed': None,
                  'bbox': {'xmin': x, 'xmax': x, 'ymin': y, 'ymax': y}}


class RegionalReconciliation(unittest.TestCase):
    def setUp(self):
        a, b = Shared.pair()
        self.b = b
        self.c = synthetic_third(a, b)
        root, cat = stac_pair()
        self.chain = verify_release_chain(root, cat, release=RELEASE, protocol=load_protocol())
        old = {r['overture_id'] for r in b}
        new = {r['overture_id']: r for r in self.c}
        self.events = [_event('added', new[r]) for r in sorted(new.keys() - old)]

    def test_agreement_only_counts_matching_change_type(self):
        r = regional_membership_reconciliation(self.b, self.c, self.events, chain=self.chain,
                                               capture_complete=True)
        self.assertEqual(r['status'], 'REGIONAL_SCOPE_RECONCILED')
        self.assertEqual(r['added_agreement']['fraction'], 1.0)
        self.assertEqual(r['removed_agreement']['k'], 0)
        self.assertFalse(r['changelog_build_baseline_publisher_attested'])

    def test_abstains_without_consecutive_pair_or_complete_capture(self):
        r = regional_membership_reconciliation(self.b, self.c, self.events,
            chain=dict(self.chain, regional_reconciliation_allowed=False), capture_complete=True)
        self.assertEqual(r['status'], 'ABSTAIN_REQUIRES_INTERMEDIATE_RELEASE')
        self.assertIsNone(r['M6_regional_membership_agreement'])
        r = regional_membership_reconciliation(self.b, self.c, self.events, chain=self.chain,
                                               capture_complete=False)
        self.assertEqual(r['status'], 'ABSTAIN_INCOMPLETE_CAPTURE')
        self.assertIsNone(r['M6_regional_membership_agreement'])

    def test_conflicting_official_rows_abstain(self):
        kind, row = self.events[0]
        r = regional_membership_reconciliation(self.b, self.c, self.events + [('removed', row)],
                                               chain=self.chain, capture_complete=True)
        self.assertEqual(r['status'], 'ABSTAIN_CONFLICTING_OFFICIAL_ROWS')

    def test_output_holds_no_raw_ids_and_ignores_outside_rows(self):
        outside = ('added', {'id': '00000000-0000-4000-8000-000000000001', 'columns_changed': None,
                             'bbox': {'xmin': 30.5, 'xmax': 30.5, 'ymin': 40.0, 'ymax': 40.0}})
        r = regional_membership_reconciliation(self.b, self.c, self.events + [outside],
                                               chain=self.chain, capture_complete=True)
        self.assertEqual(r['counts']['official_regional_added'], len(self.events))
        self.assertEqual(UUID_RE.findall(canonical({k: v for k, v in r.items() if k != 'id_set_sha256'})), [])

    def test_unknown_event_kinds_rejected(self):
        kind, row = self.events[0]
        with self.assertRaises(ValueError):
            regional_membership_reconciliation(self.b, self.c, [('data_changed', row)],
                                               chain=self.chain, capture_complete=True)


def _column(path, lo, hi, offset, physical='DOUBLE'):
    order = 'NUMERIC' if path.startswith('bbox.') else 'UNKNOWN'
    stats = None if lo is None else {'min': lo, 'max': hi, 'null_count': 0, 'order': order}
    return {'path': path, 'physical_type': physical, 'compressed_bytes': 100, 'offset': offset,
            'statistics': stats}


def _object(kind, boxes, release=RELEASE, name='a'):
    groups, offset = [], 4
    for box in boxes:
        cols = []
        for path in ('id', 'columns_changed.list.element'):
            cols.append(_column(path, None, None, offset, 'BYTE_ARRAY')); offset += 100
        for path, lo, hi in (('bbox.xmin', box[0], box[2]), ('bbox.xmax', box[0], box[2]),
                             ('bbox.ymin', box[1], box[3]), ('bbox.ymax', box[1], box[3])):
            cols.append(_column(path, lo, hi, offset) if box[0] is not None
                        else _column(path, None, None, offset)); offset += 100
        groups.append({'rows': 10, 'columns': cols})
    size = offset + 1000
    return {'key': f'changelog/{release}/theme=places/type=place/change_type={kind}/part-{name}.parquet',
            'release': release, 'change_type': kind, 'etag': '"e"', 'size': size,
            'footer_length': 500, 'footer_sha256': '0' * 64, 'rows': 10 * len(boxes),
            'row_groups': groups}


INSIDE = (28.97, 41.02, 28.98, 41.03)
FAR = (10.0, 50.0, 11.0, 51.0)
UNKNOWN = (None, None, None, None)


class RegionalPlan(unittest.TestCase):
    def setUp(self):
        self.p = load_protocol()

    def test_selects_intersecting_and_unknown_groups_only(self):
        objs = [_object('added', [INSIDE, FAR, UNKNOWN]), _object('removed', [FAR, INSIDE])]
        plan = select_regional_groups(objs, release=RELEASE, protocol=self.p)
        self.assertEqual(plan['selected_row_groups'], 3)
        self.assertEqual(plan['excluded_row_groups'], 2)
        self.assertEqual(sum(x['metadata_statistics_unknown'] for x in plan['selected']), 1)
        self.assertFalse(plan['complete_id_union_scan'])

    def test_missing_partition_other_release_or_over_budget_stop(self):
        with self.assertRaises(ValueError):
            select_regional_groups([_object('added', [INSIDE])], release=RELEASE, protocol=self.p)
        with self.assertRaises(ValueError):
            select_regional_groups([_object('added', [INSIDE], release='2026-09-23.1'),
                                    _object('removed', [INSIDE], release='2026-09-23.1')],
                                   release=RELEASE, protocol=self.p)
        tight = json.loads(json.dumps(self.p)); tight['gers']['max_event_body_bytes'] = 1000
        with self.assertRaises(ValueError):
            select_regional_groups([_object('added', [INSIDE]), _object('removed', [INSIDE])],
                                   release=RELEASE, protocol=tight)


LISTING = ('<?xml version="1.0" encoding="UTF-8"?><ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
           '<Prefix>{prefix}</Prefix><IsTruncated>{trunc}</IsTruncated>{contents}</ListBucketResult>')


class Listing(unittest.TestCase):
    prefix = f'changelog/{RELEASE}/theme=places/type=place/change_type=added/'

    def doc(self, keys, trunc='false'):
        contents = ''.join(f'<Contents><Key>{k}</Key><ETag>"x"</ETag><Size>500</Size></Contents>' for k in keys)
        return LISTING.format(prefix=self.prefix, trunc=trunc, contents=contents).encode()

    def test_parses_strict_listing(self):
        items = parse_listing(self.doc([self.prefix + 'part-0.parquet']), prefix=self.prefix,
                              release=RELEASE, kind='added')
        self.assertEqual(items[0]['size'], 500)

    def test_truncated_empty_or_foreign_listing_rejected(self):
        for raw in (self.doc([self.prefix + 'p.parquet'], 'true'), self.doc([]),
                    self.doc(['changelog/other/p.parquet']), self.doc([self.prefix + 'sub/p.parquet'])):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                parse_listing(raw, prefix=self.prefix, release=RELEASE, kind='added')


class OfflineRehearsal(unittest.TestCase):
    def build(self, tmp, *, prev=PREV, complete=True):
        a, b = Shared.pair()
        c = synthetic_third(a, b)
        write_places_dir(tmp / 'run', c, prev_href=prev)
        write_gers_dir(tmp / 'gers', b, c, complete=complete)
        return tmp / 'run', tmp / 'gers'

    def test_end_to_end_synthetic_rehearsal_is_labelled(self):
        with TemporaryDirectory() as t, patch('urllib.request.OpenerDirector.open',
                                              side_effect=AssertionError('network')):
            run, gers = self.build(Path(t))
            r = compare(run, publisher_schema_version='v2.0.0', gers_dir=gers)
        self.assertEqual(r['third_origin'], 'SYNTHETIC_REHEARSAL_NOT_A_REAL_RELEASE')
        self.assertEqual(r['trajectories']['M1_relisting_after_removal']['k'], 23)
        self.assertEqual(r['regional_gers']['status'], 'REGIONAL_SCOPE_RECONCILED')
        self.assertEqual(r['regional_gers']['counts']['local_added_without_official_event'], 3)
        self.assertEqual(r['regional_gers']['counts']['local_removed_without_official_event'], 2)
        self.assertFalse(r['consumer_publish'])

    def test_tampered_events_or_receipts_rejected(self):
        with TemporaryDirectory() as t:
            run, gers = self.build(Path(t))
            p = gers / 'gers_regional_events.json'
            p.write_bytes(p.read_bytes().replace(b'"added"', b'"removed"', 1))
            with self.assertRaises(ValueError):
                compare(run, publisher_schema_version='v2.0.0', gers_dir=gers)
        with TemporaryDirectory() as t:
            run, gers = self.build(Path(t))
            r = json.loads((run / 'places_receipt.json').read_bytes())
            (run / 'places_receipt.json').write_bytes(canonical(dict(r, origin='trust_me')))
            with self.assertRaises(ValueError):
                compare(run, publisher_schema_version='v2.0.0', gers_dir=gers)
        with TemporaryDirectory() as t:
            run, gers = self.build(Path(t))
            m = run / 'places' / 'places_minimal.json'
            m.write_bytes(m.read_bytes().replace(b'Sentetik yer 1', b'Sentetik yer X', 1))
            with self.assertRaises(ValueError):
                compare(run, publisher_schema_version='v2.0.0', gers_dir=gers)

    def test_incomplete_capture_or_gap_abstains_and_schema_change_flags(self):
        with TemporaryDirectory() as t:
            run, gers = self.build(Path(t), complete=False)
            r = compare(run, publisher_schema_version='v2.1.0', gers_dir=gers)
        self.assertIsNone(r['regional_gers']['M6_regional_membership_agreement'])
        self.assertFalse(r['trajectories']['category_semantics_comparable_second_to_third'])
        with TemporaryDirectory() as t:
            run, gers = self.build(Path(t), prev='https://stac.overturemaps.org/2026-10-14.0/catalog.json')
            r = compare(run, publisher_schema_version='v2.0.0', gers_dir=gers)
        self.assertEqual(r['regional_gers']['status'], 'ABSTAIN_REQUIRES_INTERMEDIATE_RELEASE')
        self.assertIsNotNone(r['trajectories']['M1_relisting_after_removal']['fraction'])


class CliSafety(unittest.TestCase):
    def test_default_run_is_offline(self):
        out = subprocess.run([sys.executable, 'scripts/capture_third_release.py'], cwd=ROOT,
                             capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(out.stdout)['network_calls'], 0)

    def test_fetch_requires_exact_confirmation(self):
        for cmd in (['places', '--fetch', '--release', RELEASE, '--output', '/tmp/x'],
                    ['gers', '--fetch', '--research-confirmation', 'RESEARCH_ONLY',
                     '--release', RELEASE, '--output', '/tmp/x']):
            with self.subTest(cmd=cmd):
                out = subprocess.run([sys.executable, 'scripts/capture_third_release.py', *cmd],
                                     cwd=ROOT, capture_output=True, text=True)
                self.assertEqual(out.returncode, 2)

    def test_catalog_fetch_refuses_other_hosts(self):
        with patch('urllib.request.OpenerDirector.open', side_effect=AssertionError('network')):
            for url in ('http://stac.overturemaps.org/catalog.json',
                        'https://stac.overturemaps.org.evil.example/catalog.json',
                        'https://user@stac.overturemaps.org/catalog.json'):
                with self.subTest(url=url), self.assertRaises(ValueError):
                    fetch_catalog(url)

    def test_places_override_still_requires_exact_release(self):
        from scripts.overture_istanbul import execute
        with TemporaryDirectory() as t, self.assertRaises(ValueError):
            execute(output=Path(t) / 'o', inputs=None, fetch=True, seed_file=None, release='latest')


if __name__ == '__main__':
    unittest.main()
