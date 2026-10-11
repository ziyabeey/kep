"""CORE-002 paired simulation; all human/source-world outcomes are invented."""
import copy
from dataclasses import asdict,replace
import json
import unittest
from unittest.mock import patch

from benchmarks.budgeted_core_eval import (
    View,Trial,REGIMES,POLICIES,generate,action_for,execute,run
)


def small_cfg():
    return {'study':'KEP-CORE-002','fixed_before_simulation':True,
        'seed':975,'cases_per_regime':25,'regimes':list(REGIMES),
        'policies':list(POLICIES),'false_assertion_penalty':4,
        'paired_draws':100,'max_checks_per_case':1}


class BudgetedSimulatorContracts(unittest.TestCase):
    def test_wholly_synthetic_deterministic_fixed_regimes(self):
        self.assertEqual(len(REGIMES),6)
        self.assertEqual(len(POLICIES),5)
        for regime in REGIMES:
            self.assertEqual(generate(regime,31,8),generate(regime,31,8))
        self.assertNotEqual(generate('matched',31,8),generate('matched',32,8))

    def test_hidden_answers_and_truth_absent_from_planner_view(self):
        for trial in generate('matched',12,12):
            public=asdict(trial.view)
            self.assertNotIn('truth',public)
            self.assertNotIn('hidden_answers',public)
            first=action_for(trial.view,'voi')
            alternate=replace(trial,truth=not trial.truth,
                              hidden_answers=(('deep',not trial.truth),))
            self.assertEqual(action_for(alternate.view,'voi'),first)
            with self.assertRaises(TypeError):action_for(trial,'voi')

    def test_each_policy_gets_same_frozen_view_and_no_real_api(self):
        trial=generate('matched',131,1)[0]
        with patch('urllib.request.OpenerDirector.open',
                   side_effect=AssertionError('network')) as opener:
            for mode in POLICIES:
                r=execute(trial,mode)
                self.assertFalse(r['accepted_with_model'])
                self.assertIn(r['final_lab_verdict'],
                              {'LAB_CORROBORATED','LAB_ABSTAIN','CORE_REFUSED'})
        opener.assert_not_called()

    def test_frozen_rights_policy_blocks_check_and_assertion(self):
        cases=generate('rights_and_disputes',44,40)
        for item in cases:
            if item.view.record['rights_scope']!='open_attribution':
                for mode in POLICIES:
                    r=execute(item,mode)
                    self.assertFalse(r['checked'])
                    self.assertFalse(r['accepted'])
                    self.assertEqual(r['proposal'],'CORE_REFUSED')

    def test_cost_charged_only_when_check_performed(self):
        trials=generate('matched',32,50)
        for t in trials:
            for policy in POLICIES:
                o=execute(t,policy)
                self.assertEqual(o['checked'],o['check_cost_utility_units']>0)
                if policy=='never':
                    self.assertFalse(o['checked'])
                    self.assertEqual(o['check_cost_utility_units'],0)

    def test_tight_budget_or_deadline_forbids_deep_probe(self):
        for regime in ('tight_budget','short_deadline'):
            for t in generate(regime,78,30):
                p=action_for(t.view,'voi')
                self.assertNotEqual(p.probe_id,'deep')
                self.assertLessEqual(p.proposed_cost,t.view.budget)
                if p.estimated_latency_minutes is not None:
                    self.assertLessEqual(p.estimated_latency_minutes,t.view.max_wait_minutes)

    def test_echoes_cannot_authorize_second_root(self):
        cases=generate('echo_storm',56,50)
        for t in cases:
            proposal=action_for(t.view,'voi')
            self.assertNotEqual(proposal.probe_id,'mirror')
            self.assertNotEqual(proposal.probe_root,'origin')

    def test_realistic_negative_regime_is_present_and_not_hidden(self):
        data=run(small_cfg())
        self.assertEqual(data['scenario_origin'],'fully_synthetic_paired_hidden_truth')
        self.assertIsNone(data['real_world_business_accuracy'])
        self.assertFalse(data['consumer_publish'])
        self.assertEqual(data['source_downloads'],0)
        self.assertEqual(data['model_calls'],0)
        self.assertEqual(data['real_field_labels_used'],0)
        self.assertTrue(data['policy_inputs_cannot_access_truth_or_future_answers'])
        for name in REGIMES:
            outcome=data['regimes'][name]
            for mode in POLICIES:
                r=outcome['methods'][mode]
                self.assertEqual(r['cases'],25)
                self.assertEqual(r['assertions'],r['correct_assertions']+r['false_assertions'])
                self.assertLessEqual(r['checks'],25)
                self.assertGreaterEqual(r['total_check_cost_utility_units'],0)
            self.assertEqual(outcome['methods']['never']['checks'],0)

    def test_preregistered_protocol_contract_locked(self):
        cfg=small_cfg()
        for k,bad in [('fixed_before_simulation',False),
                      ('regimes',list(REGIMES)[:-1]),
                      ('policies',['voi']),('max_checks_per_case',2),
                      ('paired_draws',0),('false_assertion_penalty',0),
                      ('seed',True),('cases_per_regime',-1)]:
            with self.subTest(k=k),self.assertRaises(ValueError):
                run({**cfg,k:bad})

    def test_small_replay_exact_and_zero_private_data(self):
        a=run(small_cfg())
        b=run(small_cfg())
        self.assertEqual(a,b)
        raw=json.dumps(a)
        self.assertNotIn('overture_id',raw)
        self.assertNotIn('reviewer_id',raw)
        self.assertNotIn('physical_business_closures": 0',raw)


    def test_fixed_decimal_half_ties_cross_version(self):
        from decimal import Decimal
        from benchmarks.budgeted_core_eval import _rounded6, _case_value
        self.assertEqual(_rounded6(Decimal('0.4612875')),0.461288)
        self.assertEqual(_rounded6(Decimal('-0.0360625')),-0.036062)
        c=generate('matched',21,1)[0]
        r={'accepted':True,'check_cost_utility_units':0.115}
        value=_case_value(c,r,4)
        self.assertEqual(value,
                         (Decimal('0.885') if c.truth else Decimal('-4.115')))


if __name__=='__main__':
    unittest.main()
