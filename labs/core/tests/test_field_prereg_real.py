"""Only actual research FRAME and hash commitments, never real human truth labels."""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path
import json
import re
import unittest
from kepcore.overture_real import DATA_DIR, load_archive

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/'reports/KEP_FIELD_001_PREREGISTRATION.json'
PLAN_SHA='3d728f609810c418179404d7cb6e45f484819d5e18d49e3b968c5bdcb8090a14'
LOCK_SHA='2a09b337e17d240f5dbdb63ea44dd8201e8e4b38b3a09c3c345825085de726bd'
SEED_COMMIT='36ad1f725c3db1510397680d873a32434373a6bca8de68b267c621555c3fe4a6'


class RealUnlabeledPilotPrerecord(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d=json.loads(REPORT.read_text())
        cls.source,_,cls.meta=load_archive(DATA_DIR)

    def test_exact_real_source_and_cohort_commitment(self):
        self.assertEqual(self.meta['release'],'2026-09-23.1')
        self.assertEqual(len(self.source['records']),4803)
        self.assertEqual(self.d['sample_n'],60)
        self.assertEqual(self.d['population_n'],4803)
        self.assertEqual(self.d['source_snapshot_compressed_sha256'],self.meta['compressed_sha256'])
        self.assertEqual(self.d['private_sample_plan_sha256'],PLAN_SHA)
        self.assertEqual(self.d['private_per_case_prediction_lock_sha256'],LOCK_SHA)
        self.assertEqual(self.d['private_sampling_seed_committed_sha256'],SEED_COMMIT)

    def test_real_human_labels_and_business_claims_not_invented(self):
        self.assertEqual(self.d['reviewer_a_completed'],0)
        self.assertEqual(self.d['reviewer_b_completed'],0)
        self.assertEqual(self.d['missing_or_late'],60)
        self.assertIsNone(self.d['weighted_source_nonexistence_fraction'])
        self.assertIsNone(self.d['claim_accuracy'])
        self.assertIsNone(self.d['physical_business_openings'])
        self.assertIsNone(self.d['physical_business_closures'])
        self.assertFalse(self.d['human_reviewers_attested_independent'])

    def test_public_prereg_is_aggregate_only(self):
        raw=REPORT.read_text()
        self.assertFalse(re.search(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',raw))
        self.assertNotIn('"evidence_url"',raw)
        self.assertNotIn('reviewer_id',raw)
        self.assertFalse(self.d['private_seed_or_POI_rows_published'])
        self.assertFalse(self.d['consumer_publish'])
        self.assertFalse(self.d['original_historical_60_cohort_reused'])

    def test_precision_forecast_not_a_measured_accuracy(self):
        self.assertEqual(self.d['design_based_nominal_95pct_half_width_fraction'],0.517502)
        self.assertFalse(self.d['design_precision_target_met'])
        self.assertEqual(self.d['naive_baseline_automatic_assertions'],60)
        self.assertEqual(self.d['kep_baseline_automatic_assertions'],0)
        self.assertIsNone(self.d['claim_accuracy'])


if __name__=='__main__':
    unittest.main()
