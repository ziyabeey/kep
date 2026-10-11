"""CORE-002: synthetic cost-aware research plan, with no network or real labels."""
import copy
import math
import random
import unittest
from dataclasses import asdict

from kepcore.core import Query,load_catalog
from kepcore.evidence_lab import EvidenceChannel
from kepcore.temporal_pipeline import Signal
from kepcore.budgeted_verify import CheckOption,plan_research

AT='2026-10-10T12:00:00+03:00'
SEEN='2026-10-10T10:00:00+03:00'
PLACE=next(r for r in load_catalog() if r['kind']=='place')


def sample(*,rights='open_attribution'):
    r=copy.deepcopy(PLACE);r.update(id='synthetic:place:1',rights_scope=rights,
         source_url='synthetic://core002',source_record_hash='synthetic-only',
         synthetic=True,publisher_root='simulated_supplier')
    return r


def event(key, *,root='origin', yes=True,observed=SEEN,available=SEEN):
    return Signal(key,'synthetic:place:1',root,observed,available,yes,'research_ingest')


def channel(name='cheap',root='new_root',sens=.74,spec=.72,cost=.02,latency=2,approved=True):
    return CheckOption(EvidenceChannel(name,root,sens,spec,cost,approved),latency)


def observed_channel():
    return EvidenceChannel('original','origin',.87,.84,0,True,True)


def plan(events=None,options=None,*,q=None,record=None,prior=.72,budget=.10,wait=10,
         policy='voi',allowed=('origin','new_root','deeper_root'),old_channels=None):
    return plan_research([sample()] if record is None else [record],
        q or Query(city='İstanbul',kind='place',at=AT,limit=1),
        [event('original')] if events is None else events,
        tuple([channel()] if options is None else options),
        observed_channels=tuple([observed_channel()] if old_channels is None else old_channels),
        approved_roots=allowed,prior=prior,budget=budget,
        max_wait_minutes=wait,policy=policy)


class BudgetedPlanContracts(unittest.TestCase):
    def test_one_root_positive_selects_value_positive_proposal(self):
        result=plan()
        self.assertEqual(result.action,'PROPOSE_CHECK')
        self.assertEqual(result.probe_id,'cheap')
        self.assertEqual(result.probe_root,'new_root')
        self.assertGreater(result.assumed_expected_net_gain,0)
        self.assertEqual(result.estimated_latency_minutes,2)
        self.assertFalse(result.consumer_publish)
        self.assertFalse(result.authorized_to_fetch)
        self.assertIsNone(result.real_world_accuracy)
        self.assertTrue(result.laboratory_only)

    def test_two_independent_roots_already_present_no_more_cost(self):
        result=plan([event('a'),event('b',root='new_root')])
        self.assertEqual(result.action,'NO_CHECK_ALREADY_SUPPORTED')
        self.assertIsNone(result.probe_id)

    def test_root_conflict_human_review_not_automatic_arbitration(self):
        for events in ([event('pos'),event('neg',yes=False)],
                       [event('pos'),event('neg',root='new_root',yes=False)]):
            with self.subTest(events=events):
                res=plan(events)
                self.assertEqual(res.action,'HUMAN_REVIEW')
                self.assertIsNone(res.probe_id)

    def test_negative_only_not_treated_as_business_closure(self):
        result=plan([event('neg',yes=False)])
        self.assertEqual(result.action,'HUMAN_REVIEW')
        self.assertIsNone(result.physical_business_closures)

    def test_one_root_80_syndicated_copies_same_plan(self):
        baseline=plan()
        events=[event('original')]+[event(f'echo-{i}') for i in range(80)]
        self.assertEqual(plan(events),baseline)

    def test_future_late_and_stale_claims_not_usable(self):
        future=event('late',root='new_root',available='2026-10-10T13:00:00+03:00')
        self.assertEqual(plan([event('original'),future]).action,'PROPOSE_CHECK')
        stale=event('old',observed='2026-10-07T09:00:00+03:00',
                    available='2026-10-07T09:00:00+03:00')
        self.assertEqual(plan([stale]).action,'NO_CHECK_NO_INDEPENDENT_SEED')

    def test_core_rights_and_price_requirements_never_bypassed(self):
        rights=plan(record=sample(rights='pending'))
        self.assertEqual(rights.action,'CORE_REFUSED')
        self.assertIsNone(rights.probe_id)
        q=Query(city='İstanbul',kind='place',at=AT,budget=30,limit=1)
        price=plan(q=q)
        self.assertEqual(price.action,'CORE_REFUSED')
        self.assertNotEqual(price.core_action,'DISCOVER')

    def test_free_low_cost_unapproved_or_same_root_denied(self):
        echo=channel('echo','origin',sens=.999,spec=.999,cost=0)
        unlicensed=channel('unlicensed','other',sens=.999,spec=.999,cost=0,approved=False)
        result=plan(options=[echo,unlicensed],allowed=('origin','other'))
        self.assertEqual(result.action,'NO_CHECK_NO_ELIGIBLE_PROBE')
        self.assertIsNone(result.probe_id)

    def test_budget_and_deadline_hard_gate(self):
        pricey=channel('deep','deeper_root',cost=.11,latency=12)
        self.assertEqual(plan(options=[pricey],budget=.10,wait=20).action,
                         'NO_CHECK_NO_ELIGIBLE_PROBE')
        self.assertEqual(plan(options=[pricey],budget=.20,wait=5).action,
                         'NO_CHECK_NO_ELIGIBLE_PROBE')
        self.assertEqual(plan(options=[pricey],budget=.20,wait=15).action,
                         'PROPOSE_CHECK')

    def test_mode_specific_sorting_and_never(self):
        cheap=channel('cheap',root='new_root',cost=.015,sens=.62,spec=.60)
        deep=channel('deep',root='deeper_root',cost=.055,sens=.95,spec=.95)
        opts=[cheap,deep]
        self.assertEqual(plan(options=opts,policy='cheapest').probe_id,'cheap')
        self.assertEqual(plan(options=opts,policy='max_information').probe_id,'deep')
        self.assertEqual(plan(options=opts,policy='never').action,'NO_CHECK_POLICY')
        self.assertEqual(plan(options=opts,policy='always_strong').probe_id,'deep')

    def test_voi_rejects_fictional_low_value_despite_budget(self):
        res=plan(prior=.002,options=[channel(sens=.51,spec=.51,cost=.09)])
        self.assertEqual(res.action,'NO_CHECK_LOW_VALUE')
        self.assertIsNone(res.probe_id)

    def test_missing_source_calibration_refused_not_assumed(self):
        with self.assertRaises(ValueError):plan(old_channels=[])

    def test_missing_approved_roots_refused(self):
        with self.assertRaises(ValueError):plan(allowed=())

    def test_unregistered_approved_option_denied(self):
        r=plan(options=[channel(root='outside')])
        self.assertEqual(r.action,'NO_CHECK_NO_ELIGIBLE_PROBE')

    def test_invalid_input_no_silent_price_or_cost_defaults(self):
        for kw in [{'budget':-1}, {'budget':float('nan')},
                   {'budget':True}, {'wait':-2}, {'wait':True},
                   {'policy':'auto_publish'}, {'prior':.0},{'prior':1.0}]:
            with self.subTest(kw=kw), self.assertRaises((TypeError,ValueError)):
                plan(**kw)

    def test_probe_identity_duplicates_rejected(self):
        opts=[channel('dup','new_root'),channel('dup','deeper_root')]
        with self.assertRaises(ValueError):plan(options=opts)

    def test_option_validates_latency_and_error_rates(self):
        for latency in (True,-1,1441,1.5):
            with self.subTest(latency=latency),self.assertRaises(ValueError):
                channel(latency=latency)
        with self.assertRaises(ValueError):channel(sens=1.1)

    def test_order_replay_is_deterministic_and_no_input_mutation(self):
        events=[event('original')]+[event(f'echo-{i}') for i in range(10)]
        options=[channel('a','new_root'),channel('b','deeper_root')]
        snapshot=(list(events),list(options))
        expected=plan(events,options)
        for seed in range(12):
            e,o=events[:],options[:]
            random.Random(seed).shuffle(e);random.Random(seed).shuffle(o)
            self.assertEqual(plan(e,o),expected)
        self.assertEqual((events,options),snapshot)

    def test_strict_lab_only_no_model_or_external_network(self):
        r=plan()
        flattened=str(asdict(r))
        self.assertNotIn('http://',flattened)
        self.assertNotIn('https://',flattened)
        self.assertFalse(r.model_used)
        self.assertIsNone(r.real_world_accuracy)
        self.assertIsNone(r.physical_business_openings)
        self.assertFalse(r.consumer_publish)


    def test_expected_gain_matches_actual_two_root_gate(self):
        """A positive second root triggers lab support even at low modeled p.

        The planner must charge the *actual* payoff if that occurs, not
        quietly assume a separate min-probability gate exists in CORE-001.
        """
        option=channel(sens=.51,spec=.51,cost=.09)
        p=plan(prior=.002,options=[option],policy='cheapest')
        self.assertEqual(p.action,'PROPOSE_CHECK')
        self.assertLess(p.assumed_expected_net_gain,-.09)
        self.assertFalse(p.authorized_to_fetch)


if __name__=='__main__':
    unittest.main()
