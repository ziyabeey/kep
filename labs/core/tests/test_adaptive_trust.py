"""CORE-003 tests: independent past synthetic audits never leak test truth."""
import unittest
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from unittest.mock import patch

from kepcore.adaptive_trust import AuditFeedback,estimate_sources,plan_adaptive
from benchmarks.budgeted_core_eval import generate

T=datetime(2026,10,10,9,tzinfo=timezone.utc)

def feedback(i,root='deep_root',*,truth=True,support=True,observed=None,delay=2,
             entity=None,origin='synthetic_independent_audit',sampling='independent_uniform'):
    when=observed or T-timedelta(hours=16-i%12)
    return AuditFeedback(f'audit-{root}-{i}',entity or f'synthetic:background:{i}',
                         root,when.isoformat(),(when+timedelta(hours=delay)).isoformat(),
                         support,truth,origin,sampling)

def training(roots=('origin','cheap_root','balanced_root','deep_root'),n=100):
    result=[]
    for root in roots:
        for i in range(n):
            truth=i%3!=0
            support=truth if i%13 else not truth
            result.append(feedback(i,root,truth=truth,support=support))
    return result

def trial():
    return generate('matched',901,1)[0]

def adaptive(audits,mode='posterior_mean',t=None):
    c=trial();v=c.view
    if t is not None:
        v=replace(v,query=replace(v.query,at=t))
    return plan_adaptive([v.record],v.query,v.signals,v.probes,
                         observed_channels=v.observed_sources,
                         approved_roots=v.approved_roots,prior=v.prior,budget=v.budget,
                         max_wait_minutes=v.max_wait_minutes,
                         audits=audits,mode=mode)

class AuditTimeContracts(unittest.TestCase):
    def test_class_conditional_rates_and_unbiased_denominators(self):
        report=estimate_sources(training(),as_of=T.isoformat(),approved_roots=
             ('origin','cheap_root','balanced_root','deep_root'),min_class_n=10)
        self.assertEqual(set(report),{'origin','cheap_root','balanced_root','deep_root'})
        root=report['deep_root']
        self.assertEqual(root.status,'READY')
        self.assertEqual(root.positive_truth_n+root.negative_truth_n,100)
        self.assertGreater(root.sensitivity_mean,.8)
        self.assertGreater(root.specificity_mean,.8)
        self.assertLess(root.sensitivity_lower,root.sensitivity_mean)
        self.assertLess(root.specificity_lower,root.specificity_mean)
        self.assertFalse(root.real_world_calibrated)

    def test_future_adjudications_never_change_old_decision(self):
        history=training()
        later=feedback(555,'deep_root',truth=False,support=True,observed=T-
                       timedelta(hours=1),delay=72)
        b=estimate_sources(history,as_of=T.isoformat(),approved_roots=('deep_root',))
        a=estimate_sources(history+[later],as_of=T.isoformat(),
                           approved_roots=('deep_root',))
        self.assertEqual(a,b)

    def test_window_uses_observation_and_review_availability(self):
        old=feedback(1,observed=T-timedelta(hours=120),delay=1)
        recent=feedback(2,observed=T-timedelta(hours=20),delay=1)
        f=estimate_sources([old,recent],as_of=T.isoformat(),
                           approved_roots=('deep_root',),window_hours=72,
                           min_class_n=1)
        self.assertEqual(f['deep_root'].observations_used,1)
        self.assertEqual(f['deep_root'].status,'INSUFFICIENT_CLASS_SUPPORT')

    def test_no_original_test_entity_as_audit_label(self):
        t=trial()
        leaking=feedback(1,'origin',entity=t.view.record['id'])
        with self.assertRaises(ValueError):
            estimate_sources([leaking],as_of=T.isoformat(),
                approved_roots=('origin',),exclude_entity_id=t.view.record['id'])

    def test_syndicated_duplicate_does_not_create_new_audits(self):
        history=training(roots=('deep_root',))
        same=feedback(0,'deep_root',truth=False,support=False)
        same=replace(same,entity_id=history[0].entity_id,
                     observed_at=history[0].observed_at,
                     adjudicated_at=history[0].adjudicated_at,
                     supports=history[0].supports,truth=history[0].truth)
        expected=estimate_sources(history,as_of=T.isoformat(),approved_roots=('deep_root',))
        got=estimate_sources(history+[same],as_of=T.isoformat(),
                             approved_roots=('deep_root',))
        self.assertEqual(got,expected)

    def test_conflicting_same_observation_is_not_training_data(self):
        x=feedback(1)
        b=replace(x,audit_id='other',supports=not x.supports)
        with self.assertRaises(ValueError):
            estimate_sources([x,b],as_of=T.isoformat(),approved_roots=('deep_root',))

    def test_unknown_and_opportunistically_selected_reviews_rejected(self):
        for edit in (dict(origin='human_label'),dict(sampling='selected_by_policy'),
                     dict(origin='invented'),dict(truth=1)):
            with self.subTest(edit=edit),self.assertRaises(ValueError):
                replace(feedback(0),**edit)

    def test_no_reverse_causality_and_naive_clocks(self):
        bad=T-timedelta(hours=1)
        with self.assertRaises(ValueError):
            replace(feedback(0),observed_at=T.isoformat(),adjudicated_at=bad.isoformat())
        with self.assertRaises(ValueError):
            replace(feedback(0),observed_at='2026-10-11T10:00:00')

    def test_invalid_roots_duplicate_audit_id_fail_closed(self):
        x=feedback(1)
        with self.assertRaises(ValueError):
            estimate_sources([x,replace(x,truth=False)],as_of=T.isoformat(),
                             approved_roots=('deep_root',))
        with self.assertRaises(ValueError):
            estimate_sources([x],as_of=T.isoformat(),approved_roots=())

    def test_order_invariance_and_idempotent_exact_replay(self):
        history=training(roots=('deep_root',))
        a=estimate_sources(history,as_of=T.isoformat(),approved_roots=('deep_root',))
        b=estimate_sources(list(reversed(history))+[history[0]]*5,
                           as_of=T.isoformat(),approved_roots=('deep_root',))
        self.assertEqual(a,b)

    def test_insufficient_audits_withheld_not_confident_fake_prior(self):
        c=trial();v=c.view
        # A known one-root positive case is needed to inspect a proposal.
        origin = next(s for s in v.signals if s.publisher_root=='origin')
        positive=replace(origin,supports=True)
        one=replace(v,signals=(positive,))
        r=plan_adaptive([one.record],one.query,one.signals,one.probes,
                        observed_channels=one.observed_sources,
                        approved_roots=one.approved_roots,prior=one.prior,
                        budget=one.budget,max_wait_minutes=one.max_wait_minutes,
                        audits=[],mode='posterior_mean')
        self.assertEqual(r.action,'NO_CHECK_INSUFFICIENT_AUDITS')
        self.assertIsNone(r.probe_id)
        self.assertFalse(r.consumer_publish)

    def test_pessimistic_guard_blocks_degraded_history(self):
        c=trial();v=c.view
        origin=next(s for s in v.signals if s.publisher_root=='origin')
        one=replace(v,signals=(replace(origin,supports=True),))
        history=[]
        for root in ('origin','cheap_root','balanced_root','deep_root'):
            for i in range(120):
                truth=i%3!=0
                support=truth if i%2 else not truth
                history.append(feedback(i,root,truth=truth,support=support))
        def call(mode):
            return plan_adaptive([one.record],one.query,one.signals,one.probes,
                observed_channels=one.observed_sources,approved_roots=one.approved_roots,
                prior=one.prior,budget=one.budget,max_wait_minutes=one.max_wait_minutes,
                audits=history,mode=mode)
        result=call('conservative')
        self.assertEqual(result.action,'NO_CHECK_UNCERTAIN_ORIGIN')
        self.assertFalse(result.authorized_to_fetch)

    def test_existing_core_rights_still_strict_before_audit(self):
        c=trial();v=c.view
        blocked=replace(v,record={**v.record,'rights_scope':'pending'})
        r=plan_adaptive([blocked.record],blocked.query,blocked.signals,blocked.probes,
                observed_channels=blocked.observed_sources,
                approved_roots=blocked.approved_roots,prior=blocked.prior,
                budget=blocked.budget,max_wait_minutes=blocked.max_wait_minutes,
                audits=[],mode='conservative')
        self.assertEqual(r.action,'CORE_REFUSED')
        self.assertIsNone(r.probe_id)

    def test_audit_history_never_escapes_to_result_or_network(self):
        c=trial();v=c.view
        rows=training()
        with patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('NETWORK')):
            result=plan_adaptive([v.record],v.query,v.signals,v.probes,
                observed_channels=v.observed_sources,approved_roots=v.approved_roots,
                prior=v.prior,budget=v.budget,max_wait_minutes=v.max_wait_minutes,
                audits=rows,mode='conservative')
        self.assertFalse(result.consumer_publish)
        self.assertFalse(result.authorized_to_fetch)
        self.assertIsNone(result.real_world_accuracy)
        self.assertNotIn(rows[0].audit_id,str(result))
        self.assertNotIn(rows[0].entity_id,str(result))

    def test_invalid_mode_or_window_fails(self):
        c=trial();v=c.view
        for mode in ('auto_publish','oracle_truth'):
            with self.assertRaises(ValueError):
                plan_adaptive([v.record],v.query,v.signals,v.probes,
                    observed_channels=v.observed_sources,approved_roots=v.approved_roots,
                    prior=v.prior,budget=v.budget,max_wait_minutes=v.max_wait_minutes,
                    audits=[],mode=mode)
        with self.assertRaises(ValueError):
            estimate_sources([],as_of=T.isoformat(),approved_roots=('origin',),
                             window_hours=0)

if __name__=='__main__':
    unittest.main()
