"""CORE-004A: focused tests of a new decision-risk experiment, not test counts."""
from __future__ import annotations
from dataclasses import replace,asdict
import unittest
from unittest.mock import patch

from benchmarks.outage_value_eval import (
    REGIMES,POLICIES,generate,choose,gate,run,config
)
from kepcore.calibration import aware


class OutageHoldoutContracts(unittest.TestCase):
    def test_new_scenario_same_seed_repeatable_without_customer_data(self):
        for regime in REGIMES:
            a=generate(regime,101,4)
            b=generate(regime,101,4)
            self.assertEqual(a,b)
            self.assertEqual(len(a[0]),4)
            self.assertTrue(all(x.view.record['synthetic'] for x in a[0]))
            self.assertTrue(all(x.view.record['source_url'].startswith('synthetic://')
                                for x in a[0]))

    def test_current_truth_never_enters_planner_or_changes_its_selection(self):
        trials,audits=generate('outage_stable',78,3)
        case=trials[2]
        self.assertNotIn('truth',asdict(case.view))
        self.assertNotIn('hidden_answers',asdict(case.view))
        before=choose(case.view,audits,'bounded_grace')
        flipped=replace(case,truth=not case.truth,hidden_answers=(('deep',False),))
        self.assertEqual(before,choose(flipped.view,audits,'bounded_grace'))
        with self.assertRaises(TypeError):
            choose(case,audits,'bounded_grace')

    def test_audit_outage_and_drift_share_identical_past_audit_stream(self):
        base,original=generate('outage_stable',123,75)
        changed,audits=generate('outage_abrupt_drift',123,75)
        self.assertEqual(original,audits)
        self.assertTrue(all(
            a.entity_id!=v.view.record['id']
            for a in original[:30] for v in base[:3]))
        self.assertEqual(len(base),len(changed))

    def test_acceptance_does_not_favor_policy_merely_because_some_checks_pass(self):
        c=config()
        def measures(utility,wrong):
            return {'utility_per_case':utility,
                    'false_assertions':wrong}
        d={}
        for regime in REGIMES:
            d[regime]={'methods':{
                'never':measures(0,0),
                'fixed_voi':measures(.4,0),
                'conservative':measures(.2,0),
                'bounded_grace':measures(.2,0)
            }}
        self.assertEqual(gate(d,c)['decision'],'NO_GO')
        d['outage_stable']['methods']['bounded_grace']=measures(.25,2)
        self.assertEqual(gate(d,c)['decision'],'NO_GO')
        self.assertIn('outage_false_assertions_not_above_fixed',gate(d,c)['failed'])

    def test_small_run_reports_safety_and_all_adverse_regimes(self):
        with patch('urllib.request.OpenerDirector.open',
                   side_effect=AssertionError('No external data requests')):
            result=run({'cases_per_regime':5,'paired_bootstrap_draws':100})
        self.assertEqual(result['scenario_origin'],
                         'PREREGISTERED_WHOLLY_SYNTHETIC_NEW_HOLDOUT')
        self.assertIsNone(result['actual_business_accuracy'])
        self.assertFalse(result['consumer_publish'])
        self.assertEqual(result['external_data_downloads'],0)
        self.assertEqual(result['real_human_labels_used'],0)
        self.assertFalse(result['policy_received_hidden_truth_or_future_answers'])
        self.assertEqual(set(result['regimes']),set(REGIMES))
        for row in result['regimes'].values():
            self.assertEqual(set(row['methods']),set(POLICIES))
            for method in row['methods'].values():
                self.assertEqual(method['cases'],5)

    def test_no_posthoc_protocol_edit_or_fake_success(self):
        p=config()
        self.assertEqual(p['experiment']['seed'],2026101204)
        self.assertEqual(p['go_no_go_frozen']['main_regime'],'outage_stable')
        for bad in ({'cases_per_regime':-1,'paired_bootstrap_draws':100},
                    {'cases_per_regime':5,'paired_bootstrap_draws':4},
                    {'cases_per_regime':5,'unregistered_feature':1}):
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                run(bad)


if __name__=='__main__':
    unittest.main()
