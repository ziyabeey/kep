"""DATA-013 RED contracts. All rows/events in this file are SYNTHETIC.

No real fixture is used to manufacture an official GERS observation or a human
business-existence label. Real archive regressions live in a separate file.
"""
import copy
from dataclasses import replace
from hashlib import sha256
import unittest
from uuid import UUID

from kepcore.overture_delta import ResearchSnapshot
from kepcore.overture_places import PILOT, canonical
from kepcore.gers_reconciliation import reconcile

OLD = '2026-08-19.0'
NEW = '2026-09-23.1'


def uid(n):
    return str(UUID(int=n))


def poi(n, **changes):
    row = dict(overture_id=uid(n), name='Synthetic cafe', address=None,
        basic_category='cafe', taxonomy_primary='cafe', operating_status=None,
        locality='Synthetic', country='TR', source_provenance=[],
        lon=29.006, lat=41.042, cell='besiktas_center', confidence=0.8,
        active_event=None, administrative_district=None, consumer_verified=False,
        live_price=None, open_now=None, opening_hours=None)
    row.update(changes)
    return row


def snapshot(rows, release):
    rows = sorted(copy.deepcopy(rows), key=lambda r: r['overture_id'])
    digest = sha256(canonical(rows)).hexdigest()
    return ResearchSnapshot(release=release, observed_at=release[:10]+'T12:00:00Z',
        normalized_sha256=digest, population_sha256=digest,
        origin='synthetic_future', records=tuple(rows),
        sampling_cells=tuple(sorted(PILOT)))


def pair(old=None, new=None):
    return (snapshot([poi(1)] if old is None else old, OLD),
            snapshot([poi(1)] if new is None else new, NEW))


def event(n, kind, columns=None):
    return {'id':uid(n), 'change_type':kind, 'columns_changed':columns}


def bundle(before, after, events, **changes):
    ids = sorted({r['overture_id'] for s in (before, after) for r in s.records})
    b = {'format':'KEP-GERS-CAPTURE-v1', 'origin':'synthetic_fixture',
        'before_release':OLD, 'after_release':NEW,
        'source_root':'overturemaps', 'source_url':'synthetic://gers',
        'retrieved_at':'2026-10-11T12:00:00Z',
        'rights_evidence_url':'https://docs.overturemaps.org/attribution/',
        'transition_evidence':{'status':'synthetic_fixture',
            'url':'synthetic://transition', 'sha256':'a'*64},
        'query':{'mode':'id_union', 'ids_sha256':sha256(canonical(ids)).hexdigest(),
                 'all_partitions_scanned':True},
        'rows':events}
    b.update(changes)
    return b


def run(before, after, b=None):
    return reconcile(before, after, changelog=b,
        expected_changelog_sha256=sha256(canonical(b)).hexdigest() if b is not None else None)


class SyntheticReconciliationTests(unittest.TestCase):
    def test_no_changelog_does_not_generate_official_events(self):
        x = run(*pair([poi(1),poi(2)],[poi(2),poi(3)]))
        self.assertEqual(x['official']['status'], 'NOT_AVAILABLE')
        self.assertIsNone(x['official']['membership_agreement_fraction'])
        self.assertEqual(x['official']['observed_unique_ids'], 0)
        self.assertIsNone(x['physical_closures'])
        self.assertIsNone(x['physical_openings'])

    def test_added_removed_membership_agrees_not_business_truth(self):
        a,b = pair([poi(1),poi(2)],[poi(2),poi(3)])
        x = run(a,b,bundle(a,b,[event(1,'removed'),event(2,'unchanged'),event(3,'added')]))
        self.assertEqual(x['official']['membership_agreement_fraction'], 1.0)
        self.assertEqual(x['official']['status'], 'SYNTHETIC_ONLY')
        self.assertEqual(x['unsupported_naive_business_assertions'], 2)
        self.assertFalse(x['consumer_publish'])
        self.assertEqual(x['independent_business_evidence_count'], 0)

    def test_regional_entry_is_not_global_addition(self):
        a,b = pair([poi(1)],[poi(1),poi(2)])
        x = run(a,b,bundle(a,b,[event(1,'unchanged'),event(2,'data_changed',['geometry'])]))
        self.assertEqual(x['official']['outcome_counts']['REGIONAL_ENTRY_OR_CAPTURE_GAP'],1)
        self.assertEqual(x['official']['membership_agreement_fraction'],0.0)

    def test_regional_exit_is_not_global_removal(self):
        a,b = pair([poi(1),poi(2)],[poi(1)])
        x = run(a,b,bundle(a,b,[event(1,'unchanged'),event(2,'unchanged')]))
        self.assertEqual(x['official']['outcome_counts']['REGIONAL_EXIT_OR_CAPTURE_GAP'],1)
        self.assertIsNone(x['physical_closures'])

    def test_confidence_only_can_be_officially_unchanged(self):
        a,b = pair([poi(1)],[poi(1,confidence=.1)])
        x = run(a,b,bundle(a,b,[event(1,'unchanged')]))
        self.assertEqual(x['official']['outcome_counts']['COMPATIBLE_ON_OBSERVED_FIELDS'],1)
        self.assertEqual(x['routing']['metadata_only_ids'],1)
        self.assertEqual(x['routing']['property_review_ids'],0)

    def test_source_only_is_metadata_not_an_independent_vote(self):
        a,b = pair([poi(1)],[poi(1,source_provenance=[{'dataset':'Meta','license':'CDLA-Permissive-2.0'}])])
        x = run(a,b,bundle(a,b,[event(1,'unchanged')]))
        self.assertEqual(x['routing']['metadata_only_ids'],1)
        self.assertEqual(x['independent_business_evidence_count'],0)

    def test_cross_schema_only_goes_to_technical_review(self):
        a,b = pair([poi(1,taxonomy_primary=None)],[poi(1)])
        x = run(a,b,bundle(a,b,[event(1,'data_changed',['taxonomy'])]))
        self.assertEqual(x['routing']['schema_only_ids'],1)
        self.assertEqual(x['routing']['property_review_ids'],0)
        self.assertIn('taxonomy',x['schema']['not_semantically_comparable'])
        self.assertEqual(x['official']['outcome_counts']['NOT_OBSERVABLE_OR_SCHEMA_AMBIGUOUS'],1)

    def test_schema_and_name_change_keeps_property_review(self):
        a,b = pair([poi(1,taxonomy_primary=None)],[poi(1,name='Synthetic rename')])
        x = run(a,b,bundle(a,b,[event(1,'data_changed',['names','taxonomy'])]))
        self.assertEqual(x['routing']['property_review_ids'],1)
        self.assertEqual(x['routing']['schema_only_ids'],0)

    def test_names_primary_projection_does_not_prove_all_names_unchanged(self):
        a,b = pair()
        x = run(a,b,bundle(a,b,[event(1,'data_changed',['names'])]))
        self.assertEqual(x['official']['outcome_counts']['NOT_OBSERVABLE_OR_SCHEMA_AMBIGUOUS'],1)
        self.assertIn('names',x['schema']['partially_observed_top_level_columns'])

    def test_unretained_websites_change_is_explicit(self):
        a,b = pair()
        x = run(a,b,bundle(a,b,[event(1,'data_changed',['websites'])]))
        self.assertEqual(x['official']['unobserved_columns'],['websites'])

    def test_comparable_property_contradiction_is_kept(self):
        a,b = pair([poi(1)],[poi(1,name='Synthetic rename')])
        x = run(a,b,bundle(a,b,[event(1,'unchanged')]))
        self.assertEqual(x['official']['outcome_counts']['CONTRADICTION'],1)
        self.assertEqual(len(x['conflicts']),1)
        self.assertEqual(x['conflicts'][0]['official_events'][0]['change_type'],'unchanged')

    def test_duplicate_official_repost_is_one_source_observation(self):
        a,b = pair()
        x = run(a,b,bundle(a,b,[event(1,'unchanged'),event(1,'unchanged')]))
        self.assertEqual(x['official']['duplicate_rows_collapsed'],1)
        self.assertEqual(x['official']['observed_unique_ids'],1)
        self.assertEqual(x['independent_business_evidence_count'],0)

    def test_conflicting_official_reposts_are_not_last_write_wins(self):
        a,b = pair()
        ev = [event(1,'unchanged'),event(1,'removed')]
        x = run(a,b,bundle(a,b,ev))
        y = run(a,b,bundle(a,b,list(reversed(ev))))
        self.assertEqual(x['conflicts'],y['conflicts'])
        self.assertEqual(x['official']['status'],'CONFLICTED')
        self.assertEqual(len(x['conflicts'][0]['official_events']),2)

    def test_missing_event_is_not_unchanged(self):
        a,b = pair([poi(1),poi(2)],[poi(1)])
        x = run(a,b,bundle(a,b,[event(1,'unchanged')]))
        self.assertEqual(x['official']['status'],'INCOMPLETE')
        self.assertIsNone(x['official']['membership_agreement_fraction'])
        self.assertEqual(x['official']['missing_union_ids'],1)

    def test_bbox_capture_cannot_claim_exhaustive_id_reconciliation(self):
        a,b = pair()
        c = bundle(a,b,[event(1,'unchanged')]);c['query']['mode']='bbox_partial'
        x = run(a,b,c)
        self.assertEqual(x['official']['status'],'PARTIAL_SCOPE')
        self.assertIsNone(x['official']['membership_agreement_fraction'])

    def test_unscanned_partitions_block_complete_agreement(self):
        a,b = pair()
        c = bundle(a,b,[event(1,'unchanged')]);c['query']['all_partitions_scanned']=False
        self.assertEqual(run(a,b,c)['official']['status'],'PARTIAL_SCOPE')

    def test_unverified_release_transition_blocks_comparison(self):
        a,b = pair()
        c = bundle(a,b,[event(1,'unchanged')]);c['transition_evidence']['status']='unverified'
        x = run(a,b,c)
        self.assertEqual(x['official']['status'],'PAIR_NOT_VERIFIED')
        self.assertIsNone(x['official']['membership_agreement_fraction'])

    def test_wrong_predecessor_rejected_even_for_same_target(self):
        a,b = pair()
        c = bundle(a,b,[event(1,'unchanged')],before_release='2026-09-23.0')
        with self.assertRaises(ValueError):run(a,b,c)

    def test_checksum_required_and_tampering_rejected(self):
        a,b = pair();c = bundle(a,b,[event(1,'unchanged')])
        with self.assertRaises(ValueError):reconcile(a,b,changelog=c)
        with self.assertRaises(ValueError):reconcile(a,b,changelog=c,expected_changelog_sha256='0'*64)

    def test_query_union_checksum_rejected(self):
        a,b = pair();c = bundle(a,b,[event(1,'unchanged')]);c['query']['ids_sha256']='0'*64
        with self.assertRaises(ValueError):run(a,b,c)

    def test_unknown_event_and_excluded_columns_fail_closed(self):
        a,b = pair()
        for ev in (event(1,'closed'),event(1,'data_changed',['confidence']),
                   event(1,'data_changed',['sources']),event(1,'data_changed',[]),
                   event(1,'unchanged',['names'])):
            with self.subTest(ev=ev),self.assertRaises(ValueError):run(a,b,bundle(a,b,[ev]))

    def test_unknown_top_level_column_preserved_not_guessed(self):
        a,b = pair()
        x = run(a,b,bundle(a,b,[event(1,'data_changed',['future_property'])]))
        self.assertIn('future_property',x['official']['unobserved_columns'])

    def test_private_extra_event_field_rejected(self):
        a,b = pair();e = event(1,'unchanged');e['reviewer_email']='not-real@example.invalid'
        with self.assertRaises(ValueError):run(a,b,bundle(a,b,[e]))

    def test_non_union_event_rejected_for_exact_id_query(self):
        a,b = pair()
        with self.assertRaises(ValueError):run(a,b,bundle(a,b,[event(2,'unchanged')]))

    def test_synthetic_capture_cannot_become_real_evidence(self):
        a,b = pair()
        c = bundle(a,b,[event(1,'unchanged')],origin='official_capture',
            source_url='https://overturemaps-us-west-2.s3.us-west-2.amazonaws.com/changelog/'+NEW+'/theme=places/type=place/')
        with self.assertRaises(ValueError):run(a,b,c)

    def test_mutated_source_snapshot_stops_before_findings(self):
        a,b = pair();b.records[0]['name']='tampered'
        with self.assertRaises(ValueError):run(a,b)

    def test_cross_schema_identity_hint_does_not_require_category_equality(self):
        a,b = pair([poi(1,basic_category=None,taxonomy_primary=None)],
                   [poi(2,basic_category='restaurant',taxonomy_primary='restaurant')])
        x = run(a,b)
        self.assertEqual(len(x['identity_review']['candidates']),1)
        self.assertFalse(x['identity_review']['automatic_merge'])
        self.assertFalse(x['identity_review']['category_used_as_identity_evidence'])

    def test_distant_same_name_does_not_match(self):
        a,b = pair([poi(1,lon=29.0021)],[poi(2,lon=29.0099)])
        self.assertEqual(run(a,b)['identity_review']['candidates'],[])

    def test_none_name_cannot_create_identity_hint(self):
        a,b = pair([poi(1,name=None)],[poi(2,name=None)])
        self.assertEqual(run(a,b)['identity_review']['candidates'],[])

    def test_no_mutation_and_stable_output(self):
        a,b = pair([poi(1),poi(2)],[poi(2),poi(3)])
        before = copy.deepcopy((a.records,b.records))
        self.assertEqual(run(a,b),run(a,b))
        self.assertEqual(before,(a.records,b.records))


if __name__ == '__main__':
    unittest.main()
