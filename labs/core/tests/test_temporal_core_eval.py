"""Synthetic evaluator contracts. No source truth or field labels inferred."""
import copy
from dataclasses import asdict,replace
import json
import unittest

from benchmarks.temporal_core_eval import (
    REGIMES,POLICIES,CaseInput,generate,policy_actions,run,
)
from kepcore.core import decide


class TemporalSimulatorTests(unittest.TestCase):
    def test_deterministic_independent_regimes_and_seeds(self):
        for regime in REGIMES:
            self.assertEqual(generate(regime,17,15),generate(regime,17,15))
        a=generate('matched',17,15)
        b=generate('matched',18,15)
        self.assertNotEqual(a,b)
        self.assertEqual(len(set(REGIMES)),5)

    def test_hidden_truth_structurally_unavailable_to_policy(self):
        case=generate('matched',123,1)[0]
        self.assertNotIn('truth',asdict(case.view))
        expected=policy_actions(case.view)
        self.assertEqual(policy_actions(replace(case,truth=not case.truth).view),expected)
        with self.assertRaises(TypeError):
            policy_actions(case)

    def test_one_root_echo_attack_is_not_independent_support(self):
        examples=generate('mirror_attack',19,60)
        has_many=any(len(c.view.signals)>=10 for c in examples)
        self.assertTrue(has_many)
        for case in examples:
            ids={x.publisher_root for x in case.view.signals
                 if x.publisher_root in ('origin','partner')}
            result=policy_actions(case.view)
            if ids=={'origin'}:
                self.assertFalse(result['temporal_root'])

    def test_rights_bypass_blocked_in_all_policies(self):
        cases=generate('rights_blocked',130,30)
        for case in cases:
            out=policy_actions(case.view)
            if case.view.record['rights_scope']!='open_attribution':
                self.assertFalse(any(out.values()))

    def test_future_reports_are_invisible_at_current_clock(self):
        cases=generate('delivery_lag',19,10)
        first=cases[0].view
        delayed=[s for s in first.signals if s.event_id.startswith('sensor-b')]
        self.assertTrue(delayed)
        self.assertGreater(delayed[0].available_at,first.query.at)
        from kepcore.temporal_pipeline import evidence_snapshot
        visible=evidence_snapshot(first.signals,as_of=first.query.at,
                                  entity_ids=[first.record['id']],
                                  approved_roots=('origin','partner'))
        self.assertNotIn('partner',visible[first.record['id']]['independent_roots'])

    def test_one_run_is_paired_and_never_real_validation(self):
        cfg={'study':'KEP-CORE-001','fixed_before_simulation':True,
            'seed':987,'n_per_regime':30,'regimes':list(REGIMES),
            'policies':list(POLICIES),'false_assertion_penalty':4,
            'paired_bootstrap_draws':100}
        x=run(cfg)
        self.assertEqual(x,run(cfg))
        self.assertEqual(x['scenario_origin'],'wholly_synthetic_hidden_truth')
        self.assertIsNone(x['real_field_accuracy'])
        self.assertFalse(x['consumer_publish'])
        self.assertEqual(x['new_source_downloads'],0)
        self.assertEqual(x['model_api_calls'],0)
        for regime in REGIMES:
            result=x['results'][regime]
            for method in POLICIES:
                m=result['policies'][method]
                self.assertEqual(m['n'],30)
                self.assertLessEqual(m['asserted_n'],30)
                self.assertEqual(m['correct_asserted_n']+m['false_asserted_n'],
                                 m['asserted_n'])
            self.assertEqual(result['policies']['always_abstain']['asserted_n'],0)
            self.assertIsNone(result['policies']['always_abstain']['false_assertion_fraction_if_asserted'])

    def test_unregistered_simulation_configuration_denied(self):
        cfg={'study':'KEP-CORE-001','fixed_before_simulation':True,
            'seed':987,'n_per_regime':3,'regimes':list(REGIMES),
            'policies':list(POLICIES),'false_assertion_penalty':4,
            'paired_bootstrap_draws':100}
        for key,bad in [('fixed_before_simulation',False),('n_per_regime',0),
                        ('regimes',['matched']),('policies',['temporal_root']),
                        ('false_assertion_penalty',0),('paired_bootstrap_draws',0)]:
            with self.subTest(key=key),self.assertRaises(ValueError):
                run({**cfg,key:bad})

    def test_synthetic_catalog_records_are_not_real_venues(self):
        c=generate('matched',87,10)
        for record in c:
            source=record.view.record
            self.assertTrue(source['synthetic'])
            self.assertTrue(source['id'].startswith('syn:core001:'))
            self.assertTrue(source['source_url'].startswith('synthetic://'))
            self.assertFalse(hasattr(record.view,'truth'))
            self.assertEqual(record.view.query.kind,'place')


if __name__=='__main__':
    unittest.main()
