"""CORE-004A targeted tests for the ONE measured CORE-003 outage failure.

These tests cover distinct new decisions not exercised by the existing
CORE-001/002/003 safety suite. All history and venues are synthetic.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
import unittest

from benchmarks.budgeted_core_eval import TIME,generate
from kepcore.adaptive_trust import AuditFeedback,plan_adaptive
from kepcore.outage_grace import plan_outage_grace

AT=TIME
ROOTS=('origin','deep_root')


def _case():
    sample=generate('matched',901,2)[1].view
    origin=next(x for x in sample.signals if x.publisher_root=='origin')
    deep=next(x for x in sample.probes if x.channel.id=='deep')
    return replace(sample,signals=(replace(origin,supports=True),),probes=(deep,))


def _audit(i,root,*,truth,support,age=85,available_delay=1):
    from kepcore.calibration import aware
    when=AT-timedelta(hours=age)
    return AuditFeedback(f'qa004:{root}:{i}',f'synthetic:other:{i}',root,
        when.isoformat(),(when+timedelta(hours=available_delay)).isoformat(),
        support,truth)


def _history(*,deep_false_positives=False,recent=True):
    rows=[]
    for root in ROOTS:
        for i in range(80):
            truth=i<40
            support=True if deep_false_positives and root=='deep_root' else truth
            rows.append(_audit(i,root,truth=truth,support=support))
        if recent:
            for i in (80,81):
                truth=i==80
                support=truth if root=='origin' or not deep_false_positives else True
                rows.append(_audit(i,root,truth=truth,support=support,age=10))
    return rows


def _call(c,audits,**kw):
    return plan_outage_grace(
       [c.record],c.query,c.signals,c.probes,
       observed_channels=c.observed_sources,
       approved_roots=c.approved_roots,prior=c.prior,budget=c.budget,
       max_wait_minutes=c.max_wait_minutes,audits=audits,**kw)


def _conservative(c,audits):
    return plan_adaptive(
       [c.record],c.query,c.signals,c.probes,
       observed_channels=c.observed_sources,
       approved_roots=c.approved_roots,prior=c.prior,budget=c.budget,
       max_wait_minutes=c.max_wait_minutes,audits=audits,
       mode='conservative',window_hours=72,min_class_n=12)


class OutageGraceValueTests(unittest.TestCase):
    def test_bounded_fallback_adds_one_affordable_check_when_short_frame_insufficient(self):
        c=_case();rows=_history()
        self.assertIn(_conservative(c,rows).action,{
           'NO_CHECK_INSUFFICIENT_AUDITS',
           'NO_CHECK_INSUFFICIENT_OR_UNCERTAIN_PROBES'})
        decision=_call(c,rows)
        self.assertEqual(decision.action,'PROPOSE_CHECK')
        self.assertEqual(decision.probe_id,'deep')
        self.assertLessEqual(decision.proposed_cost,c.budget)
        self.assertLessEqual(decision.estimated_latency_minutes,c.max_wait_minutes)
        self.assertFalse(decision.authorized_to_fetch)
        self.assertFalse(decision.consumer_publish)

    def test_stale_history_cannot_be_reactivated_without_recent_completed_audit(self):
        c=_case()
        self.assertNotEqual(_call(c,_history(recent=False)).action,'PROPOSE_CHECK')
        rows=_history(recent=False)
        for root in ROOTS:
            for i in (80,81):
                truth=i==80
                # Seen recently, but adjudication is in the FUTURE.
                rows.append(_audit(i,root,truth=truth,support=truth,
                                   age=10,available_delay=12))
        self.assertNotEqual(_call(c,rows).action,'PROPOSE_CHECK')

    def test_reject_high_recall_zero_specificity_second_root(self):
        c=_case()
        result=_call(c,_history(deep_false_positives=True))
        self.assertNotEqual(result.action,'PROPOSE_CHECK')
        self.assertIsNone(result.probe_id)

    def test_cannot_override_explicit_recent_uncertainty_warning(self):
        c=_case()
        rows=_history()
        for i in range(82,162):
            truth=i%2==0
            # New independent audit stream shows origin is almost random.
            rows.append(_audit(i,'origin',truth=truth,support=i%3==0,age=5))
        previous=_conservative(c,rows)
        self.assertEqual(previous.action,'NO_CHECK_UNCERTAIN_ORIGIN')
        after=_call(c,rows)
        self.assertEqual(after.action,previous.action)
        self.assertIsNone(after.probe_id)

    def test_never_bypass_hard_core_or_consumer_authority(self):
        c=_case();rows=_history()
        c=replace(c,record={**c.record,'rights_scope':'pending'})
        result=_call(c,rows)
        self.assertEqual(result.action,'CORE_REFUSED')
        self.assertIsNone(result.probe_id)
        self.assertFalse(result.authorized_to_fetch)
        self.assertFalse(result.consumer_publish)

    def test_budget_and_deadline_remain_hard_and_no_data_modification(self):
        c=_case();rows=_history()
        original=rows[:]
        c2=replace(c,budget=.03,max_wait_minutes=2)
        result=_call(c2,rows)
        self.assertNotEqual(result.action,'PROPOSE_CHECK')
        self.assertEqual(rows,original)

    def test_invalid_grace_and_window_settings_are_rejected(self):
        c=_case();rows=_history()
        for kw in ({'grace_hours':0},{'grace_hours':True},
                   {'long_window_hours':48},{'long_window_hours':900},
                   {'short_window_hours':0}):
            with self.subTest(kw=kw),self.assertRaises(ValueError):
                _call(c,rows,**kw)


if __name__=='__main__':
    unittest.main()
