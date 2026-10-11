"""Controlled, synthetic, no-network field drift and triage policy tests."""
import copy
import unittest
from kepcore.overture_change_triage import (
    POLICY_VERSION, inspect_releases, build_targeted_queue, safe_public_summary,
)


def poi(uid,*,confidence=.8,**overrides):
    r=dict(overture_id=uid, name='Test place',address=None,
       basic_category='cafe',taxonomy_primary='cafe',operating_status=None,
       locality='Test',country='TR',source_provenance=[],lon=29.,lat=41.,
       cell='besiktas_center',confidence=confidence,
       active_event=None, administrative_district=None, consumer_verified=False,
       live_price=None, open_now=None, opening_hours=None)
    r.update(overrides)
    return r


class DriftTests(unittest.TestCase):
    def test_all_basic_lanes_and_no_closure_inference(self):
        old=[poi('removed'),poi('unchanged'),poi('field'),poi('schema'),poi('conf')]
        new=[poi('added'),poi('unchanged'),poi('field',name='New name'),
             poi('schema',taxonomy_primary='restaurant'),poi('conf',confidence=.3)]
        x=inspect_releases(old,new)
        summary=x['summary']
        self.assertEqual((summary['source_ids_old'],summary['source_ids_new'],summary['retained_ids']),(5,5,4))
        self.assertEqual((summary['no_longer_listed_ids'],summary['newly_listed_ids']),(1,1))
        self.assertEqual(summary['source_fields_revised'],2)
        self.assertEqual(summary['schema_only_revisions_cross_version_not_truth'],1)
        self.assertEqual(summary['confidence_only_revisions'],1)
        self.assertEqual(summary['retained_ids_no_changes'],1)
        self.assertIsNone(summary['physical_closures']);self.assertIsNone(summary['physical_openings'])
        self.assertFalse(summary['category_semantics_comparable'])
    def test_missing_score_does_not_claim_numeric_magnitude(self):
        x=inspect_releases([poi('a',confidence=None)],[poi('a',confidence=.9)])['summary']
        self.assertEqual(x['confidence_only_revisions'],1)
        self.assertEqual(x['confidence_missing_in_pair'],1)
        self.assertEqual(x['confidence_only_abs_delta_over_0_05'],0)
    def test_nonsemantic_source_order_ignored(self):
        a=[{'provider':'one'},{'provider':'two'}]
        x=inspect_releases([poi('a',source_provenance=a)],
                           [poi('a',source_provenance=a[::-1])])['summary']
        self.assertEqual(x['retained_ids_no_changes'],1)
    def test_name_revision_and_score_overlap_not_double_count(self):
        x=inspect_releases([poi('a')],[poi('a',name='changed',confidence=.2)])['summary']
        self.assertEqual(x['score_and_field_changes_overlap'],1)
        self.assertEqual(x['confidence_only_revisions'],0)
    def test_confidence_exact_threshold_distinguishes_small(self):
        old=[poi('a',confidence=.5),poi('b',confidence=.5),poi('c',confidence=.5)]
        new=[poi('a',confidence=.501),poi('b',confidence=.61),poi('c',confidence=.9)]
        x=inspect_releases(old,new)['summary']
        self.assertEqual(x['confidence_changed_count'],3)
        self.assertEqual(x['confidence_abs_delta_over_0_05'],2)
        self.assertEqual(x['confidence_abs_delta_over_0_10'],2)
        self.assertEqual(x['confidence_only_abs_delta_over_0_10'],2)
        self.assertEqual(x['paired_confidence_delta_mean'],round((.001+.11+.4)/3,6))
    def test_provenance_content_change_reported(self):
        x=inspect_releases([poi('a',source_provenance=[{'provider':'a'}])],
                           [poi('a',source_provenance=[{'provider':'b'}])])['summary']
        self.assertEqual(x['field_revision_counts_nonexclusive']['source_provenance'],1)
    def test_geometry_revision_counts_once(self):
        x=inspect_releases([poi('a')],[poi('a',lon=29.01,lat=41.01)])['summary']
        self.assertEqual(x['field_revision_counts_nonexclusive']['geometry'],1)
    def test_null_to_known_name_is_not_truth(self):
        x=inspect_releases([poi('a',name=None)],[poi('a',name='new')])['summary']
        self.assertEqual(x['source_fields_revised'],1);self.assertEqual(x['human_truth_labels'],0)
    def test_repeated_ids_rejected(self):
        with self.assertRaisesRegex(ValueError,'repeated'):
            inspect_releases([poi('a'),poi('a')],[poi('a')])
    def test_no_partial_empty_frame(self):
        with self.assertRaises(ValueError):inspect_releases([],[poi('a')])
    def test_nan_score_rejected(self):
        for bad in (float('nan'),float('inf'),True,-1,1.1):
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                inspect_releases([poi('a',confidence=bad)],[poi('a')])
    def test_inf_coordinate_rejected(self):
        with self.assertRaises(ValueError):inspect_releases([poi('a',lat=float('inf'))],[poi('a')])
    def test_extra_personal_fields_rejected(self):
        r=poi('a');r['phones']=['private']
        with self.assertRaises(ValueError):inspect_releases([r],[poi('a')])
    def test_live_status_invented_rejected(self):
        with self.assertRaises(ValueError):inspect_releases([poi('a',open_now=True)],[poi('a')])
    def test_unapproved_cell_rejected(self):
        with self.assertRaises(ValueError):inspect_releases([poi('a',cell='istanbul_all')],[poi('a')])
    def test_missing_source_fields_rejected(self):
        r=poi('a');r.pop('name')
        with self.assertRaises(ValueError):inspect_releases([r],[poi('a')])
    def test_deterministic_reordering(self):
        aa=[poi('a'),poi('b'),poi('c')]
        bb=[poi('d'),poi('b',name='B'),poi('a'),poi('c',confidence=.4)]
        self.assertEqual(inspect_releases(aa,bb),inspect_releases(list(reversed(aa)),list(reversed(bb))))
    def test_safe_public_summary_has_no_poi_fields(self):
        d=safe_public_summary(inspect_releases([poi('a',name='private')],[poi('a')]))
        raw=str(d)
        self.assertNotIn('private',raw);self.assertNotIn('overture_id',raw)


class QueueTests(unittest.TestCase):
    def test_fixed_quotas_and_disjoint_lanes(self):
        old=[poi(f'r{i}') for i in range(10)]+[poi(f'f{i}') for i in range(10)]
        new=[poi(f'n{i}') for i in range(10)]+[poi(f'f{i}',name='newname') for i in range(10)]
        x=inspect_releases(old,new)
        q=build_targeted_queue(x,quotas=dict(no_longer_listed=3,newly_listed=4,
               property_or_location=5,schema_only=0,confidence_only_over_0_10=0))
        self.assertEqual(q['total_selected'],12)
        self.assertEqual(len(set(v['overture_id'] for v in q['items'])),12)
        self.assertFalse(q['can_estimate_error_rate']);self.assertFalse(q['unbiased_audit'])
    def test_queue_deterministic_no_labels(self):
        old=[poi(f'r{i}') for i in range(30)]+[poi('s')]
        new=[poi('s')]
        self.assertEqual(build_targeted_queue(inspect_releases(old,new)),
                         build_targeted_queue(inspect_releases(old,new)))
        self.assertEqual(POLICY_VERSION,'KEP-DATA-011-TRIAGE-v1')
    def test_invalid_quota_rejected(self):
        with self.assertRaises(ValueError):
            build_targeted_queue(inspect_releases([poi('a')],[poi('a')]),quotas={'newly_listed':3})
    def test_duplicate_across_lanes_rejected(self):
        x=inspect_releases([poi('a')],[poi('a')])
        x=copy.deepcopy(x)
        x['lanes']['no_longer_listed'].append({'overture_id':'a','review_reason':'source'})
        x['lanes']['newly_listed'].append({'overture_id':'a','review_reason':'source'})
        with self.assertRaises(ValueError):build_targeted_queue(x)

if __name__=='__main__':unittest.main()
