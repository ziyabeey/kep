"""KEP-DATA-002: synthetic POI contracts; NOT actual Istanbul verification."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import hashlib
import json
import subprocess
import sys
import unittest

from benchmarks.overture_places_eval import example
from kepcore.overture_audit import (
    POLICY, confidence_band, verify_artifact, design_existence_audit,
    estimate_existence_error,
)
from kepcore.overture_places import PILOT, canonical
from scripts.overture_istanbul import execute

SEED='not-real-private-seed-2026-10-11'
FREEZE='2026-10-11T09:00:00+03:00'
REVIEW='2026-10-12T09:00:00+03:00'
EVAL='2026-10-13T09:00:00+03:00'
ROOT=Path(__file__).resolve().parents[1]


def vote(name,outcome='exists',ts=REVIEW):
    return {'reviewer_id':name, 'outcome':outcome,'checked_at':ts,
            'evidence_url':'https://example.org/operator-review-evidence'}


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)
        inputs={}
        counter=10
        for cell in PILOT:
            rows=[]
            for j in range(14):
                v=example(counter,cell,f'Test POI {cell} {j}','cafe',
                          confidence=(None if j==0 else (.3 if j<4 else .7 if j<8 else .93)))
                rows.append(v);counter+=1
            path=self.base/f'{cell}.json'
            path.write_text(json.dumps({'type':'FeatureCollection','features':rows},ensure_ascii=False))
            inputs[cell]=path
        self.directory=self.base/'output'
        execute(output=self.directory,inputs=inputs,fetch=False,seed_file=None)

    def manifest(self):return json.loads((self.directory/'manifest.json').read_bytes())
    def dataset(self):return json.loads((self.directory/'places_minimal.json').read_bytes())

    def save(self, *, data=None,manifest=None, update_hashes=True):
        if data is None:data=self.dataset()
        if manifest is None:manifest=self.manifest()
        binary=canonical(data)
        if update_hashes:
            manifest['normalized_sha256']=hashlib.sha256(binary).hexdigest()
            manifest['population_sha256']=hashlib.sha256(canonical(data['records'])).hexdigest()
        (self.directory/'places_minimal.json').write_bytes(binary)
        (self.directory/'manifest.json').write_bytes(canonical(manifest))

    def plan(self,budget=12):
        return design_existence_audit(self.directory,budget=budget,seed=SEED,sampled_at=FREEZE)

    def labels(self,plan, outcomes=None):
        values=outcomes or {}
        return [{'overture_id':s['overture_id'],
                 'votes':[vote('a',values.get(s['overture_id'],'exists')),
                          vote('b',values.get(s['overture_id'],'exists'))]}
                 for s in plan['selected']]

    def test_offline_artifact_integrity_pass(self):
        r=verify_artifact(self.directory)
        self.assertTrue(r['artifact_integrity_verified'])
        self.assertFalse(r['upstream_acquisition_authenticated'])
        self.assertFalse(r['real_world_place_existence_verified'])
        self.assertEqual(r['population_n'],28)
    def test_offline_fixture_cannot_claim_authenticated_live(self):
        with self.assertRaisesRegex(ValueError,'Manually fetched'):
            verify_artifact(self.directory,require_live=True)
    def test_manifest_bytes_tampering(self):
        path=self.directory/'manifest.json'
        path.write_bytes(path.read_bytes()+b'  ')
        with self.assertRaisesRegex(ValueError,'canonical'):verify_artifact(self.directory)
    def test_poisoned_output_hash(self):
        data=self.dataset();data['records'][0]['name']='altered'
        self.save(data=data,update_hashes=False)
        with self.assertRaisesRegex(ValueError,'hash'):verify_artifact(self.directory)
    def test_poisoned_population_hash(self):
        data=self.dataset();man=self.manifest()
        data['records'][0]['name']='altered'
        self.save(data=data,manifest=man,update_hashes=True)
        self.assertTrue(verify_artifact(self.directory)['artifact_integrity_verified'])
        self.assertFalse(verify_artifact(self.directory)['upstream_acquisition_authenticated'])
    def test_refuses_extra_root_output_field(self):
        data=self.dataset();data['raw_personal_contacts']=['not_allowed']
        self.save(data=data)
        with self.assertRaisesRegex(ValueError,'envelope'):
            verify_artifact(self.directory)
    def test_refuses_extra_manifest_field(self):
        man=self.manifest();man['session_cookie']='private'
        self.save(manifest=man)
        with self.assertRaisesRegex(ValueError,'manifest envelope'):
            verify_artifact(self.directory)
    def test_refuses_extra_raw_file_metadata(self):
        man=self.manifest();man['source_files'][0]['raw_payload']='private'
        self.save(manifest=man)
        with self.assertRaisesRegex(ValueError,'raw source metadata'):
            verify_artifact(self.directory)
    def test_refuses_extra_audit_field(self):
        man=self.manifest();man['audit']['operator_notes']='unreviewed'
        self.save(manifest=man)
        with self.assertRaisesRegex(ValueError,'Unexpected audit'):
            verify_artifact(self.directory)
    def test_refuses_added_personal_contact_field(self):
        data=self.dataset();data['records'][0]['phone']='secret-number'
        self.save(data=data)
        with self.assertRaisesRegex(ValueError,'schema'):verify_artifact(self.directory)
    def test_refuses_fake_open_now(self):
        data=self.dataset();data['records'][0]['open_now']=True
        self.save(data=data)
        with self.assertRaisesRegex(ValueError,'real-time'):verify_artifact(self.directory)
    def test_refuses_fake_verified(self):
        data=self.dataset();data['records'][0]['consumer_verified']=True
        self.save(data=data)
        with self.assertRaisesRegex(ValueError,'consumer verification'):verify_artifact(self.directory)
    def test_refuses_box_escape(self):
        data=self.dataset();data['records'][0]['lon']=0.0
        self.save(data=data)
        with self.assertRaisesRegex(ValueError,'outside'):verify_artifact(self.directory)
    def test_refuses_duplicate_ids(self):
        data=self.dataset();data['records'][1]['overture_id']=data['records'][0]['overture_id']
        self.save(data=data)
        with self.assertRaisesRegex(ValueError,'unique'):verify_artifact(self.directory)
    def test_refuses_fake_complete_count(self):
        man=self.manifest();man['audit']['accepted']+=1
        self.save(manifest=man)
        with self.assertRaisesRegex(ValueError,'accepted'):verify_artifact(self.directory)
    def test_refuses_fake_raw_count(self):
        man=self.manifest();man['audit']['rows_read']+=1
        self.save(manifest=man)
        with self.assertRaisesRegex(ValueError,'accounting'):verify_artifact(self.directory)
    def test_refuses_missing_cell(self):
        man=self.manifest();man['source_files'].pop()
        self.save(manifest=man)
        with self.assertRaisesRegex(ValueError,'both'):verify_artifact(self.directory)
    def test_refuses_changed_attribution(self):
        man=self.manifest();man['license_evidence_url']='https://example.com'
        self.save(manifest=man)
        with self.assertRaisesRegex(ValueError,'attribution'):verify_artifact(self.directory)
    def test_refuses_wrong_release(self):
        man=self.manifest();man['pinned_release']='2026-08-19.0'
        self.save(manifest=man)
        with self.assertRaisesRegex(ValueError,'inconsistent'):verify_artifact(self.directory)
    def test_refuses_false_mean_confidence(self):
        man=self.manifest();man['audit']['mean_overture_confidence_not_truth']=.99
        self.save(manifest=man)
        with self.assertRaisesRegex(ValueError,'Mean Overture confidence'):
            verify_artifact(self.directory)
    def test_refuses_fake_acquisition(self):
        man=self.manifest();man['acquisition']['method']='manual_overturemaps_cli_stac_pinned'
        self.save(manifest=man)
        with self.assertRaisesRegex(ValueError,'acquisition fields'):verify_artifact(self.directory)
    def test_source_sha_manifest_is_not_upstream_authenticity(self):
        man=self.manifest();man['source_files'][0]['sha256']='f'*64
        self.save(manifest=man)
        report=verify_artifact(self.directory)
        self.assertFalse(report['raw_source_sha256_independently_verified'])
    def test_confidence_band_cutoffs_and_invalid(self):
        self.assertEqual([confidence_band(v) for v in (None,.1,.5,.6,.8,.9)],
                         ['missing','low','low','medium','medium','high'])
        for v in (-1,2,float('nan'),float('inf'),True):
            with self.subTest(value=v),self.assertRaises(ValueError):confidence_band(v)

    def test_audit_plan_reproducible(self):
        a=self.plan();b=self.plan()
        self.assertEqual(a,b)
        self.assertEqual(a['policy_version'],POLICY)
        self.assertEqual(len(a['selected']),12)
        self.assertEqual(a['verified_labels'],0)
        self.assertNotIn(SEED,json.dumps(a))
        self.assertAlmostEqual(sum(s['population_n'] for s in a['strata']),28)
        self.assertEqual({s['confidence_band'] for s in a['strata']},
                         {'missing','low','medium','high'})
    def test_audit_strata_require_enough_budget(self):
        with self.assertRaisesRegex(ValueError,'minimum'):
            self.plan(budget=3)
    def test_audit_draw_refuses_mutated_population(self):
        a=self.plan();data=self.dataset();data['records'][0]['name']='Name changed after draw'
        self.save(data=data)
        with self.assertRaisesRegex(ValueError,'Tampered'):
            estimate_existence_error(self.directory,plan=a,seed=SEED,labels=self.labels(a),evaluation_asof=EVAL)
    def test_audit_seed_replay_required(self):
        a=self.plan()
        with self.assertRaisesRegex(ValueError,'seed'):
            estimate_existence_error(self.directory,plan=a,seed='other'+SEED,labels=self.labels(a),evaluation_asof=EVAL)
    def test_audit_tampered_inclusion_probability(self):
        a=self.plan();a['selected'][0]['inclusion_probability']=.12345
        with self.assertRaisesRegex(ValueError,'Tampered'):
            estimate_existence_error(self.directory,plan=a,seed=SEED,labels=self.labels(a),evaluation_asof=EVAL)
    def test_incomplete_label_denies_population_estimate(self):
        a=self.plan();labels=self.labels(a)[:-1]
        r=estimate_existence_error(self.directory,plan=a,seed=SEED,labels=labels,evaluation_asof=EVAL)
        self.assertIsNone(r['error_fraction_estimate'])
        self.assertEqual(r['status'],'INCOMPLETE_OR_CONFLICTING_REVIEWS')
    def test_disagreement_denies_population_estimate(self):
        a=self.plan();labels=self.labels(a);labels[0]['votes'][1]['outcome']='does_not_exist'
        r=estimate_existence_error(self.directory,plan=a,seed=SEED,labels=labels,evaluation_asof=EVAL)
        self.assertIsNone(r['error_fraction_estimate'])
    def test_one_human_vote_denied(self):
        a=self.plan();labels=self.labels(a);labels[0]['votes'].pop()
        with self.assertRaisesRegex(ValueError,'Two human'):
            estimate_existence_error(self.directory,plan=a,seed=SEED,labels=labels,evaluation_asof=EVAL)
    def test_same_reviewer_denied(self):
        a=self.plan();labels=self.labels(a);labels[0]['votes'][1]['reviewer_id']='A'
        with self.assertRaisesRegex(ValueError,'reviewer IDs'):
            estimate_existence_error(self.directory,plan=a,seed=SEED,labels=labels,evaluation_asof=EVAL)
    def test_pre_audit_vote_denied(self):
        a=self.plan();labels=self.labels(a);labels[0]['votes'][0]['checked_at']='2026-10-10T09:00:00+03:00'
        with self.assertRaisesRegex(ValueError,'predates'):
            estimate_existence_error(self.directory,plan=a,seed=SEED,labels=labels,evaluation_asof=EVAL)
    def test_late_review_denies_population_estimate(self):
        a=self.plan();labels=self.labels(a);labels[0]['votes'][0]['checked_at']='2026-10-15T09:00:00+03:00'
        r=estimate_existence_error(self.directory,plan=a,seed=SEED,labels=labels,evaluation_asof=EVAL)
        self.assertIsNone(r['error_fraction_estimate'])
    def test_targeted_extra_label_denied(self):
        a=self.plan();labels=self.labels(a)
        labels.append({'overture_id':'ffffffff-ffff-ffff-ffff-ffffffffffff','votes':[vote('a'),vote('b')]})
        with self.assertRaisesRegex(ValueError,'Non-random'):
            estimate_existence_error(self.directory,plan=a,seed=SEED,labels=labels,evaluation_asof=EVAL)
    def test_all_reviews_complete_yields_weighted_report(self):
        a=self.plan()
        outcomes={s['overture_id']:('does_not_exist' if i%4==0 else 'exists') for i,s in enumerate(a['selected'])}
        r=estimate_existence_error(self.directory,plan=a,seed=SEED,
                                   labels=self.labels(a,outcomes),evaluation_asof=EVAL)
        self.assertEqual(r['status'],'COMPLETE_DESIGN_BASED_DIAGNOSTIC')
        self.assertGreaterEqual(r['error_fraction_estimate'],0)
        self.assertLessEqual(r['error_fraction_estimate'],1)
        self.assertFalse(r['independent_reviewers_verified_in_person'])
        self.assertFalse(r['real_world_verification_guaranteed'])
        self.assertEqual(len(r['strata']),8)
    def test_full_population_sample_exact(self):
        a=self.plan(budget=28)
        r=estimate_existence_error(self.directory,plan=a,seed=SEED,
                                   labels=self.labels(a),evaluation_asof=EVAL)
        self.assertEqual(r['confidence_band']['lower'],0)
        self.assertEqual(r['confidence_band']['upper'],0)
    def test_cli_without_network(self):
        p=subprocess.run([sys.executable,str(ROOT/'scripts/verify_overture_pilot.py'),
                          '--directory',str(self.directory)],cwd=ROOT,capture_output=True,text=True,timeout=10)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertFalse(json.loads(p.stdout)['upstream_acquisition_authenticated'])
    def test_cli_audit_plan_never_overwritten(self):
        seed_file=self.base/'private.audit-seed';seed_file.write_text(SEED)
        output=self.base/'frozen_plan.json'
        cmd=[sys.executable,str(ROOT/'scripts/verify_overture_pilot.py'),
             '--directory',str(self.directory),'--audit-seed-file',str(seed_file),
             '--audit-budget','12','--audit-plan-output',str(output)]
        one=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,timeout=10)
        self.assertEqual(one.returncode,0,one.stderr)
        self.assertTrue(output.is_file())
        self.assertNotIn(SEED,output.read_text())
        two=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,timeout=10)
        self.assertNotEqual(two.returncode,0)


if __name__=='__main__':unittest.main()
