"""Actual archived Overture records: integrity and scientific boundaries only.

No test asserts physical venue existence or calibrated confidence.
"""
from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import gzip
import json
import shutil
import subprocess
import sys
import unittest

from kepcore.overture_real import (
    DATA_DIR, MAX_UNCOMPRESSED_BYTES, EXPECTED_COUNT, load_archive,
    quality_report, core_research_candidates, check_core_publish_gate,
    prepare_private_audit,
)
from kepcore.overture_audit import confidence_band
from kepcore.overture_places import canonical
from kepcore.core import Query, decide

SEED='KEP-PUBLIC-CI-SEED-ONLY-NOT-A-REAL-FIELD-AUDIT'
AFTER_ACQUISITION='2026-10-11T01:00:00Z'


def editable_snapshot() -> tuple[TemporaryDirectory,Path]:
    d=TemporaryDirectory()
    base=Path(d.name)
    for name in ['places_minimal.json.gz','manifest.json','archive_metadata.json']:
        shutil.copy2(DATA_DIR/name,base/name)
    return d,base


class RealPOIReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc,cls.manifest,cls.meta=load_archive()
        cls.report=quality_report()

    def test_exact_real_count(self):
        self.assertEqual(len(self.doc['records']),4803)
        self.assertEqual(self.meta['record_count'],EXPECTED_COUNT)

    def test_two_bounded_cells(self):
        self.assertEqual(self.report['by_cell'],{'besiktas_center':1872,'karakoy_center':2931})

    def test_verified_normalized_hash(self):
        self.assertEqual(self.meta['normalized_sha256'],
                         sha256(canonical(self.doc)).hexdigest())

    def test_verified_manifest_hash(self):
        self.assertEqual(sha256(canonical(self.manifest)).hexdigest(),self.meta['manifest_sha256'])

    def test_archive_provenance(self):
        self.assertEqual(self.meta['original_actions_run_id'],38096227796)
        self.assertEqual(self.meta['release'],'2026-09-23.1')
        self.assertFalse(self.meta['raw_source_sha256_independently_verified'])
        self.assertFalse(self.meta['consumer_display_approved'])

    def test_real_missing_fields_not_synthetic(self):
        self.assertEqual(self.report['missing_address'],422)
        self.assertEqual(self.report['missing_taxonomy'],131)
        self.assertEqual(self.report['missing_name'],0)

    def test_research_dup_hints_are_not_merged(self):
        self.assertEqual(self.report['candidate_duplicate_pairs_conservative'],3)
        self.assertEqual(len(self.doc['records']),4803)

    def test_actual_category_counts(self):
        from collections import Counter
        d=Counter(r['basic_category'] for r in self.doc['records'])
        self.assertEqual(d['restaurant'],548)
        self.assertEqual(d['cafe'],214)
        self.assertEqual(d['coffee_shop'],147)

    def test_all_live_fields_unknown(self):
        for row in self.doc['records']:
            self.assertIsNone(row['open_now'])
            self.assertIsNone(row['opening_hours'])
            self.assertIsNone(row['live_price'])
            self.assertIsNone(row['active_event'])
            self.assertFalse(row['consumer_verified'])

    def test_no_human_ground_truth(self):
        self.assertEqual(self.report['human_confirmed_businesses'],0)
        self.assertEqual(self.manifest['human_verified_labels'],0)
        self.assertEqual(self.report['live_open_now_observations'],0)

    def test_actual_confidence_bands_are_not_truth(self):
        self.assertEqual(self.report['confidence_bands'],{'high':1879,'low':1115,'medium':1809})
        self.assertEqual(sum(self.report['confidence_bands'].values()),4803)

    def test_provenance_license_mixture(self):
        observed={x['license'] for x in self.report['provider_license_rows']}
        self.assertEqual(observed,{'CC0-1.0','Apache-2.0','CDLA-Permissive-2.0'})

    def test_source_raw_files_not_present(self):
        self.assertEqual(len(self.manifest['source_files']),2)
        self.assertFalse(self.report['source_files_stored'])
        self.assertFalse(self.report['upstream_authenticated_independently'])

    def test_candidate_only_research_rights(self):
        c=core_research_candidates(limit=12,basic_category='restaurant')
        self.assertEqual(len(c),12)
        self.assertTrue(all(r['kind']=='place' and r['rights_scope']=='research_ingest' for r in c))
        self.assertTrue(all(r['price'] is None and r['opening_hours'] is None for r in c))

    def test_core_gate_blocks_consumers(self):
        result=check_core_publish_gate()
        self.assertEqual(result['action'],'ABSTAIN')
        self.assertEqual(result['blocked'],25)
        self.assertTrue(result['no_consumer_display'])

    def test_no_live_api_calls_in_offline_replay(self):
        with patch('urllib.request.urlopen',side_effect=AssertionError('Unexpected network')):
            self.assertEqual(quality_report()['n'],4803)

    def test_same_input_same_report(self):
        self.assertEqual(quality_report(),self.report)

    def test_private_seed_produces_unlabeled_stratified_plan(self):
        result=prepare_private_audit(DATA_DIR,budget=60,seed=SEED,sampled_at=AFTER_ACQUISITION)
        self.assertEqual(len(result['unlabeled_review_sheet']),60)
        self.assertEqual(result['observed_label_count'],0)
        self.assertEqual(len(result['plan']['strata']),6)
        self.assertTrue(all(item['physical_existence_label']=='UNREVIEWED' for item in result['unlabeled_review_sheet']))
        self.assertNotIn(SEED,json.dumps(result))

    def test_plan_is_deterministic_at_frozen_population(self):
        first=prepare_private_audit(DATA_DIR,budget=60,seed=SEED,sampled_at=AFTER_ACQUISITION)
        second=prepare_private_audit(DATA_DIR,budget=60,seed=SEED,sampled_at=AFTER_ACQUISITION)
        self.assertEqual(first['plan'],second['plan'])

    def test_new_seed_selects_different_records(self):
        a=prepare_private_audit(DATA_DIR,budget=60,seed=SEED,sampled_at=AFTER_ACQUISITION)
        b=prepare_private_audit(DATA_DIR,budget=60,seed=SEED+'-different',sampled_at=AFTER_ACQUISITION)
        self.assertNotEqual(a['plan']['selected'],b['plan']['selected'])

    def test_cli_runs_offline(self):
        root=Path(__file__).resolve().parents[1]
        proc=subprocess.run([sys.executable,str(root/'scripts/real_overture_replay.py')],
                            cwd=root,capture_output=True,text=True,timeout=15)
        self.assertEqual(proc.returncode,0,proc.stderr)
        r=json.loads(proc.stdout)
        self.assertEqual(r['n'],4803)
        self.assertTrue(r['core_gate']['no_consumer_display'])

    def test_cannot_draw_sample_before_acquisition(self):
        with self.assertRaises(ValueError):
            prepare_private_audit(DATA_DIR,budget=60,seed=SEED,sampled_at='2026-10-10T20:00:00+00:00')

    def test_decompressed_bomb_rejected(self):
        d,root=editable_snapshot()
        try:
            contents=b'X'*(MAX_UNCOMPRESSED_BYTES+1)
            data=gzip.compress(contents,mtime=0)
            meta=json.loads((root/'archive_metadata.json').read_bytes())
            meta['compressed_sha256']=sha256(data).hexdigest()
            meta['compressed_bytes']=len(data)
            meta['normalized_sha256']=sha256(contents).hexdigest()
            meta['normalized_uncompressed_bytes']=len(contents)
            (root/'places_minimal.json.gz').write_bytes(data)
            (root/'archive_metadata.json').write_bytes(canonical(meta))
            with self.assertRaisesRegex(ValueError,'Expanded archive exceeds'):
                load_archive(root)
        finally:d.cleanup()

    def test_corrupt_compressed_payload_rejected(self):
        d,root=editable_snapshot()
        try:
            packed=(root/'places_minimal.json.gz').read_bytes()
            (root/'places_minimal.json.gz').write_bytes(packed[:-10]+b'0123456789')
            with self.assertRaisesRegex(ValueError,'Compressed archive SHA'):
                load_archive(root)
        finally:d.cleanup()

    def test_deleted_raw_snapshot_rejected(self):
        d,root=editable_snapshot()
        try:
            (root/'places_minimal.json.gz').unlink()
            with self.assertRaisesRegex(ValueError,'Missing, unsafe'):
                load_archive(root)
        finally:d.cleanup()

    def test_manifest_changed_not_allowed(self):
        d,root=editable_snapshot()
        try:
            meta=json.loads((root/'manifest.json').read_bytes())
            meta['consumer_display_approved']=True
            (root/'manifest.json').write_bytes(canonical(meta))
            with self.assertRaisesRegex(ValueError,'Manifest SHA-256'):
                load_archive(root)
        finally:d.cleanup()

    def test_forged_meta_cannot_grant_publish_rights(self):
        d,root=editable_snapshot()
        try:
            meta=json.loads((root/'archive_metadata.json').read_bytes())
            meta['consumer_display_approved']=True
            (root/'archive_metadata.json').write_bytes(canonical(meta))
            with self.assertRaisesRegex(ValueError,'boundary'):
                load_archive(root)
        finally:d.cleanup()

    def test_invalid_seed_cannot_sample(self):
        with self.assertRaises(ValueError):
            prepare_private_audit(DATA_DIR,budget=60,seed='short',sampled_at=AFTER_ACQUISITION)

    def test_symlink_archive_rejected(self):
        d,root=editable_snapshot()
        try:
            real=root/'original.gz'
            (root/'places_minimal.json.gz').rename(real)
            (root/'places_minimal.json.gz').symlink_to(real)
            with self.assertRaisesRegex(ValueError,'unsafe'):
                load_archive(root)
        finally:d.cleanup()

if __name__=='__main__':unittest.main()
