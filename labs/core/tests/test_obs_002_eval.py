"""KEP-OBS-002 targeted leakage and accounting tests (research branch only).

One test per preregistered mutant in obs_002_protocol.json audit_requirements.
"""
import unittest
from dataclasses import asdict, fields, replace
from datetime import timedelta
from decimal import Decimal

from kepcore.calibration import aware
from benchmarks import obs_002_eval as E

CFG = E.load_protocol()
PILOT = CFG['pilot']['seed']


def _view(regime='outage_stable', i=60):
    return E.generate_cases(CFG, regime, PILOT, i + 1)[i].view


def _votes(view, n, disagree, *, delivered_late=False, hours_ago=1):
    at = aware(view.query.at) - timedelta(hours=hours_ago)
    later = aware(view.query.at) + timedelta(hours=1)
    out = []
    for k in range(n):
        e = f'synthetic:test-bg:{k}'
        a = at.isoformat()
        b = later.isoformat() if delivered_late else a
        out.append(E.ObservedVote('origin', e, a, b, True))
        out.append(E.ObservedVote('deep_root', e, a, b, not (k < disagree)))
    return out



def _old_pulse(view):
    return E.ReviewPulse((aware(view.query.at) - timedelta(hours=9)).isoformat())


class ObsTwoLeakageTests(unittest.TestCase):
    def test_observed_vote_and_pulse_have_no_outcome_fields(self):
        # Mutant: truth exposed in ObservedVote / reviewer outcome in pulse.
        self.assertEqual({f.name for f in fields(E.ObservedVote)},
                         {'root', 'entity_id', 'observed_at', 'available_at', 'supports'})
        self.assertEqual({f.name for f in fields(E.ReviewPulse)}, {'last_completed_at'})
        view = _view()
        self.assertNotIn('truth', asdict(view))
        self.assertNotIn('hidden_answers', asdict(view))

    def test_undelivered_votes_are_invisible(self):
        # Mutant: available_at filter removed. 40 disagreeing pairs delivered
        # only after the decision would otherwise force an alarm.
        view = _view()
        late = _votes(view, 40, 40, delivered_late=True)
        mode, info = E.select_mode(view, late, _old_pulse(view), E.CANDIDATE)
        self.assertEqual((mode, info.disagreement, info.pairs), ('conservative', None, 0))
        # Also through the executor-side filter.
        raws = [E.RawVote(v, True) for v in late]
        _, visible, _ = E.policy_inputs(view, raws, ())
        self.assertEqual(visible, ())

    def test_current_case_cannot_feed_telemetry(self):
        view = _view()
        own = E.ObservedVote('origin', view.record['id'], view.query.at, view.query.at, True)
        with self.assertRaises(ValueError):
            E.select_mode(view, _votes(view, 20, 0) + [own], _old_pulse(view), E.CANDIDATE)
        raws, _ = E.generate_background(CFG, 'outage_syndicated_drift', PILOT, 30)
        cases = E.generate_cases(CFG, 'outage_syndicated_drift', PILOT, 30)
        self.assertFalse({c.view.record['id'] for c in cases} & {r.vote.entity_id for r in raws})

    def test_reviewer_outcomes_do_not_change_selector(self):
        regime = 'outage_midstream_drift'
        cases = E.generate_cases(CFG, regime, PILOT, 50)
        raws, audits = E.generate_background(CFG, regime, PILOT, 50)
        flipped = tuple(replace(a, truth=not a.truth) for a in audits)
        for c in cases[::7]:
            _, v1, p1 = E.policy_inputs(c.view, raws, audits)
            _, v2, p2 = E.policy_inputs(c.view, raws, flipped)
            self.assertEqual(E.select_mode(c.view, v1, p1, E.CANDIDATE),
                             E.select_mode(c.view, v2, p2, E.CANDIDATE))

    def test_frozen_thresholds_and_boundaries(self):
        # Mutant: threshold altered.
        self.assertEqual((E.LOOKBACK_HOURS, E.MIN_ENTITIES, E.CUTOFF, E.MAX_REVIEW_AGE_HOURS),
                         (12, 18, 0.35, 8))
        view = _view()
        pulse = _old_pulse(view)
        self.assertEqual(E.select_mode(view, _votes(view, 20, 7), pulse, E.CANDIDATE)[0], 'fixed_voi')   # 0.35
        self.assertEqual(E.select_mode(view, _votes(view, 20, 8), pulse, E.CANDIDATE)[0], 'conservative')  # 0.40
        self.assertEqual(E.select_mode(view, _votes(view, 17, 0), pulse, E.CANDIDATE)[0], 'conservative')
        self.assertEqual(E.select_mode(view, _votes(view, 18, 0, hours_ago=13), pulse,
                                       E.CANDIDATE)[0], 'conservative')
        fresh = E.ReviewPulse((aware(view.query.at) - timedelta(hours=8)).isoformat())
        self.assertEqual(E.select_mode(view, _votes(view, 20, 0), fresh, E.CANDIDATE)[0], 'conservative')
        self.assertEqual(E.select_mode(view, (), pulse, 'audit_age_only')[0], 'fixed_voi')

    def test_telemetry_cost_charged_on_every_read(self):
        # Mutant: telemetry cost not charged.
        res = E.run_regime(CFG, 'outage_stable', PILOT, 40, 100, 1)
        c = res['methods'][E.CANDIDATE]
        self.assertGreater(c['telemetry_reads'], 0)
        expected = Decimal(str(c['utility_per_case_gross'])) - E.TELEMETRY_COST*c['telemetry_reads']/40
        self.assertAlmostEqual(c['utility_per_case'], float(expected), places=5)
        self.assertEqual(res['methods']['audit_age_only']['telemetry_reads'], 0)

    def test_protocol_hash_is_enforced(self):
        self.assertEqual(E.load_protocol()['study'], 'KEP-OBS-002')


if __name__ == '__main__':
    unittest.main()
