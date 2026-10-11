"""DATA-015: real source receipt checks, separate from synthetic policy tests."""
import json
import unittest
from unittest.mock import patch
from pathlib import Path

from scripts.review_gers_region_events import (PINNED_SHA256, REPORT, evaluate,
                                                 validate_receipt)


class PinnedRealRegionalEvents(unittest.TestCase):
    def test_original_source_receipt_exact_integrity(self):
        from hashlib import sha256
        raw=REPORT.read_bytes()
        self.assertEqual(sha256(raw).hexdigest(), PINNED_SHA256)
        data=validate_receipt(raw)
        self.assertEqual(data['status'],
                         'REGIONAL_OBSERVATIONS_CAPTURED_NOT_COMPLETE_ID_UNION')
        self.assertEqual(data['aggregate']['regional_rows'],285)
        self.assertEqual(data['aggregate']['regional_event_type_counts']['added'],218)
        self.assertEqual(data['aggregate']['regional_event_type_counts']['removed'],67)
        self.assertEqual(data['aggregate']['scanned_rows'],207733)
        self.assertEqual(data['data_page_response_bytes'],8022067)
        self.assertEqual(data['request_count'],14)

    def test_official_agreement_and_business_truth_still_unknown(self):
        observed=evaluate()
        self.assertIsNone(observed['official_membership_agreement_fraction'])
        self.assertIsNone(observed['physical_business_openings'])
        self.assertIsNone(observed['physical_business_closures'])
        self.assertFalse(observed['complete_for_all_union_ids'])
        self.assertIsNone(observed['publisher_patch_scope']['verified_changelog_comparison_baseline'])
        self.assertFalse(observed['consumer_publish'])
        self.assertFalse(observed['aggregate']['safe_to_reconcile_membership'])
        self.assertEqual(observed['aggregate']['matched_union_ids'],285)

    def test_mutation_is_rejected_not_accepted_as_new_evidence(self):
        raw=REPORT.read_bytes()
        mutated=raw.replace(b'"regional_rows":285',b'"regional_rows":286')
        self.assertNotEqual(raw,mutated)
        with self.assertRaises(ValueError):
            validate_receipt(mutated)

    def test_offline_no_arrow_no_source_access(self):
        with patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('network')):
            observed=evaluate()
        self.assertEqual(observed['scope'],'regional_bbox_rows_only')
        self.assertEqual(observed['source_root'],'overturemaps')
        self.assertEqual(observed['captured_change_types'],['added','removed'])

if __name__=='__main__':
    unittest.main()
