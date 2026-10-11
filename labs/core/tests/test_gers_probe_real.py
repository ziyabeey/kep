"""Only immutable REAL metadata and REAL pinned August/September snapshot populations."""
import unittest
from kepcore.gers_access_cost import DATA_DIR,PINNED_ZIP_SHA256,load_capture
from kepcore.gers_reconciliation import load_pinned_pair
from kepcore.gers_region_probe import regional_plan


class PinnedRegionStudy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m=load_capture(DATA_DIR/'footers.zip',PINNED_ZIP_SHA256)
        cls.before,cls.after=load_pinned_pair()

    def test_exact_four_groups_in_one_release(self):
        plan=regional_plan(self.m)
        self.assertEqual(plan['target_release'],'2026-09-23.0')
        self.assertEqual(len(plan['selected']),4)
        self.assertEqual({x['change_type'] for x in plan['selected']},
                         {'added','removed','data_changed','unchanged'})
        self.assertEqual(sum(x['rows'] for x in plan['selected']),475582)

    def test_geo_filter_cannot_claim_all_tracked_ids(self):
        plan=regional_plan(self.m)
        self.assertFalse(plan['complete_id_union_scan'])
        self.assertEqual(plan['total_row_groups'],1244)
        self.assertEqual(plan['selected_one_release_groups'],4)
        self.assertEqual(plan['excluded_row_groups_across_both_releases'],1236)
        self.assertIsNone(plan['official_membership_agreement_fraction'])
        self.assertEqual(plan['data_pages_read'],0)

    def test_budget_is_explicitly_preflighted(self):
        p=regional_plan(self.m)
        self.assertLess(p['estimated_candidate_column_bytes'],32*1024*1024)
        self.assertGreater(p['estimated_candidate_column_bytes'],16*1024*1024)
        self.assertEqual(p['source_zip_sha256'],PINNED_ZIP_SHA256)
        self.assertFalse(p['consumer_publish'])

    def test_incomplete_inventory_does_not_pass(self):
        corrupted=dict(self.m)
        corrupted['status']='INCOMPLETE_METADATA'
        with self.assertRaises(ValueError):regional_plan(corrupted)


if __name__=='__main__':unittest.main()
