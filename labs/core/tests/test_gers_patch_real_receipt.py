"""REAL captured DATA-016 aggregate; no real-world truth labels or raw IDs."""
import unittest
from hashlib import sha256
from unittest.mock import patch
from scripts.review_gers_patch import evaluate,validate_receipt,REPORT,REPORT_SHA256

class PinnedRealPatchReceipt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d=evaluate()

    def test_original_report_digest(self):
        self.assertEqual(sha256(REPORT.read_bytes()).hexdigest(),REPORT_SHA256)
        self.assertEqual(self.d['status'],'PATCH_REGIONAL_PROJECTION_CAPTURED_NOT_BASELINE_VERIFIED')

    def test_real_fingerprint_and_source_cost(self):
        self.assertTrue(self.d['regional_patch_comparison']['regional_observation_sets_equal'])
        self.assertEqual(self.d['aggregate']['regional_rows'],285)
        self.assertEqual(self.d['data_page_response_bytes'],8022067)
        self.assertEqual(self.d['request_count'],14)
        self.assertEqual(self.d['scanned_rows'],207733)

    def test_scoped_equality_cannot_prove_full_objects_or_lineage(self):
        x=self.d['regional_patch_comparison']
        self.assertEqual(x['before_region_sha256'],x['after_region_sha256'])
        self.assertIsNone(x['full_parquet_objects_equal'])
        self.assertIsNone(x['verified_changelog_comparison_baseline'])
        self.assertIsNone(x['official_membership_agreement_fraction'])
        self.assertFalse(x['safe_to_compose_as_independent_adjacent_hops'])
        self.assertFalse(self.d['consumer_publish'])

    def test_receipt_tampering_fails(self):
        with self.assertRaises(ValueError):validate_receipt(REPORT.read_bytes()+b' ')

    def test_replay_has_no_network_or_arrow(self):
        with patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('NETWORK')):
            self.assertEqual(evaluate(),self.d)

if __name__=='__main__':unittest.main()
