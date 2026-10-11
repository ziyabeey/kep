"""Pinned REAL footer metadata only. No synthetic GERS events or human labels."""
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from kepcore.gers_access_cost import DATA_DIR, PINNED_ZIP_SHA256, load_capture
from scripts.review_gers_footer import evaluate


class RealFooterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = evaluate()
        cls.capture = load_capture(DATA_DIR/'footers.zip', PINNED_ZIP_SHA256)

    def test_original_metadata_zip_hash(self):
        self.assertEqual(PINNED_ZIP_SHA256, '1cefe054f5b61adfa2117d43e441626ab5355fed1096aa105b397d70f619bf9d')
        self.assertEqual(sha256((DATA_DIR/'footers.zip').read_bytes()).hexdigest(), PINNED_ZIP_SHA256)

    def test_actual_inventory_is_two_releases_eight_partitions(self):
        r = self.report['stable_results']
        self.assertEqual((r['metadata_objects'], r['metadata_row_groups']), (128, 1244))
        self.assertEqual(len(r['by_partition']), 8)
        self.assertTrue(all(v['objects'] == 16 for v in r['by_partition'].values()))

    def test_actual_query_population_stays_4872(self):
        self.assertEqual(self.report['stable_results']['query_id_count'], 4872)

    def test_id_statistics_cannot_prune_any_group(self):
        p = self.report['stable_results']['policies']
        self.assertEqual(p['id_union']['candidate_groups'], 1244)
        self.assertEqual(p['id_union']['projected_chunk_bytes'], 5789190970)

    def test_bbox_smaller_is_not_complete_id_tracking(self):
        r = self.report['stable_results']; p = r['policies']['bbox']
        self.assertEqual(p['candidate_groups'], 8)
        self.assertEqual(p['projected_chunk_bytes'], 35805264)
        self.assertFalse(p['complete_for_id_union'])
        self.assertEqual(r['bbox_excluded_but_id_candidate_groups'], 1236)

    def test_actual_budget_and_request_accounting(self):
        c = self.report['observed_capture']
        self.assertEqual(c['body_bytes_read'], 1072094)
        self.assertEqual(c['accounted_body_allowance'], 2063202)
        self.assertEqual(c['request_count'], 392)
        self.assertLessEqual(c['body_bytes_read'], c['accounted_body_allowance'])
        self.assertLessEqual(c['accounted_body_allowance'], c['budget_bytes'])

    def test_metadata_aliases_do_not_authenticate_patch_baseline(self):
        a = self.report['metadata_alias_review']
        self.assertEqual(a['cross_release_identical_footer_etag_size_pairs'], 64)
        self.assertEqual(a['unique_footer_hashes'], 64)
        self.assertTrue(a['all_objects_have_cross_release_metadata_counterpart'])
        self.assertIsNone(a['verified_changelog_comparison_baseline'])
        self.assertFalse(a['event_content_equality_verified'])
        self.assertFalse(a['safe_to_compose_as_independent_adjacent_hops'])

    def test_metadata_row_totals_are_not_unique_places_or_truth(self):
        r = self.report['stable_results']
        self.assertEqual(r['metadata_source_rows'], 165169686)
        self.assertEqual(r['official_event_rows_read'], 0)
        self.assertEqual(r['data_page_bytes_read'], 0)
        self.assertIsNone(r['matched_ids'])
        self.assertIsNone(r['business_event_accuracy'])
        self.assertIsNone(r['membership_agreement_fraction'])
        self.assertFalse(r['consumer_publish'])

    def test_replay_is_offline_without_arrow(self):
        with patch('urllib.request.OpenerDirector.open', side_effect=AssertionError('network')):
            self.assertEqual(evaluate(), self.report)

    def test_capture_mutation_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'capture.zip'; raw=(DATA_DIR/'footers.zip').read_bytes()
            p.write_bytes(raw[:-1] + bytes([raw[-1] ^ 1]))
            with self.assertRaises(ValueError):load_capture(p,PINNED_ZIP_SHA256)

    def test_original_places_archives_are_not_replaced(self):
        p=DATA_DIR.parent/'overture_istanbul_2026-08-19.0/original_actions_artifact.zip'
        self.assertEqual(sha256(p.read_bytes()).hexdigest(),'cb9ee86c128b4839a00722e1b192f460691c0f33e358f0b0b9ae458ea403ef05')

    def test_stable_reference_report_matches(self):
        root=DATA_DIR.parents[2]/'reports'
        expected=json.loads((root/'KEP_DATA_014_FOOTER_RESULTS.json').read_text())
        self.assertEqual({k:self.report[k] for k in ('stable_results','observed_capture')}, expected)
        alias=json.loads((root/'KEP_DATA_014_ALIAS_REVIEW.json').read_text())
        self.assertEqual(alias, self.report['metadata_alias_review'])

if __name__=='__main__':unittest.main()
