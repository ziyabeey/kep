"""Scientific contract tests; not field performance evidence."""
from __future__ import annotations
import math
import unittest
from kepcore.evidence_lab import (
    EvidenceChannel,Observation,bayes_update,fuse_roots,expected_value_of_sample,
    expected_information_gain,route_research,field_research_tasks,action_utility)
from kepcore.core import load_catalog, Query, decide, reconcile_claims, load_json,ROOT
from benchmarks.evidence_value import run,generate,one_case
from scripts.research_intelligence import demo


def source(id='first',root='root',r=.8,cost=.03,approved=True,primary=False):
    return EvidenceChannel(id,root,r,r,cost,approved,primary)


class EvidencePosteriorTest(unittest.TestCase):
    def test_yes_update(self):
        self.assertAlmostEqual(bayes_update(.5,source(),True),.8)
    def test_no_update(self):
        self.assertAlmostEqual(bayes_update(.5,source(),False),.2)
    def test_root_duplicate_no_multiplication(self):
        owner=source('owner','one',.8,0,primary=True)
        copy=source('copied','one',.999,0)
        first=Observation('owner','one',True)
        echoed=Observation('copied','one',True)
        baseline=fuse_roots(.5,[first],[owner,copy])
        for repeat in [1,10,100]:
            actual=fuse_roots(.5,[first]+[echoed]*repeat,[owner,copy])
            self.assertEqual(actual,baseline)
            self.assertEqual(actual.independent_roots,('one',))
    def test_root_different_sources_combine(self):
        a=source('a','r1');b=source('b','r2')
        fused=fuse_roots(.5,[Observation('a','r1',True),Observation('b','r2',True)],[a,b])
        self.assertAlmostEqual(fused.probability,16/17)
    def test_conflict_same_root_refuse(self):
        a=source('a','same');b=source('b','same')
        v=fuse_roots(.5,[Observation('a','same',True),Observation('b','same',False)],[a,b])
        self.assertEqual(v.status,'disputed');self.assertIsNone(v.probability)
        self.assertEqual(route_research(.5,[Observation('a','same',True),Observation('b','same',False)],[a,b]).action,'HUMAN_REVIEW')
    def test_root_order_invariant(self):
        a=source('a','z',.8);b=source('b','a',.9)
        claims=[Observation('a','z',True),Observation('b','a',False)]
        self.assertEqual(fuse_roots(.44,claims,[a,b]),fuse_roots(.44,list(reversed(claims)),[b,a]))
    def test_unknown_source_rejected(self):
        with self.assertRaises(ValueError):fuse_roots(.5,[Observation('fake','root',True)],[source()])
    def test_wrong_root_rejected(self):
        with self.assertRaises(ValueError):fuse_roots(.5,[Observation('first','wrong',True)],[source()])
    def test_unapproved_evidence_rejected(self):
        with self.assertRaises(PermissionError):fuse_roots(.5,[Observation('a','r',True)],[source('a','r',approved=False)])
    def test_duplicate_source_id_rejected(self):
        with self.assertRaises(ValueError):route_research(.5,[],[source(),source()])
    def test_unbounded_probs_rejected(self):
        for bad in [float('nan'),float('inf'),-1.,0.,1.,2.,True]:
            with self.subTest(bad=bad),self.assertRaises(ValueError):bayes_update(bad,source(),True)
    def test_sensor_invalids(self):
        with self.assertRaises(ValueError):source(r=1)
        with self.assertRaises(ValueError):EvidenceChannel('x','y',.8,.8,-1,True)
        with self.assertRaises(ValueError):EvidenceChannel('x','y',.8,.8,float('nan'),True)
    def test_real_multivalued_conflicts_are_not_probabilities(self):
        claims=load_json(ROOT/'data/raw/pera_conflict_research_fixture.json')['claims']
        data=reconcile_claims(claims*20)
        self.assertEqual(len(data),3)
        self.assertTrue(all(x['independent_publisher_count']==1 and x['status']=='disputed' for x in data.values()))


class ValueOfInformationTest(unittest.TestCase):
    def test_experiment_never_means_no_check(self):
        a=source('s','rs');r=route_research(.50,[],[a],mode='never')
        self.assertIn(r.action,{'LAB_ACCEPT','LAB_DEFER'});self.assertIsNone(r.selected_probe)
    def test_unapproved_source_not_queried(self):
        a=source('a','x',.999,.0,approved=False)
        self.assertIsNone(route_research(.7,[],[a],mode='cheapest').selected_probe)
    def test_same_root_not_queried(self):
        a=source('a','x');b=source('b','x',.999,0.0)
        route=route_research(.65,[Observation('a','x',True)],[a,b],mode='max_information')
        self.assertIsNone(route.selected_probe)
    def test_budget_limit(self):
        a=source('a','x',.99,.5)
        route=route_research(.55,[],[a],budget=.1,mode='cheapest')
        self.assertIsNone(route.selected_probe)
    def test_voi_is_nonnegative_before_cost(self):
        for p in [.1,.5,.7,.85,.99]:
            v=expected_value_of_sample(p,source('a','b',.88,.07))
            self.assertGreaterEqual(v.expected_decision_gain,0)
            self.assertGreaterEqual(v.expected_sample_information,-1e-12)
    def test_no_positive_net_no_check(self):
        a=source('expensive','x',.8,100.)
        r=route_research(.5,[],[a],budget=200,mode='voi')
        self.assertNotEqual(r.action,'VERIFY')
    def test_information_policy_distinct_from_voi(self):
        a=source('expensive','x',.8,.12)
        self.assertEqual(route_research(.5,[],[a],budget=.12,mode='max_information').action,'VERIFY')
        self.assertNotEqual(route_research(.5,[],[a],budget=.12,mode='voi').action,'VERIFY')
    def test_invalid_budget(self):
        with self.assertRaises(ValueError):route_research(.5,[],[],budget=float('inf'))
    def test_invalid_policy(self):
        with self.assertRaises(ValueError):route_research(.5,[],[],mode='agent_magic')
    def test_very_extreme_prior_finite(self):
        for p in [1e-8,1-1e-8]:
            self.assertTrue(math.isfinite(bayes_update(p,source(),False)))
    def test_not_verified_for_production(self):
        r=route_research(.9,[],[],mode='never')
        self.assertTrue(r.laboratory_only)
        self.assertTrue(r.belief.caveat.startswith('HYPOTHETICAL'))
    def test_core_field_requests_no_effect_on_decision(self):
        catalog=load_catalog();d=decide(catalog,Query(city='İstanbul',kind='place',budget=500))
        self.assertEqual(d.action,'REFRESH')
        tasks=field_research_tasks(d)
        self.assertTrue(tasks)
        self.assertTrue(all(t.field=='price' and t.status.startswith('PROPOSE_ONLY') for t in tasks))
        self.assertFalse(d.selected)
        self.assertEqual(field_research_tasks(decide(catalog,Query(city='İstanbul')),5),[])
    def test_task_order_stable(self):
        catalog=load_catalog()
        d=decide(catalog,Query(city='İstanbul',budget=500))
        a=field_research_tasks(d)
        self.assertEqual(a,field_research_tasks(d))
        with self.assertRaises(ValueError):field_research_tasks(d,0)
    def test_demo_no_live_calls(self):
        v=demo()
        self.assertEqual(v['pera_disputed_fields'],3)
        self.assertTrue(v['proposed_next_fields'])
        self.assertTrue(v['hypothetical_model_output']['not_real_world_calibrated'])


class SyntheticProtocolTest(unittest.TestCase):
    def test_same_seed_same_facts_and_sensors(self):
        self.assertEqual(generate('matched',34,5),generate('matched',34,5))
    def test_no_truth_leakage_into_decision(self):
        c=generate('matched',57,1)[0]
        r=one_case(c,'voi',{'decision_utility':dict(reward_true=1,penalty_false=4,min_probability=.8),'check_budget':.12})
        self.assertIn(r['result'],{'LAB_ACCEPT','LAB_DEFER'})
        self.assertTrue(math.isfinite(r['utility']))
    def test_benchmark_regimes_report_shift(self):
        x=run({'seed':114,'cases_per_regime':45,'regimes':['matched','source_degradation','prior_shift'],
               'policies':['never','cheapest','max_information','voi'],
               'check_budget':.12,'decision_utility':{'reward_true':1,'penalty_false':4,'min_probability':.8}})
        self.assertEqual(set(x['regimes']),{'matched','source_degradation','prior_shift'})
        self.assertFalse(x['real_source_validation'])
        for v in x['regimes'].values():
            self.assertEqual(v['methods']['voi']['cases'],45)
            self.assertEqual(v['methods']['never']['checks_per_case'],0)
            self.assertIsNotNone(v['voi_vs_never']['conditional_simulation_CI95'])

if __name__ == '__main__':
    unittest.main()
