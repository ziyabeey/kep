"""DATA-018: third-release preregistration, offline compare and fail-closed gates."""
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import os
import re
import shutil
import subprocess
import sys
import unittest

from benchmarks.third_release_rehearsal import (PREV, RELEASE, stac_pair, synthetic_third,
                                                write_gers_dir, write_places_bundle,
                                                write_places_dir)
from kepcore.gers_reconciliation import load_pinned_pair
from kepcore.overture_places import PILOT, canonical
from kepcore.overture_third_release import (
    PROTOCOL_PATH, PROTOCOL_SHA256, check_candidate_release, load_protocol,
    regional_membership_reconciliation, select_regional_groups, three_release_trajectories,
    verify_release_chain, wilson,
)
from scripts.capture_third_release import _event_reader, compare, fetch_catalog, parse_listing

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

    def test_m4_field_list_is_part_of_the_hashed_protocol(self):
        p = load_protocol()
        self.assertEqual(p['m4_factual_fields'],
                         ['address', 'country', 'geometry', 'locality', 'name', 'operating_status'])
        with TemporaryDirectory() as tmp:
            copy = Path(tmp) / 'p.json'
            raw = PROTOCOL_PATH.read_bytes().replace(b'"operating_status"]', b'"operating_status", "source_provenance"]')
            self.assertNotEqual(raw, PROTOCOL_PATH.read_bytes())
            copy.write_bytes(raw)
            with self.assertRaises(ValueError):
                load_protocol(copy)
            # Even with a matching hash, category fields cannot enter M4.
            doc = json.loads(PROTOCOL_PATH.read_bytes())
            doc['m4_factual_fields'] = ['name', 'basic_category']
            bad = json.dumps(doc).encode()
            copy.write_bytes(bad)
            with self.assertRaises(ValueError):
                load_protocol(copy, expected_sha256=sha256(bad).hexdigest())

    def test_values_enforced_elsewhere_are_bound_to_the_protocol(self):
        # A frozen number that no code reads would be decorative: with a
        # re-pinned hash, any drift from the enforcing constant must still fail.
        doc = json.loads(PROTOCOL_PATH.read_bytes())
        self.assertEqual(doc['decision_gate']['type'], 'NONE_DESCRIPTIVE_SOURCE_STUDY')
        self.assertIsNone(doc['decision_gate']['primary_metric'])
        edits = {
            'footer_bytes': lambda d: d['gers'].update(max_footer_body_bytes=1024 * 1024),
            'max_records': lambda d: d.update(max_records_total=5),
            'references': lambda d: d.update(reference_releases=['2026-08-19.0', '2026-09-23.0']),
            'event_bytes': lambda d: d['gers'].update(max_event_body_bytes=64 * 1024 * 1024),
            'event_requests': lambda d: d['gers'].update(max_event_requests=512),
            'columns': lambda d: d['gers'].update(projected_columns=['id', 'bbox']),
            'predecessor': lambda d: d.update(expected_predecessor='2026-09-23.0'),
            'change_types': lambda d: d['gers'].update(captured_change_types=['added']),
            'prefix': lambda d: d['gers'].update(
                changelog_prefix_template='changelog/{release}/theme=places/type=place/kind={kind}/'),
            'rows_scanned': lambda d: d['gers'].update(max_event_rows_scanned=2_000_000),
        }
        with TemporaryDirectory() as tmp:
            copy = Path(tmp) / 'p.json'
            for name, edit in edits.items():
                with self.subTest(name=name):
                    d = json.loads(PROTOCOL_PATH.read_bytes())
                    edit(d)
                    raw = json.dumps(d).encode()
                    copy.write_bytes(raw)
                    with self.assertRaises(ValueError):
                        load_protocol(copy, expected_sha256=sha256(raw).hexdigest())

    def test_release_window(self):
        p = load_protocol()
        for good in ('2026-10-21.0', '2026-10-28.1', '2026-10-14.0', '2026-11-17.0'):
            self.assertEqual(check_candidate_release(good, p), good)
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
        for prev in ('2026-10-14.0', '2026-09-23.0', '2026-08-19.0'):
            with self.subTest(prev=prev):
                root, cat = stac_pair(prev_href=f'https://stac.overturemaps.org/{prev}/catalog.json')
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
        for field in ('basic_category', 'taxonomy_primary'):
            with self.subTest(field=field):
                c = [dict(x, **{field: 'changed'}) for x in b]
                r = three_release_trajectories(a, b, c, schema_comparable=False)
                delta = r['M3_consecutive_source_delta']
                self.assertNotIn(field, delta['field_change_counts'])
                self.assertEqual(delta['category_fields_excluded_technical_schema_review'][field], len(b))
                # Category-only changes must not count as revisions at the ID level either.
                self.assertEqual(delta['field_or_geometry_revised_ids'], 0)
                self.assertEqual(delta['unchanged_ids'], delta['retained_ids'])
        c = [dict(x, basic_category='changed') for x in b]
        mixed = [dict(x, basic_category='changed', confidence=None) for x in b]
        delta = three_release_trajectories(a, b, mixed, schema_comparable=False)['M3_consecutive_source_delta']
        self.assertEqual(delta['confidence_only_revised_ids'], len(b))
        comparable = three_release_trajectories(a, b, c, schema_comparable=True)['M3_consecutive_source_delta']
        self.assertEqual(comparable['field_or_geometry_revised_ids'], len(b))

    def test_m4_and_m5_numerators_follow_the_protocol_text(self):
        _, b = Shared.pair()
        base = [dict(r) for r in sorted(b, key=lambda r: r['overture_id'])[:7]]
        # (first, second, third) confidence; name changes per hop (hop1, hop2).
        plan = [((0.5, 0.6, 0.5), (True, True)),     # large, reversed; M4 persisted
                ((0.5, 0.6, 0.7), (True, False)),    # large, same direction
                ((0.5, 0.6, 0.58), (False, True)),   # large, small opposite move
                ((0.77, 0.72, 0.77), (False, False)),  # exactly 0.05 in decimal: not large
                ((0.85, 0.9, 0.85), (False, False)),   # exactly 0.05 the other way
                ((0.5, 0.8, 0.75), (False, False)),    # large, then exactly 0.05 back: not reversed
                ((0.8, 0.6, 0.65), (False, False))]    # same with opposite signs
        first, second, third = [], [], []
        for row, ((c1, c2, c3), (h1, h2)) in zip(base, plan):
            n1 = row['name'] or 'x'
            n2 = n1 + ' 2' if h1 else n1
            n3 = n2 + ' 3' if h2 else n2
            first.append(dict(row, confidence=c1, name=n1))
            second.append(dict(row, confidence=c2, name=n2))
            third.append(dict(row, confidence=c3, name=n3))
        r = three_release_trajectories(first, second, third, schema_comparable=True)
        m5, m4 = r['M5_confidence_reversal'], r['M4_revision_persistence']
        self.assertEqual((m5['k'], m5['n']), (1, 5))
        after, without = m4['after_first_hop_revision'], m4['without_first_hop_revision']
        self.assertEqual((after['k'], after['n'], without['k'], without['n']), (1, 2, 1, 5))

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

    def test_no_cross_counts_survive_any_abstention(self):
        cross = ('added_matched_official_row', 'removed_matched_official_row',
                 'local_added_without_official_event', 'local_removed_without_official_event',
                 'official_added_missing_from_third_snapshot',
                 'official_removed_still_in_third_snapshot',
                 'official_added_already_in_second_snapshot')
        _, row = self.events[0]
        cases = {'intermediate': (self.events, dict(self.chain, regional_reconciliation_allowed=False), True),
                 'incomplete': (self.events, self.chain, False),
                 'conflicting': (self.events + [('removed', row)], self.chain, True)}
        for name, (events, chain, complete) in cases.items():
            with self.subTest(name=name):
                r = regional_membership_reconciliation(self.b, self.c, events, chain=chain,
                                                       capture_complete=complete)
                self.assertTrue(r['status'].startswith('ABSTAIN_'))
                self.assertEqual({k: r['counts'][k] for k in cross}, dict.fromkeys(cross))
                self.assertEqual(r['counts']['local_newly_listed'], len(self.events))
        ok = regional_membership_reconciliation(self.b, self.c, self.events, chain=self.chain,
                                                capture_complete=True)
        self.assertTrue(all(type(ok['counts'][k]) is int for k in cross))

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

    def test_cross_type_events_do_not_count_as_agreement(self):
        old = {r['overture_id']: r for r in self.b}
        new = {r['overture_id']: r for r in self.c}
        added = sorted(new.keys() - old.keys())
        gone = sorted(old.keys() - new.keys())
        events = ([_event('removed', new[r]) for r in added[:5]]
                  + [_event('added', new[r]) for r in added[5:]]
                  + [_event('added', old[r]) for r in gone[:4]]
                  + [_event('removed', old[r]) for r in gone[4:]])
        r = regional_membership_reconciliation(self.b, self.c, events, chain=self.chain,
                                               capture_complete=True)
        self.assertEqual(r['status'], 'REGIONAL_SCOPE_RECONCILED')
        self.assertEqual(r['counts']['added_matched_official_row'], len(added) - 5)
        self.assertEqual(r['counts']['removed_matched_official_row'], len(gone) - 4)
        self.assertEqual((r['removed_agreement']['k'], r['removed_agreement']['n']), (len(gone) - 4, len(gone)))
        m6 = r['M6_regional_membership_agreement']
        self.assertEqual((m6['k'], m6['n']), (len(added) + len(gone) - 9, len(added) + len(gone)))
        self.assertEqual(r['counts']['official_added_already_in_second_snapshot'], 4)
        self.assertEqual(r['counts']['official_removed_still_in_third_snapshot'], 5)

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
WIDE = (20.0, 36.0, 35.0, 42.0)  # a real changelog row group spans far beyond the cells
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
        wide = select_regional_groups([_object('added', [WIDE, FAR]), _object('removed', [WIDE])],
                                      release=RELEASE, protocol=self.p)
        self.assertEqual((wide['selected_row_groups'], wide['excluded_row_groups']), (2, 1))

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
        few_rows = json.loads(json.dumps(self.p)); few_rows['gers']['max_event_rows_scanned'] = 15
        with self.assertRaises(ValueError):
            select_regional_groups([_object('added', [INSIDE]), _object('removed', [INSIDE])],
                                   release=RELEASE, protocol=few_rows)


class _Response:
    def __init__(self, req, item):
        start, end = map(int, req.get_header('Range').split('=')[1].split('-'))
        self.status, self.length = 206, end - start + 1
        self.headers = {'Content-Length': str(self.length), 'ETag': item['etag'],
                        'Content-Range': f'bytes {start}-{end}/{item["size"]}'}

    def read(self, n):
        return b'x' * min(n, self.length)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class EventReadBudget(unittest.TestCase):
    """The runtime GERS read budget is the protocol's, and it is really charged."""
    def setUp(self):
        self.p = load_protocol()
        self.item = {'key': f'changelog/{RELEASE}/theme=places/type=place/change_type=added/part-0.parquet',
                     'size': 64 * 1024 * 1024, 'etag': '"e"'}

    def reader(self):
        r = _event_reader(RELEASE, self.p)
        self.assertEqual((r.budget.limit, r.budget.request_limit),
                         (self.p['gers']['max_event_body_bytes'], self.p['gers']['max_event_requests']))
        calls = []
        r.opener.open = lambda req, timeout: calls.append(1) or _Response(req, self.item)
        return r, calls

    def test_request_cap_stops_before_the_next_request(self):
        r, calls = self.reader()
        cap = self.p['gers']['max_event_requests']
        for i in range(cap):
            r.read(self.item, i, i)
        with self.assertRaises(ValueError):
            r.read(self.item, cap, cap)
        self.assertEqual(len(calls), cap)

    def test_byte_cap_stops_before_the_oversized_request(self):
        r, calls = self.reader()
        r.read(self.item, 0, 12 * 1024 * 1024 - 1)
        with self.assertRaises(ValueError):
            r.read(self.item, 12 * 1024 * 1024, 17 * 1024 * 1024)
        self.assertEqual(len(calls), 1)
        self.assertLessEqual(r.budget.bytes_reserved, self.p['gers']['max_event_body_bytes'])



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
    def build(self, tmp, *, prev=PREV, complete=True, stac_schema=None, recorded='v2.0.0'):
        a, b = Shared.pair()
        c = synthetic_third(a, b)
        write_places_dir(tmp / 'run', c, prev_href=prev, schema_version=stac_schema,
                         publisher_schema_version=recorded)
        write_gers_dir(tmp / 'gers', b, c, complete=complete, prev_href=prev)
        return tmp / 'run', tmp / 'gers'

    def test_end_to_end_synthetic_rehearsal_is_labelled(self):
        with TemporaryDirectory() as t, patch('urllib.request.OpenerDirector.open',
                                              side_effect=AssertionError('network')):
            run, gers = self.build(Path(t))
            r = compare(run, gers_dir=gers)
        self.assertEqual(r['third_origin'], 'SYNTHETIC_REHEARSAL_NOT_A_REAL_RELEASE')
        self.assertEqual(r['status'], 'COMPARED')
        self.assertEqual(r['publisher_schema_version'], 'v2.0.0')
        self.assertIn('committed together', r['preregistration_note'])
        m1, m2 = r['trajectories']['M1_relisting_after_removal'], r['trajectories']['M2_transient_additions']
        self.assertEqual((m1['k'], m1['n'], m2['k'], m2['n']), (23, 69, 4, 222))
        m4 = r['trajectories']['M4_revision_persistence']
        self.assertEqual(m4['field_list_source'], 'protocol.m4_factual_fields')
        self.assertEqual([(m4[k]['k'], m4[k]['n']) for k in ('after_first_hop_revision',
                                                              'without_first_hop_revision')],
                         [(7, 158), (81, 4306)])
        m5 = r['trajectories']['M5_confidence_reversal']
        self.assertEqual((m5['k'], m5['n'], m5['threshold']), (19, 249, 0.05))
        self.assertEqual(r['protocol_sha256'], PROTOCOL_SHA256)
        self.assertIsNone(r['capture_code_commit'])
        self.assertEqual(r['compare_code_commit'], os.environ.get('GITHUB_SHA'))
        m6 = r['regional_gers']['M6_regional_membership_agreement']
        self.assertEqual((m6['k'], m6['n']), (169, 174))
        self.assertEqual(r['third_normalization_audit']['in_cell_rejections'], 0)
        self.assertEqual(r['regional_gers']['status'], 'REGIONAL_SCOPE_RECONCILED')
        self.assertEqual(r['regional_gers']['counts']['local_added_without_official_event'], 3)
        self.assertEqual(r['regional_gers']['counts']['local_removed_without_official_event'], 2)
        self.assertFalse(r['consumer_publish'])

    def test_tampered_places_capture_rejected(self):
        with TemporaryDirectory() as t:
            run, gers = self.build(Path(t))
            r = json.loads((run / 'places_receipt.json').read_bytes())
            (run / 'places_receipt.json').write_bytes(canonical(dict(r, origin='trust_me')))
            with self.assertRaises(ValueError):
                compare(run, gers_dir=gers)
        with TemporaryDirectory() as t:
            run, gers = self.build(Path(t))
            m = run / 'places' / 'places_minimal.json'
            m.write_bytes(m.read_bytes().replace(b'Sentetik yer 1', b'Sentetik yer X', 1))
            with self.assertRaises(ValueError):
                compare(run, gers_dir=gers)
        relabels = {
            # A synthetic bundle cannot be passed off as a real capture.
            'real_origin': lambda r: dict(r, origin='captured_overture_cli'),
            # A capture made under another protocol version is rejected.
            'other_protocol': lambda r: dict(r, protocol_sha256='0' * 64),
            'no_protocol': lambda r: {k: v for k, v in r.items() if k != 'protocol_sha256'},
        }
        for name, mutate in relabels.items():
            with self.subTest(name=name), TemporaryDirectory() as t:
                run, gers = self.build(Path(t))
                r = json.loads((run / 'places_receipt.json').read_bytes())
                (run / 'places_receipt.json').write_bytes(canonical(mutate(r)))
                with self.assertRaises(ValueError):
                    compare(run, gers_dir=gers)

    def test_bad_gers_capture_abstains_but_keeps_m1_to_m5(self):
        def tamper_events(gers):
            p = gers / 'gers_regional_events.json'
            p.write_bytes(p.read_bytes().replace(b'"added"', b'"removed"', 1))

        def receipt(mutate):
            def apply(gers):
                g = json.loads((gers / 'gers_receipt.json').read_bytes())
                (gers / 'gers_receipt.json').write_bytes(canonical(mutate(g)))
            return apply

        def bad_uuid(gers):
            events = json.loads((gers / 'gers_regional_events.json').read_bytes())
            events[0]['id'] = events[0]['id'].upper()
            raw = canonical(events)
            (gers / 'gers_regional_events.json').write_bytes(raw)
            receipt(lambda g: dict(g, events_sha256=sha256(raw).hexdigest()))(gers)

        def deep_events(gers):
            raw = b'[' * 50_000 + b']' * 50_000
            (gers / 'gers_regional_events.json').write_bytes(raw)
            receipt(lambda g: dict(g, events_sha256=sha256(raw).hexdigest()))(gers)

        def event_edit(mutate):
            def apply(gers):
                events = json.loads((gers / 'gers_regional_events.json').read_bytes())
                mutate(events[0])
                raw = canonical(events)
                (gers / 'gers_regional_events.json').write_bytes(raw)
                receipt(lambda g: dict(g, events_sha256=sha256(raw).hexdigest()))(gers)
            return apply

        cases = {
            'events_altered': tamper_events,
            'release': receipt(lambda g: dict(g, release='2026-10-28.1')),
            'origin': receipt(lambda g: dict(g, origin='captured_public_GERS_rows')),
            'predecessor': receipt(lambda g: dict(g, chain=dict(g['chain'], observed_predecessor='2026-10-14.0'))),
            'other_protocol': receipt(lambda g: dict(g, protocol_sha256='0' * 64)),
            'no_protocol': receipt(lambda g: {k: v for k, v in g.items() if k != 'protocol_sha256'}),
            'unhashable_kind': event_edit(lambda e: e.update(change_type=['added'])),
            'huge_bbox': event_edit(lambda e: e['bbox'].update(xmin=10 ** 400)),
            'receipt_is_list': lambda gers: (gers / 'gers_receipt.json').write_bytes(canonical([1])),
            'deeply_nested_events': deep_events,
            'noncanonical_uuid': bad_uuid,
        }
        for name, mutate in cases.items():
            with self.subTest(name=name), TemporaryDirectory() as t:
                run, gers = self.build(Path(t))
                mutate(gers)
                r = compare(run, gers_dir=gers)
                self.assertEqual(r['regional_gers']['status'], 'ABSTAIN_GERS_CAPTURE_INVALID')
                self.assertIsNone(r['regional_gers']['M6_regional_membership_agreement'])
                self.assertEqual(r['trajectories']['M1_relisting_after_removal']['n'], 69)

    def test_missing_gers_capture_still_reports_an_m6_status(self):
        # A skipped or early-failed GERS step must not leave M6 silently empty.
        for name, gers_dir in (('no_dir_given', lambda g: None), ('no_receipt', lambda g: g),
                               ('dir_missing', lambda g: g / 'nope')):
            with self.subTest(name=name), TemporaryDirectory() as t:
                run, gers = self.build(Path(t))
                (gers / 'gers_receipt.json').unlink()
                r = compare(run, gers_dir=gers_dir(gers))
                self.assertEqual(r['status'], 'COMPARED')
                self.assertEqual(r['regional_gers']['status'], 'ABSTAIN_GERS_CAPTURE_MISSING')
                self.assertIn('receipt', r['regional_gers']['reason'])
                self.assertIsNone(r['regional_gers']['M6_regional_membership_agreement'])
                self.assertEqual(r['trajectories']['M1_relisting_after_removal']['n'], 69)

    def test_incomplete_capture_or_gap_abstains_and_schema_change_flags(self):
        with TemporaryDirectory() as t:
            run, gers = self.build(Path(t), complete=False, recorded='v2.1.0')
            r = compare(run, gers_dir=gers)
        self.assertEqual(r['regional_gers']['status'], 'ABSTAIN_INCOMPLETE_CAPTURE')
        self.assertIsNone(r['regional_gers']['M6_regional_membership_agreement'])
        self.assertFalse(r['trajectories']['category_semantics_comparable_second_to_third'])
        with TemporaryDirectory() as t:
            run, gers = self.build(Path(t), prev='https://stac.overturemaps.org/2026-10-14.0/catalog.json')
            r = compare(run, gers_dir=gers)
        self.assertEqual(r['regional_gers']['status'], 'ABSTAIN_REQUIRES_INTERMEDIATE_RELEASE')
        self.assertIsNotNone(r['trajectories']['M1_relisting_after_removal']['fraction'])

    def test_normalization_rejections_abstain_instead_of_counting_as_removed(self):
        with TemporaryDirectory() as t:
            run, gers = self.build(Path(t))
            path = run / 'places' / 'manifest.json'
            m = json.loads(path.read_bytes())
            m['audit'] = dict(m['audit'], rows_read=m['audit']['rows_read'] + 2,
                              rejected={'outside_sampling_cell': 3, 'invalid_operating_status': 2})
            path.write_bytes(canonical(m))
            r = compare(run, gers_dir=gers)
            self.assertEqual(r['status'], 'ABSTAIN_NORMALIZATION_REJECTED_IN_CELL_RECORDS')
            self.assertIsNone(r['trajectories'])
            self.assertIsNone(r['regional_gers'])
            self.assertEqual(r['third_normalization_audit']['in_cell_rejection_reasons'],
                             {'invalid_operating_status': 2})
            m['audit'] = dict(m['audit'], rows_read=1)
            path.write_bytes(canonical(m))
            with self.assertRaises(ValueError):
                compare(run, gers_dir=gers)

    def test_schema_is_fixed_at_capture_and_checked_against_stac(self):
        with TemporaryDirectory() as t:
            run, _ = self.build(Path(t), stac_schema='2.1.0', recorded='v2.1.0')
            r = compare(run, gers_dir=None)
            self.assertFalse(r['category_semantics_comparable'])
            self.assertEqual(r['stac_schema_version'], '2.1.0')
            # A later offline re-run cannot swap the schema after seeing results.
            with self.assertRaises(ValueError):
                compare(run, gers_dir=None, publisher_schema_version='v2.0.0')
            self.assertEqual(compare(run, gers_dir=None, publisher_schema_version='2.1.0')['status'], 'COMPARED')
        with TemporaryDirectory() as t:
            run, _ = self.build(Path(t), stac_schema='2.1.0', recorded='v2.0.0')
            with self.assertRaises(ValueError):
                compare(run, gers_dir=None)
        with TemporaryDirectory() as t:
            run, _ = self.build(Path(t), stac_schema='2.0.0', recorded='2.0.0')
            self.assertTrue(compare(run, gers_dir=None)['category_semantics_comparable'])
        with TemporaryDirectory() as t:
            run, _ = self.build(Path(t), recorded='  ')
            with self.assertRaises(ValueError):
                compare(run, gers_dir=None)

    def test_stored_chain_must_replay_exactly(self):
        with TemporaryDirectory() as t:
            run, gers = self.build(Path(t))
            cat = run / 'stac_release.json'
            cat.write_bytes(cat.read_bytes().replace(PREV.encode(),
                            b'https://stac.overturemaps.org/2026-10-14.0/catalog.json'))
            with self.assertRaises(ValueError):
                compare(run, gers_dir=gers)


class PlacesCapture(unittest.TestCase):
    """run_places with STAC and the overturemaps download stubbed: no network."""
    def run_places(self, tmp, *, operator, stac_schema='2.0.0'):
        from scripts import capture_third_release as cap
        root, cat = stac_pair(schema_version=stac_schema)
        downloads = []

        def fake_execute(*, output, inputs, fetch, seed_file, release):
            self.assertEqual((fetch, release), (True, RELEASE))
            downloads.append(output)
            a, b = Shared.pair()
            rows = synthetic_third(a, b)
            write_places_bundle(output, rows, synthetic=False)
            return {'rows_accepted': len(rows)}

        catalogs = {cap.STAC_ROOT: root,
                    f'https://stac.overturemaps.org/{RELEASE}/catalog.json': cat}
        with patch.object(cap, 'fetch_catalog', side_effect=lambda url: catalogs[url]), \
                patch('scripts.overture_istanbul.execute', side_effect=fake_execute), \
                patch('urllib.request.OpenerDirector.open', side_effect=AssertionError('network')), \
                patch.dict('os.environ', {'GITHUB_SHA': 'f' * 40}):
            try:
                return cap.run_places(RELEASE, tmp / 'run', publisher_schema_version=operator), downloads
            except ValueError as exc:
                return exc, downloads

    def test_contradicting_operator_schema_stops_before_places_read(self):
        with TemporaryDirectory() as t:
            result, downloads = self.run_places(Path(t), operator='v2.1.0')
        self.assertIsInstance(result, ValueError)
        self.assertEqual(downloads, [])

    def test_receipt_records_schema_protocol_and_commit_then_compares(self):
        with TemporaryDirectory() as t:
            receipt, downloads = self.run_places(Path(t), operator='v2.0.0')
            self.assertEqual(len(downloads), 1)
            self.assertEqual((receipt['publisher_schema_version'], receipt['stac_schema_version']),
                             ('v2.0.0', '2.0.0'))
            self.assertEqual((receipt['protocol_sha256'], receipt['code_commit']),
                             (PROTOCOL_SHA256, 'f' * 40))
            r = compare(Path(t) / 'run', gers_dir=None)
        self.assertEqual((r['status'], r['third_origin']), ('COMPARED', 'REAL_OVERTURE_CAPTURE'))
        self.assertEqual(r['capture_code_commit'], 'f' * 40)
        self.assertEqual(r['regional_gers']['status'], 'ABSTAIN_GERS_CAPTURE_MISSING')

    def test_operator_schema_recorded_when_stac_is_silent(self):
        # The pinned 2026-09-23.1 catalog has no schema:version, so only the
        # operator's value can trigger the category exclusion.
        with TemporaryDirectory() as t:
            receipt, _ = self.run_places(Path(t), operator='v2.1.0', stac_schema=None)
            self.assertEqual((receipt['publisher_schema_version'], receipt['stac_schema_version']),
                             ('v2.1.0', None))
            r = compare(Path(t) / 'run', gers_dir=None)
        self.assertFalse(r['category_semantics_comparable'])
        self.assertIn('category_fields_excluded_technical_schema_review',
                      r['trajectories']['M3_consecutive_source_delta'])

    def test_real_manifest_with_synthetic_receipt_rejected(self):
        with TemporaryDirectory() as t:
            receipt, _ = self.run_places(Path(t), operator='v2.0.0')
            path = Path(t) / 'run' / 'places_receipt.json'
            path.write_bytes(canonical(dict(receipt, origin='synthetic_rehearsal')))
            with self.assertRaises(ValueError):
                compare(Path(t) / 'run', gers_dir=None)


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
        with TemporaryDirectory() as t, patch('urllib.request.OpenerDirector.open',
                                              side_effect=AssertionError('network')):
            with self.assertRaises(ValueError):
                execute(output=Path(t) / 'o', inputs=None, fetch=True, seed_file=None, release='latest')
            self.assertFalse((Path(t) / 'o').exists())


if __name__ == '__main__':
    unittest.main()
