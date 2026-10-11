"""Untampered REAL archives only. No synthetic changelog is used as real evidence."""
import copy
from hashlib import sha256
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from kepcore.gers_reconciliation import (
    load_pinned_pair, reconcile, public_summary, assess_changelog_compatibility,
)


class PinnedRealReconciliationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before,cls.after=load_pinned_pair()
        cls.result=reconcile(cls.before,cls.after,allow_historical_backfill=True)

    def test_real_population_accounting(self):
        r=self.result['source_record_delta']
        self.assertEqual((len(self.before.records),len(self.after.records)),(4650,4803))
        self.assertEqual((r['retained_ids'],r['newly_listed_ids'],r['no_longer_listed_ids']),(4581,222,69))
        self.assertEqual((r['field_or_geometry_revised_ids'],r['confidence_only_revised_ids'],r['unchanged_ids']),(198,3337,1046))

    def test_replayed_drift_not_truth_probability(self):
        d=self.result['drift_summary']
        self.assertEqual((d['confidence_changed_count'],d['confidence_abs_delta_over_0_05']),(3513,256))
        self.assertEqual(d['schema_only_revisions_cross_version_not_truth'],36)
        self.assertFalse(d['score_calibrated_truth_probability'])

    def test_exclusive_routing_and_review_scope(self):
        self.assertEqual(self.result['routing'],dict(membership_review_ids=291,
            property_review_ids=162,schema_only_ids=36,metadata_only_ids=3337,unchanged_local_ids=1046))
        self.assertEqual(len(self.result['review_queue']),489)
        self.assertTrue(all(x['targeted_not_random'] for x in self.result['review_queue']))

    def test_identity_queue_is_four_unverified_pairs_not_four_merges(self):
        self.assertEqual(self.result['legacy_identity_hint_count'],3)
        self.assertEqual(len(self.result['identity_review']['candidates']),4)
        self.assertFalse(self.result['identity_review']['automatic_merge'])
        self.assertFalse(self.result['identity_review']['candidate_recall_measured'])

    def test_real_changelog_absence_does_not_become_matching_events(self):
        o=self.result['official']
        self.assertEqual(o['observed_unique_ids'],0)
        self.assertIsNone(o['membership_agreement_fraction'])
        self.assertEqual(o['status'],'NOT_AVAILABLE')
        self.assertEqual(self.result['official_outcomes'],[])

    def test_real_catalog_requires_intermediate_patch(self):
        c=assess_changelog_compatibility()
        self.assertEqual(c['status'],'REQUIRES_INTERMEDIATE_RELEASE')
        self.assertEqual(c['release_chain'],['2026-08-19.0','2026-09-23.0','2026-09-23.1'])
        self.assertFalse(c['direct_pair_comparison_allowed'])
        self.assertFalse(c['complete_event_capture_available'])

    def test_successful_workflow_is_not_successful_data_capture(self):
        a=assess_changelog_compatibility()['capture_attempt']
        self.assertEqual(a['status'],'INCOMPLETE_CAPTURE')
        self.assertEqual(a['official_event_rows'],0)
        self.assertLessEqual(a['bytes_transferred'],a['budget_bytes'])

    def test_no_raw_ids_or_poi_fields_in_public_report(self):
        s=str(public_summary(self.result))
        for row in self.before.records[:20]:
            self.assertNotIn(row['overture_id'],s)
        self.assertNotIn('official_events',s)
        self.assertNotIn('review_queue\':',s)

    def test_real_replay_has_no_network(self):
        with patch('socket.socket',side_effect=AssertionError('Network forbidden')):
            a,b=load_pinned_pair()
            self.assertEqual(public_summary(reconcile(a,b,allow_historical_backfill=True)),public_summary(self.result))

    def test_no_business_labels_or_publishing(self):
        self.assertIsNone(self.result['physical_closures'])
        self.assertIsNone(self.result['physical_openings'])
        self.assertIsNone(self.result['business_event_accuracy'])
        self.assertEqual(self.result['independent_business_evidence_count'],0)
        self.assertFalse(self.result['consumer_publish'])


if __name__=='__main__':unittest.main()
