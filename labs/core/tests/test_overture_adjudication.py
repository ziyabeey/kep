"""KEP-DATA-005: every human answer in these tests is invented for CI.

Real Overture source rows are ONLY the immutable sampling frame, never real
field-verification labels. No actual person was reviewed.
"""
from __future__ import annotations
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import subprocess
import sys
import unittest

from tests.test_overture_field_review import (
    make_book,SEED,AT,REVIEW_AT,EVAL,BEFORE,
)
from kepcore.overture_real import DATA_DIR,load_archive,prepare_private_audit
from kepcore.overture_adjudication import (
    DIMENSION,blind_case_templates,read_adjudications,reconcile,
    new_holdout_forecast,_estimate_from_resolved,
)


class FrozenThirdReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.freeze=prepare_private_audit(DATA_DIR,budget=60,seed=SEED,sampled_at=AT)
        cls.plan=cls.freeze['plan']
        doc,_,cls.meta=load_archive(DATA_DIR,verify=False)
        cls.lookup={r['overture_id']:r for r in doc['records']}
        cls.ids=[p['overture_id'] for p in cls.plan['selected']]
        cls.conflict_id=cls.ids[0]

    def setUp(self):
        self.directory=TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path=Path(self.directory.name)
        self.plan_file=self.path/'pilot.json'
        self.plan_file.write_text(json.dumps(self.plan),encoding='utf-8')
        self.seed_file=self.path/'secret-seed.txt'
        self.seed_file.write_text(SEED,encoding='utf-8')
        self.good_a={rid:'exists' for rid in self.ids}
        self.good_b=self.good_a.copy()
        self.good_b[self.conflict_id]='does_not_exist'

    def workbooks(self,*,a=None,b=None):
        ap=self.path/'a.xlsx';bp=self.path/'b.xlsx'
        make_book(ap,'A',self.plan,self.lookup,votes=a if a is not None else self.good_a)
        make_book(bp,'B',self.plan,self.lookup,votes=b if b is not None else self.good_b)
        return ap,bp

    def context(self,*,a=None,b=None,asof=EVAL):
        pa,pb=self.workbooks(a=a,b=b)
        return dict(reviewer_a=pa,reviewer_b=pb,audit_plan=self.plan_file,
                    seed_file=self.seed_file,evaluation_asof=asof)

    def cases(self,context=None):
        return blind_case_templates(**(context or self.context()))

    def third_file(self,*,outcome='exists',cases=None,overrides=None):
        if cases is None:cases=self.cases()
        records=[]
        for case in cases:
            record=dict(case)
            record.update({'outcome':outcome,'reviewer_id':'human-independent-c',
                           'checked_at':'2026-10-11T13:00:00+03:00',
                           'evidence_url':'https://example.org/source/case-with-historical-visit',
                           'reason':'Synthetic test record: independent physical verification.'})
            if overrides:record.update(overrides)
            records.append(record)
        path=self.path/'third.jsonl'
        path.write_text('\n'.join(json.dumps(x) for x in records)+'\n')
        return path

    def test_blind_no_ab_votes_or_pseudonyms(self):
        cases=self.cases()
        self.assertEqual(len(cases),1)
        value=json.dumps(cases)
        self.assertNotIn('does_not_exist',value)
        self.assertNotIn('synthetic-human-a-fixture',value)
        self.assertEqual(cases[0]['dimension'],DIMENSION)
        self.assertIn('case_sha256',cases[0])
        self.assertEqual(cases[0]['outcome'],'not_reviewed')

    def test_missing_third_stops_rate(self):
        r=reconcile(**self.context())
        self.assertEqual(r['third_cases_required'],1)
        self.assertEqual(r['status'],'INCOMPLETE_OR_ADJUDICATION_PENDING')
        self.assertIsNone(r['error_fraction_estimate'])

    def test_explicit_third_exists_releases_research_estimate(self):
        c=self.context();three=self.third_file()
        r=reconcile(**c,adjudications=three)
        self.assertEqual(r['status'],'COMPLETE_ADJUDICATED_RESEARCH_DIAGNOSTIC')
        self.assertEqual(r['third_cases_resolved'],1)
        self.assertEqual(r['error_fraction_estimate'],0)
        self.assertFalse(r['consumer_publish'])
        self.assertFalse(r['current_operation_verified'])
        self.assertFalse(r['open_now_verified'])
        self.assertFalse(r['coordinate_accuracy_verified'])

    def test_explicit_third_nonexistent_is_measured_not_majority_voted(self):
        c=self.context();three=self.third_file(outcome='does_not_exist')
        r=reconcile(**c,adjudications=three)
        self.assertGreater(r['error_fraction_estimate'],0)
        self.assertLess(r['error_fraction_estimate'],.2)
        self.assertEqual(r['third_cases_resolved'],1)

    def test_unknown_third_stops_rate(self):
        self.assertIsNone(reconcile(**self.context(),adjudications=self.third_file(outcome='unknown'))['error_fraction_estimate'])

    def test_original_unknown_not_overridden(self):
        a=self.good_a.copy(); a[self.conflict_id]='unknown'
        c=self.context(a=a)
        self.assertEqual(self.cases(c),[])
        self.assertIsNone(reconcile(**c)['error_fraction_estimate'])

    def test_original_missing_not_overridden(self):
        a=self.good_a.copy(); a.pop(self.conflict_id)
        c=self.context(a=a)
        self.assertEqual(self.cases(c),[])
        self.assertIsNone(reconcile(**c)['error_fraction_estimate'])

    def test_extra_third_for_concordant_source_rejected(self):
        third=self.third_file()
        c=self.context(a=self.good_a,b=self.good_a)
        with self.assertRaisesRegex(ValueError,'non-conflicted'):
            reconcile(**c,adjudications=third)

    def test_adjudicator_cannot_be_reviewer_a(self):
        third=self.third_file(overrides={'reviewer_id':'synthetic-human-a-fixture'})
        with self.assertRaisesRegex(ValueError,'must differ'):
            reconcile(**self.context(),adjudications=third)

    def test_adjudicator_cannot_be_reviewer_b(self):
        third=self.third_file(overrides={'reviewer_id':'synthetic-human-b-fixture'})
        with self.assertRaisesRegex(ValueError,'must differ'):
            reconcile(**self.context(),adjudications=third)

    def test_third_preceding_originals_rejected(self):
        third=self.third_file(overrides={'checked_at':'2026-10-11T11:00:00+03:00'})
        with self.assertRaisesRegex(ValueError,'predate'):
            reconcile(**self.context(),adjudications=third)

    def test_late_third_excluded_from_asof(self):
        third=self.third_file(overrides={'checked_at':'2026-10-15T00:00:00+03:00'})
        result=reconcile(**self.context(),adjudications=third)
        self.assertEqual(result['third_cases_late'],1)
        self.assertIsNone(result['error_fraction_estimate'])

    def test_snapshot_binding_detects_changed_original_vote(self):
        old_cases=self.cases()
        third=self.third_file(cases=old_cases)
        c=self.context()
        # Rebuild the workbook with a *different reviewer* while preserving
        # the same conflicting labels. Third ballot is now for another case.
        pa=c['reviewer_a']
        with __import__('zipfile').ZipFile(pa) as z:
            parts={n:z.read(n) for n in z.namelist()}
        k='xl/worksheets/sheet1.xml'
        parts[k]=parts[k].replace(b'synthetic-human-a-fixture',b'synthetic-human-modified')
        with __import__('zipfile').ZipFile(pa,'w') as z:
            for n,v in parts.items():z.writestr(n,v)
        with self.assertRaisesRegex(ValueError,'unchanged A/B'):
            reconcile(**c,adjudications=third)

    def test_third_blinded_name_tampering_rejected(self):
        third=self.third_file(overrides={'name':'changed name'})
        with self.assertRaisesRegex(ValueError,'source fields'):
            reconcile(**self.context(),adjudications=third)

    def test_non_existence_dimension_rejected(self):
        third=self.third_file(overrides={'dimension':'open_now'})
        with self.assertRaisesRegex(ValueError,'measured field'):
            read_adjudications(third)

    def test_duplicate_third_entry_rejected(self):
        t=self.third_file();t.write_text(t.read_text()*2)
        with self.assertRaisesRegex(ValueError,'Repeated'):
            read_adjudications(t)

    def test_incorrect_evidence_url_rejected(self):
        t=self.third_file(overrides={'evidence_url':'https://www.google.com/maps/search/?api=1&query=41,29'})
        with self.assertRaisesRegex(ValueError,'Specific HTTPS'):
            read_adjudications(t)

    def test_partial_not_reviewed_rejected(self):
        t=self.third_file(overrides={'outcome':'not_reviewed'})
        with self.assertRaisesRegex(ValueError,'partial'):
            read_adjudications(t)

    def test_valid_unfilled_template_does_not_release_rate(self):
        p=self.path/'empty_cases.jsonl'
        p.write_text('\n'.join(json.dumps(x) for x in self.cases())+'\n')
        r=reconcile(**self.context(),adjudications=p)
        self.assertEqual(r['third_cases_resolved'],0)
        self.assertIsNone(r['error_fraction_estimate'])

    def test_no_conflict_older_estimator_parity(self):
        from kepcore.overture_field_review import evaluate_review_workbooks
        c=self.context(a=self.good_a,b=self.good_a)
        before=evaluate_review_workbooks(**c)
        after=reconcile(**c)
        self.assertEqual(before['error_fraction_estimate'],after['error_fraction_estimate'])
        self.assertEqual(before['confidence_band'],after['confidence_band'])

    def test_all_unknown_never_a_rate(self):
        a=dict.fromkeys(self.ids,'unknown')
        c=self.context(a=a,b=a)
        self.assertIsNone(reconcile(**c)['error_fraction_estimate'])

    def test_inclusion_probabilities_separate_from_truth(self):
        r=reconcile(**self.context(),adjudications=self.third_file())
        self.assertNotIn('verified_true',r)
        self.assertFalse(r['survey_label_truth_verified_independently'])


class HoldoutDesignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan=prepare_private_audit(DATA_DIR,budget=60,seed=SEED,sampled_at=AT)['plan']

    def test_new_frame_is_disjoint_and_no_sample_draw(self):
        r=new_holdout_forecast(self.plan)
        self.assertEqual(r['new_disjoint_frame_n'],4743)
        self.assertEqual(r['excluded_existing_pilot_n'],60)
        self.assertEqual(r['mode'],'DESIGN_ONLY_NO_NEW_SAMPLE_DRAWN')
        self.assertTrue(r['pilot_ids_cannot_be_reused'])
        self.assertFalse(r['consumer_publish'])

    def test_three_forecast_budgets(self):
        p=new_holdout_forecast(self.plan)
        self.assertEqual([x['new_holdout_sample_n'] for x in p['forecast']],[401,713,1604])
        self.assertLessEqual(p['forecast'][-1]['achieved_conservative_half_width'],.1)
        self.assertEqual(p['forecast'][-1]['two_reviewers_hours'],641.6)

    def test_weighted_allocation_sums(self):
        p=new_holdout_forecast(self.plan)
        for d in p['forecast']:
            self.assertEqual(sum(x['proposed_n'] for x in d['allocation']),d['new_holdout_sample_n'])
            self.assertTrue(all(x['proposed_n']<=x['eligible_n'] for x in d['allocation']))

    def test_invalid_frame_and_risk_rejected(self):
        p=dict(self.plan);p['population_n']=2
        with self.assertRaises(ValueError):new_holdout_forecast(p)
        with self.assertRaises(ValueError):new_holdout_forecast(self.plan,targets=(float('nan'),))
        with self.assertRaises(ValueError):new_holdout_forecast(self.plan,alpha=0)

    def test_no_future_accuracy_claim(self):
        p=new_holdout_forecast(self.plan)
        self.assertNotIn('error_fraction_estimate',p)
        self.assertFalse(p['consumer_publish'])

    def test_help_offline_and_no_keys(self):
        f=Path(__file__).resolve().parents[1]/'scripts/adjudicate_overture_field.py'
        completed=subprocess.run([sys.executable,str(f),'--help'],capture_output=True,text=True,timeout=10)
        self.assertEqual(completed.returncode,0,completed.stderr)
        self.assertIn('blinded-cases',completed.stdout)


if __name__=='__main__':unittest.main()
