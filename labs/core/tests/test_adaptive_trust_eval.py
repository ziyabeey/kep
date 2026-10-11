"""CORE-003 audit-stream and temporal policy holdout regressions, all synthetic."""
import unittest
from dataclasses import asdict,replace
from datetime import timedelta
from unittest.mock import patch

from benchmarks.adaptive_trust_eval import (
    REGIMES,POLICIES,generate_chronological,choose,execute_preplanned,run,
)
from kepcore.calibration import aware
from kepcore.adaptive_trust import estimate_sources

def small():
    return {'study':'KEP-CORE-003','fixed_before_simulation':True,
            'seed':456,'cases_per_regime':12,'regimes':list(REGIMES),
            'policies':list(POLICIES),'false_assertion_penalty':4,
            'paired_draws':100,'audit_window_hours':72,
            'audit_label_delay_hours':3,'per_hour_background_audits':3}

class AdaptiveChronologyTests(unittest.TestCase):
    def test_six_scenarios_reproducible_without_real_source(self):
        for name in REGIMES:
            cases,audits=generate_chronological(name,123,8)
            cases2,audits2=generate_chronological(name,123,8)
            self.assertEqual((cases,audits),(cases2,audits2))
            self.assertEqual(len(cases),8)
            self.assertTrue(all(c.view.record['synthetic'] for c in cases))
            self.assertTrue(all(c.view.record['source_url'].startswith('synthetic://') for c in cases))
        self.assertEqual(len(REGIMES),6)

    def test_background_case_identity_never_reveals_trial_truth(self):
        cases,audits=generate_chronological('stable',55,9)
        for case in cases:
            self.assertNotIn('truth',asdict(case.view))
            self.assertNotIn('hidden_answers',asdict(case.view))
            self.assertNotIn(case.view.record['id'],{x.entity_id for x in audits})
        with self.assertRaises((ValueError,TypeError)):
            choose(cases[0],audits,'posterior_mean')

    def test_causal_selection_excludes_all_late_feedback(self):
        cases,audits=generate_chronological('late_adjudication',88,10)
        case=cases[0]
        asof=aware(case.view.query.at)
        eligible=[x for x in audits if aware(x.adjudicated_at)<=asof]
        all_result=choose(case.view,audits,'conservative')
        eligible_result=choose(case.view,eligible,'conservative')
        self.assertEqual(all_result,eligible_result)
        self.assertGreater(len(audits),len(eligible))

    def test_changing_hidden_test_answer_does_not_change_proposal(self):
        cases,audits=generate_chronological('abrupt_degradation',678,10)
        c=cases[0]
        eligible=[a for a in audits if aware(a.adjudicated_at)<=aware(c.view.query.at)]
        before=choose(c.view,eligible,'posterior_mean')
        after=replace(c,truth=not c.truth,hidden_answers=(('deep',not c.truth),))
        self.assertEqual(choose(after.view,eligible,'posterior_mean'),before)

    def test_paired_options_use_same_cost_deadline_and_rights(self):
        cases,audits=generate_chronological('stable',211,12)
        for c in cases:
            for p in POLICIES:
                plan=choose(c.view,(),p)
                if p in {'posterior_mean','conservative'}:
                    self.assertNotEqual(plan.action,'PROPOSE_CHECK')
                    continue
                if plan.action=='PROPOSE_CHECK':
                    self.assertLessEqual(plan.proposed_cost,c.view.budget)
                    self.assertLessEqual(plan.estimated_latency_minutes,
                                         c.view.max_wait_minutes)
                    self.assertNotEqual(plan.probe_root,'origin')
                self.assertFalse(plan.authorized_to_fetch)

    def test_outage_audits_reach_cutoff_but_do_not_leak_future(self):
        cases,audits=generate_chronological('audit_outage',32,80)
        at=aware(cases[-1].view.query.at)
        available=[a for a in audits if aware(a.adjudicated_at)<=at]
        self.assertTrue(available)
        self.assertTrue(any(aware(a.adjudicated_at)>at for a in audits))
        selected=estimate_sources(available,as_of=at.isoformat(),
                                  approved_roots=('origin','cheap_root','balanced_root','deep_root'))
        self.assertTrue(all(x.observations_used>=0 for x in selected.values()))

    def test_executor_still_requires_no_network_and_no_consumer_output(self):
        cases,audits=generate_chronological('stable',65,1)
        c=cases[0]
        h=tuple(a for a in audits if aware(a.adjudicated_at)<=aware(c.view.query.at))
        with patch('urllib.request.OpenerDirector.open',
                   side_effect=AssertionError('no external request')) as network:
            for p in POLICIES:
                out=execute_preplanned(c,choose(c.view,h,p))
                self.assertTrue(out['proposal_without_external_io'])
                self.assertFalse(out['accepted'] and out['false_assertion'])
        network.assert_not_called()

    def test_full_small_result_keeps_adverse_regimes_and_null_field_truth(self):
        result=run(small())
        self.assertEqual(result,run(small()))
        self.assertEqual(result['scenario_origin'],
                         'WHOLLY_SYNTHETIC_INDEPENDENT_BACKGROUND_AUDITS')
        self.assertFalse(result['consumer_publish'])
        self.assertIsNone(result['real_business_accuracy'])
        self.assertFalse(result['actual_field_source_calibration'])
        self.assertEqual(result['real_human_reviews_used'],0)
        self.assertEqual(result['source_downloads'],0)
        for name in REGIMES:
            methods=result['results'][name]['methods']
            self.assertEqual(set(methods),set(POLICIES))
            for p in POLICIES:
                self.assertEqual(methods[p]['cases'],12)
                self.assertEqual(methods[p]['assertions'],
                                 methods[p]['correct_assertions']+methods[p]['false_assertions'])
                self.assertLessEqual(methods[p]['checks'],12)
            self.assertEqual(methods['never']['checks'],0)
        self.assertIn('correlated_failure',result['results'])
        self.assertIn('abrupt_degradation',result['results'])

    def test_config_not_tuned_after_results(self):
        c=small()
        for k,v in [('fixed_before_simulation',False),('regimes',['stable']),
                    ('policies',['conservative']),('cases_per_regime',0),
                    ('audit_window_hours',24),('paired_draws',0),
                    ('seed',True),('false_assertion_penalty',0)]:
            with self.subTest(k=k),self.assertRaises(ValueError):run({**c,k:v})

if __name__=='__main__':
    unittest.main()
