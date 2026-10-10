"""KEP-SCI-003: randomized selection, nonresponse and population risk tests.

All reviewers and sources in this file are simulated. Passing tests do not
constitute an accuracy audit of any real Istanbul data source.
"""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
import json
import tempfile
import unittest

from kepcore.audit_sampling import (
    POLICY, design_random_audit, estimate_population_error,
)
from kepcore.review_intake import ReviewCandidate
from kepcore.calibration import ReviewedClaim
from kepcore.radar import Source

OBS='2026-10-01T08:00:00+03:00'
DEC='2026-10-02T08:00:00+03:00'
DRAW='2026-10-03T08:00:00+03:00'
CHECK='2026-10-04T08:00:00+03:00'
EVALUATE='2026-10-05T08:00:00+03:00'
SEED='private-seed-for-audit-tests-v1'
BYTES=b'IMMUTABLE_RESEARCH_FIXTURE_ONLY'
SHA=sha256(BYTES).hexdigest()


def source(status='approved'):
    return Source.parse({'id':'demo','url':'https://source.example.org/events',
        'city':'İzmir','format':'izmir_event_json' if status=='approved' else 'website_review_required',
        'status':status,'approved_uses':['research_ingest'] if status=='approved' else [],
        'license':'CC0-test-fixture','rights_evidence_url':'https://example.org/license',
        'rights_reviewed_at':'2026-10-01','review_note':'Synthetic only'})


def candidate(i=0,root='official',field='venue'):
    return ReviewCandidate(claim_id=f'c-{i}',entity_id=f'event-{i}',field=field,
        claimed_value='Test only',publisher_root=root,source_id='demo',
        source_url='https://source.example.org/events/123',city='İzmir',
        claimed_at=OBS,observed_at=OBS,predicted_at=DEC,
        snapshot_sha256=SHA,rights_scope='research_ingest')


def review(c:ReviewCandidate,correct=True,when=CHECK,origin='synthetic'):
    return ReviewedClaim(claim_id=c.claim_id,entity_id=c.entity_id,field=c.field,
        publisher_root=c.publisher_root,source_id=c.source_id,city=c.city,
        claimed_at=c.claimed_at,observed_at=c.observed_at,predicted_at=c.predicted_at,
        checked_at=when,snapshot_sha256=c.snapshot_sha256,
        rights_scope='research_ingest',outcome='correct' if correct else 'incorrect',
        reviewer_id='simulator' if origin=='synthetic' else 'auditor_a',
        evidence_ref='synthetic:review' if origin=='synthetic' else 'https://source.example.org/proof',
        origin=origin)


class AuditCase(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir=Path(self.temp.name)
        (self.dir/f'{SHA}.snapshot').write_bytes(BYTES)
        self.registry={'demo':source()}
        self.population=[candidate(i,'official' if i<12 else 'community',
                                   'venue' if i%2==0 else 'starts_at') for i in range(24)]

    def plan(self, rows=None, **kw):
        opts=dict(candidates=self.population if rows is None else rows,
                  sources=self.registry,snapshot_dir=self.dir,asof=DRAW,
                  budget=12,seed=SEED,synthetic=True)
        opts.update(kw)
        return design_random_audit(**opts)

    def outcome(self,plan=None,rows=None,**kw):
        p=plan or self.plan()
        xs=self.population if rows is None else rows
        selected={r['claim_id'] for r in p['selected']}
        samples=[review(c,correct=int(c.claim_id[2:])%3>0) for c in xs if c.claim_id in selected]
        opts=dict(plan=p,candidates=xs,reviews=samples,sources=self.registry,
                  snapshot_dir=self.dir,evaluation_asof=EVALUATE,replay_seed=SEED)
        opts.update(kw)
        return estimate_population_error(**opts)

    def test_deterministic_order_independent(self):
        self.assertEqual(self.plan(),self.plan(list(reversed(self.population))))

    def test_new_seed_changes_selection_not_population(self):
        a,b=self.plan(),self.plan(seed='another-long-hidden-test-seed')
        self.assertEqual(a['population_sha256'],b['population_sha256'])
        self.assertNotEqual(a['selected'],b['selected'])
        self.assertNotIn(SEED,json.dumps(a))

    def test_positive_probability_in_every_stratum(self):
        p=self.plan()
        self.assertEqual(p['budget'],12)
        self.assertEqual(len(p['strata']),4)
        self.assertTrue(all(x['selected_n']>=2 for x in p['strata']))
        self.assertTrue(all(0<x['inclusion_probability']<=1 for x in p['selected']))

    def test_budget_not_covering_minimum_fails(self):
        with self.assertRaisesRegex(ValueError,'minimum'):self.plan(budget=7)

    def test_budget_exceeding_population_fails(self):
        with self.assertRaisesRegex(ValueError,'exceeds'):self.plan(budget=25)

    def test_budget_boolean_fails(self):
        with self.assertRaises(ValueError):self.plan(budget=True)

    def test_empty_population_fails(self):
        with self.assertRaises(ValueError):self.plan([])

    def test_invalid_seed_fails(self):
        with self.assertRaises(ValueError):self.plan(seed='123')

    def test_duplicates_do_not_inflate_population(self):
        with self.assertRaises(ValueError):self.plan(self.population+[self.population[0]])

    def test_reposts_same_root_and_time_fail(self):
        duplicate=replace(self.population[0],claim_id='c-extra')
        with self.assertRaisesRegex(ValueError,'repost'):
            self.plan(self.population+[duplicate])

    def test_permission_denied(self):
        self.registry={'demo':source(status='pending')}
        with self.assertRaises(PermissionError):self.plan()

    def test_missing_source_denied(self):
        self.registry={}
        with self.assertRaises(PermissionError):self.plan()

    def test_city_mismatch_denied(self):
        with self.assertRaises(ValueError):self.plan([replace(self.population[0],city='İstanbul')],budget=1,min_per_stratum=1)

    def test_snapshot_mismatch_denied(self):
        (self.dir/f'{SHA}.snapshot').write_bytes(b'altered')
        with self.assertRaisesRegex(ValueError,'mismatch'):self.plan()

    def test_snapshot_missing_denied(self):
        (self.dir/f'{SHA}.snapshot').unlink()
        with self.assertRaises(ValueError):self.plan()

    def test_future_candidates_denied(self):
        late=replace(self.population[0],predicted_at='2026-10-09T10:00:00+03:00')
        with self.assertRaisesRegex(ValueError,'future'):
            self.plan([late],budget=1,min_per_stratum=1)

    def test_sampled_full_review_estimates(self):
        r=self.outcome()
        self.assertEqual(r['status'],'COMPLETE_STRATIFIED_AUDIT')
        self.assertEqual(r['sample_n'],12)
        self.assertEqual(r['resolved_n'],12)
        self.assertIsNotNone(r['error_rate_estimate'])
        self.assertLessEqual(r['confidence_band']['lower'],r['error_rate_estimate'])
        self.assertGreaterEqual(r['confidence_band']['upper'],r['error_rate_estimate'])
        self.assertFalse(r['allow_auto_publish'])

    def test_all_census_exact_uncertainty(self):
        p=self.plan(budget=24)
        r=self.outcome(plan=p)
        self.assertEqual(r['confidence_band']['lower'],r['confidence_band']['upper'])
        self.assertAlmostEqual(r['error_rate_estimate'],8/24,places=6)

    def test_missing_review_abstains(self):
        p=self.plan()
        selected={x['claim_id'] for x in p['selected']}
        rows=[review(c) for c in self.population if c.claim_id in selected][:-1]
        r=self.outcome(plan=p,reviews=rows)
        self.assertEqual(r['status'],'INCOMPLETE_NONRESPONSE')
        self.assertIsNone(r['error_rate_estimate'])
        self.assertEqual(r['unresolved_n'],1)

    def test_unknown_review_abstains(self):
        p=self.plan()
        selected={x['claim_id'] for x in p['selected']}
        rows=[review(c) for c in self.population if c.claim_id in selected]
        rows[0]=replace(rows[0],outcome='unknown')
        self.assertIsNone(self.outcome(plan=p,reviews=rows)['error_rate_estimate'])

    def test_late_review_abstains(self):
        p=self.plan()
        selected={x['claim_id'] for x in p['selected']}
        rows=[review(c) for c in self.population if c.claim_id in selected]
        rows[0]=replace(rows[0],checked_at='2026-11-01T00:00:00Z')
        self.assertIsNone(self.outcome(plan=p,reviews=rows)['error_rate_estimate'])

    def test_non_random_targeted_review_rejected(self):
        p=self.plan()
        excluded=next(c for c in self.population if c.claim_id not in {x['claim_id'] for x in p['selected']})
        with self.assertRaisesRegex(ValueError,'Targeted'):
            self.outcome(plan=p,reviews=[review(excluded)])

    def test_claim_field_tamper_fails(self):
        p=self.plan()
        p['selected'][0]['field']='price'
        with self.assertRaisesRegex(ValueError,'altered'):
            self.outcome(plan=p)

    def test_inclusion_probability_tamper_fails(self):
        p=self.plan()
        p['selected'][0]['inclusion_probability']=.99
        with self.assertRaisesRegex(ValueError,'altered'):
            self.outcome(plan=p)

    def test_population_tamper_fails(self):
        p=self.plan()
        changed=list(self.population)
        changed[0]=replace(changed[0],source_url='https://source.example.org/events/other')
        # Same identity, changed URL shouldn't pass a population snapshot signature.
        with self.assertRaisesRegex(ValueError,'changed'):
            self.outcome(plan=p,rows=changed)

    def test_same_stratum_cherrypicked_id_rejected_by_replay(self):
        p=self.plan()
        selected={e['claim_id'] for e in p['selected']}
        row=p['selected'][0]
        replacement=next(c for c in self.population if c.claim_id not in selected
                         and c.publisher_root==row['publisher_root'] and c.field==row['field'])
        for key in ('claim_id','entity_id','field','publisher_root','source_id','snapshot_sha256'):
            row[key]=getattr(replacement,key)
        with self.assertRaisesRegex(ValueError,'altered'):
            self.outcome(plan=p)

    def test_replay_seed_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError,'seed'):
            self.outcome(replay_seed='wrong-seed-must-never-match')

    def test_mixed_review_origin_fails(self):
        p=self.plan()
        samples=[review(c,origin='human_review') for c in self.population if c.claim_id in {x['claim_id'] for x in p['selected']}]
        with self.assertRaisesRegex(ValueError,'origin'):
            self.outcome(plan=p,reviews=samples)

    def test_review_city_spoofing_fails(self):
        p=self.plan()
        ids={x['claim_id'] for x in p['selected']}
        samples=[review(c) for c in self.population if c.claim_id in ids]
        samples[0]=replace(samples[0],city='İstanbul')
        with self.assertRaisesRegex(ValueError,'bound'):
            self.outcome(plan=p,reviews=samples)

    def test_review_prediction_time_spoofing_fails(self):
        p=self.plan()
        ids={x['claim_id'] for x in p['selected']}
        samples=[review(c) for c in self.population if c.claim_id in ids]
        samples[0]=replace(samples[0],predicted_at='2026-10-02T09:00:00+03:00')
        with self.assertRaisesRegex(ValueError,'bound'):
            self.outcome(plan=p,reviews=samples)

    def test_review_snapshot_mismatch_fails(self):
        p=self.plan()
        samples=[review(c) for c in self.population if c.claim_id in {x['claim_id'] for x in p['selected']}]
        samples[0]=replace(samples[0],snapshot_sha256='0'*64)
        with self.assertRaisesRegex(ValueError,'snapshot'):
            self.outcome(plan=p,reviews=samples)

    def test_duplicate_labels_fail(self):
        p=self.plan()
        selected={x['claim_id'] for x in p['selected']}
        samples=[review(c) for c in self.population if c.claim_id in selected]
        with self.assertRaisesRegex(ValueError,'Multiple'):self.outcome(plan=p,reviews=samples+[samples[0]])

    def test_evaluation_before_plan_fails(self):
        with self.assertRaisesRegex(ValueError,'before'):
            self.outcome(evaluation_asof=OBS)

    def test_invalid_alpha_fails(self):
        with self.assertRaisesRegex(ValueError,'Alpha'):
            self.outcome(alpha=0.)

    def test_plan_research_only_flag(self):
        self.assertTrue(self.plan()['research_only'])
        self.assertFalse(self.plan()['allow_auto_publish'])
        self.assertFalse(self.plan()['targeted_reviews_in_estimator'])

if __name__=='__main__':unittest.main()

class AuditCommandTests(unittest.TestCase):
    def test_help_does_not_need_network_or_secret(self):
        import subprocess, sys
        root=Path(__file__).resolve().parents[1]
        r=subprocess.run([sys.executable,str(root/'scripts/audit_source_reliability.py'),'--help'],
                        cwd=root,capture_output=True,text=True,timeout=10)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn('KEP_AUDIT_SEED',r.stdout)

    def test_never_export_to_arbitrary_location(self):
        from scripts.audit_source_reliability import _save_report
        with tempfile.TemporaryDirectory() as d:
            target=Path(d)/'audit.json'
            with self.assertRaises(PermissionError):
                _save_report({'test':True},str(target))
            self.assertFalse(target.exists())
