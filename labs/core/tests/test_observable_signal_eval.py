"""Only previously UNCOVERED observable-signal risks, no test-count inflation."""
from dataclasses import replace
from datetime import timedelta
import unittest

from benchmarks.observable_signal_eval import (
    ObservedVote,ReviewPulse,observable_snapshot,project_at,
    generate_holdout,choose_policy,protocol,evaluate_gate,REGIMES,POLICIES,
)
from benchmarks.adaptive_trust_eval import TIME
from kepcore.calibration import aware


class ObservableValueContracts(unittest.TestCase):
    def test_future_and_unadjudicated_answers_are_not_observable(self):
        cases,audits=generate_holdout('abrupt_outage',159,3)
        cutoff=cases[0].view.query.at
        completed,votes,pulses=project_at(audits,as_of=cutoff)
        self.assertTrue(all(aware(v.observed_at)<=aware(cutoff) for v in votes))
        self.assertTrue(all(aware(a.adjudicated_at)<=aware(cutoff) for a in completed))
        self.assertTrue(all(aware(p.completed_at)<=aware(cutoff) for p in pulses))
        # Resampling synthetic truth labels may change an already-reviewed
        # baseline calibrator, but must NEVER change raw-source observability.
        changed=[replace(a,truth=not a.truth) for a in audits]
        _,raw_again,pulses_again=project_at(changed,as_of=cutoff)
        self.assertEqual(raw_again,votes)
        self.assertEqual(pulses_again,pulses)

    def test_duplicate_copy_and_equal_clock_conflict_cannot_inflate_pairs(self):
        stamp=(TIME-timedelta(hours=1)).isoformat()
        raws=[]
        for i in range(20):
            ent='synthetic:unit:'+str(i)
            raws.append(ObservedVote(ent,'origin',stamp,True))
            raws.append(ObservedVote(ent,'deep_root',stamp,i%3!=0))
        pulse=(ReviewPulse((TIME-timedelta(hours=10)).isoformat()),)
        expected=observable_snapshot(tuple(raws),pulse,as_of=TIME.isoformat())
        self.assertEqual(expected.independent_pairs,20)
        self.assertEqual(expected.discordant_pairs,7)
        # Copied URLs with same root do not become new samples.
        repeated=observable_snapshot(tuple(raws+[raws[0]]*200),
                                     pulse,as_of=TIME.isoformat())
        self.assertEqual(expected,repeated)
        # A same-time contradictory original becomes unusable for that entity.
        contradictory=replace(raws[0],supports=False)
        ambiguous=observable_snapshot(tuple(raws+[contradictory]),
                                      pulse,as_of=TIME.isoformat())
        self.assertEqual(ambiguous.independent_pairs,19)

    def test_same_outage_heartbeat_cannot_identify_hidden_source_quality(self):
        stable,a=generate_holdout('stable_outage',124,120)
        broken,b=generate_holdout('abrupt_outage',124,120)
        ca=stable[110].view.query.at
        cb=broken[110].view.query.at
        self.assertEqual(ca,cb)
        labels_a,raw_a,pulses_a=project_at(a,as_of=ca)
        labels_b,raw_b,pulses_b=project_at(b,as_of=cb)
        self.assertEqual(tuple(p.completed_at for p in pulses_a),
                         tuple(p.completed_at for p in pulses_b))
        feature_a=observable_snapshot(raw_a,pulses_a,as_of=ca)
        feature_b=observable_snapshot(raw_b,pulses_b,as_of=cb)
        self.assertEqual(feature_a.completed_audit_age_hours,
                         feature_b.completed_audit_age_hours)
        self.assertEqual(feature_a.independent_pairs,feature_b.independent_pairs)
        # No universal guarantee of disagreement separability is asserted.

    def test_current_trial_truth_and_future_probe_answers_absent_from_policy(self):
        cases,audits=generate_holdout('stable_outage',881,2)
        case=cases[1]
        completed,raw,pulse=project_at(audits,as_of=case.view.query.at)
        a=choose_policy(case.view,completed,raw,pulse,'unlabelled_disagreement')
        altered=replace(case,truth=not case.truth,
                        hidden_answers=(('deep',not case.truth),))
        b=choose_policy(altered.view,completed,raw,pulse,'unlabelled_disagreement')
        self.assertEqual(a,b)
        with self.assertRaises(TypeError):
            choose_policy(case,completed,raw,pulse,'unlabelled_disagreement')

    def test_hard_go_no_go_requires_all_precommitted_checks(self):
        cfg=protocol()
        def method(utility,incorrect=0):
            return {'utility_per_case':utility,'false_assertions':incorrect}
        tables={}
        for name in REGIMES:
            tables[name]={'methods':{
                p:method(.3) for p in POLICIES
            }}
        diag={name:{'flagged_fraction_after_85':0.0} for name in REGIMES}
        decision=evaluate_gate(tables,diag,cfg)
        self.assertEqual(decision['decision'],'NO_GO')
        self.assertTrue(decision['failed_checks'])
        self.assertFalse(decision['acceptance_does_not_authorize_production'] is False)


if __name__=='__main__':
    unittest.main()
