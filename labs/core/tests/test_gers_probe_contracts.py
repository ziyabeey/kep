"""Synthetic and mocked transport contracts only. No live publisher rows."""
import unittest
from unittest.mock import patch
from kepcore.gers_region_probe import (RangeBudget, validate_response, validate_event,
    summarize_events, publisher_patch_scope)


class ProbeContractTests(unittest.TestCase):
    def test_budget_reservation_and_unbounded_reads(self):
        b=RangeBudget(limit=10,requests=2)
        b.reserve(6);self.assertEqual(b.bytes_reserved,6)
        with self.assertRaises(ValueError): b.reserve(5)
        with self.assertRaises(ValueError): b.reserve(0)
        b.reserve(4)
        with self.assertRaises(ValueError): b.reserve(1)

    def test_budget_cannot_be_raised_above_fixed_cap(self):
        with self.assertRaises(ValueError):RangeBudget(limit=64*1024*1024)

    def test_bogus_source_range_is_not_accepted(self):
        obj={'size':100,'etag':'"sha"'}
        headers={'Content-Range':'bytes 10-19/100','Content-Length':'10','ETag':'"sha"'}
        validate_response(206,headers,10,19,obj,b'0'*10)
        for altered in [{'Content-Range':'bytes 9-19/100'}, {'ETag':'"wrong"'},
                        {'Content-Length':'11'},{'Content-Encoding':'gzip'}]:
            with self.subTest(altered=altered),self.assertRaises(ValueError):
                validate_response(206,{**headers,**altered},10,19,obj,b'0'*10)
        with self.assertRaises(ValueError):validate_response(200,headers,10,19,obj,b'0'*10)

    def test_non_utf8_canonical_id_rejected(self):
        for bad in ['',None,'spoof','00000000-0000-0000-0000-0000000000AA']:
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                validate_event({'id':bad,'bbox':{'xmin':29.,'xmax':29.01,'ymin':41.,'ymax':41.01},'columns_changed':None},'added')

    def test_invalid_bbox_and_unknown_columns_stop(self):
        x={'id':'00000000-0000-0000-0000-000000000001',
           'bbox':{'xmin':29.,'xmax':29.01,'ymin':41.,'ymax':41.01},'columns_changed':None}
        validate_event(x,'added')
        for bb in ({'xmin':float('nan'),'xmax':30,'ymin':40,'ymax':42},
                   {'xmin':30,'xmax':29,'ymin':40,'ymax':42},
                   {'xmin':29,'xmax':30,'ymin':40}):
            with self.subTest(bb=bb),self.assertRaises(ValueError):
                validate_event({**x,'bbox':bb},'added')
        with self.assertRaises(ValueError):
            validate_event({**x,'columns_changed':['names']},'removed')
        validate_event({**x,'columns_changed':['names','geometry']},'data_changed')

    def test_publisher_scope_not_a_comparison_baseline_attestation(self):
        x=publisher_patch_scope()
        self.assertEqual(x['patch_release'],'2026-09-23.1')
        self.assertEqual(x['stated_patch_targets'],['base','building_parts'])
        self.assertFalse(x['places_explicitly_named_as_patch_target'])
        self.assertIsNone(x['verified_changelog_comparison_baseline'])
        self.assertFalse(x['may_sum_september_changelogs_as_independent_hops'])

    def test_synthetic_counting_retains_contradiction_and_no_physical_truth(self):
        rid='00000000-0000-0000-0000-000000000001'
        row={'id':rid,'bbox':{'xmin':29.004,'xmax':29.004,'ymin':41.04,'ymax':41.04},'columns_changed':None}
        report=summarize_events([('added',row),('removed',row),('removed',row)],{rid},
                                origin='synthetic_test_fixture')
        self.assertEqual(report['unique_regional_ids'],1)
        self.assertEqual(report['conflicting_regional_ids'],1)
        self.assertEqual(report['duplicate_exact_observations'],1)
        self.assertFalse(report['safe_to_reconcile_membership'])
        self.assertIsNone(report['official_membership_agreement_fraction'])
        self.assertIsNone(report['physical_business_closures'])
        self.assertFalse(report['consumer_publish'])
        self.assertEqual(report['origin'],'synthetic_test_fixture')

    def test_non_matching_bbox_not_counted_in_region(self):
        rid='00000000-0000-0000-0000-000000000001'
        row={'id':rid,'bbox':{'xmin':0.,'xmax':1.,'ymin':0.,'ymax':1.},'columns_changed':None}
        report=summarize_events([('added',row)],{rid},origin='synthetic_test_fixture')
        self.assertEqual(report['regional_rows'],0)
        self.assertEqual(report['scanned_rows'],1)
        self.assertIsNone(report['official_membership_agreement_fraction'])

    def test_duplicate_rows_do_not_become_independent_evidence(self):
        rid='00000000-0000-0000-0000-000000000001'
        row={'id':rid,'bbox':{'xmin':29.004,'xmax':29.004,'ymin':41.04,'ymax':41.04},'columns_changed':None}
        result=summarize_events([('added',row),('added',row)],{rid},origin='synthetic_test_fixture')
        self.assertEqual(result['regional_rows'],1)
        self.assertEqual(result['duplicate_exact_observations'],1)
        self.assertEqual(result['matched_union_ids'],1)


if __name__=='__main__': unittest.main()
