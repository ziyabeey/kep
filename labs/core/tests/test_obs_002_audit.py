"""Independent-auditor additions to the KEP-OBS-002 targeted tests (pilot seed only).

Each test names the surviving mutant(s) it kills. Nothing here changes the
evaluator; config copies are test fixtures only and never the holdout seed.
"""
import copy
import unittest
from dataclasses import asdict, replace
from datetime import timedelta

from kepcore.adaptive_trust import AuditFeedback
from kepcore.calibration import aware
from kepcore.core import load_catalog
from benchmarks import obs_002_eval as E

CFG = E.load_protocol()
PILOT = CFG['pilot']['seed']
C = E.CANDIDATE


def _view(regime='outage_stable', i=60):
    return E.generate_cases(CFG, regime, PILOT, i + 1)[i].view


def _votes(view, n, disagree, *, hours_ago=1):
    at = (aware(view.query.at) - timedelta(hours=hours_ago)).isoformat()
    out = []
    for k in range(n):
        e = f'synthetic:test-bg:{k}'
        out += [E.ObservedVote('origin', e, at, at, True),
                E.ObservedVote('deep_root', e, at, at, not (k < disagree))]
    return out


def _old_pulse(view):
    return E.ReviewPulse((aware(view.query.at) - timedelta(hours=9)).isoformat())


def _cfg(regime, **over):
    cfg = copy.deepcopy(CFG)
    cfg['generator']['regimes'][regime].update(over)
    return cfg


class AuditAdditions(unittest.TestCase):
    # ---- (a) truth exposed -------------------------------------------------
    def test_background_votes_are_publisher_answers_not_truth(self):      # kills a2
        raws, _ = E.generate_background(CFG, 'outage_stable', PILOT, 10)
        origin = [r for r in raws if r.vote.root == 'origin']
        agree = sum(r.vote.supports == r.truth for r in origin)/len(origin)
        self.assertTrue(0.75 < agree < 0.95, agree)   # stable origin quality ~0.85

    def test_view_record_has_no_extra_keys(self):                          # kills a3, a4
        base = next(x for x in load_catalog() if x['kind'] == 'place' and x['city'] == 'İstanbul')
        for regime in E.REGIMES:
            for t in E.generate_cases(CFG, regime, PILOT, 20):
                self.assertEqual(set(t.view.record), set(base))
                blob = repr(asdict(t.view)).lower()
                for word in ('truth', 'answer', 'hidden'):
                    self.assertNotIn(word, blob)

    # ---- (d) reviewer outcome visible to selector ---------------------------
    def test_pulse_is_latest_completed_review_regardless_of_outcome(self):  # kills d2, d5
        view = _view()
        at = aware(view.query.at)
        def audit(k, hours_ago, truth):
            t = at - timedelta(hours=hours_ago)
            return AuditFeedback(audit_id=f'test-audit:{k}', entity_id=f'synthetic:test-audit:{k}',
                                 publisher_root='origin', observed_at=(t - timedelta(hours=3)).isoformat(),
                                 adjudicated_at=t.isoformat(), supports=True, truth=truth)
        for latest_truth in (True, False):
            audits = (audit(0, 20, True), audit(1, 20, False), audit(2, 2, latest_truth),
                      audit(3, -1, True))                      # adjudicated in the future
            done, _, pulse = E.policy_inputs(view, (), audits)
            self.assertEqual(pulse.last_completed_at, (at - timedelta(hours=2)).isoformat())
            self.assertEqual({a.audit_id for a in done}, {'test-audit:0', 'test-audit:1', 'test-audit:2'})

    def test_selector_calls_invariant_to_reviewer_outcomes_end_to_end(self):  # kills d3, d4
        def record(flip):
            calls, real_sel, real_bg = [], E.select_mode, E.generate_background
            def spy(*a, **k):
                out = real_sel(*a, **k); calls.append((a[0].query.at, a[3], out)); return out
            def bg(*a, **k):
                raws, audits = real_bg(*a, **k)
                return raws, (tuple(replace(x, truth=not x.truth) for x in audits) if flip else audits)
            E.select_mode, E.generate_background = spy, bg
            try:
                E.run_regime(CFG, 'outage_midstream_drift', PILOT, 60, 20, 1)
            finally:
                E.select_mode, E.generate_background = real_sel, real_bg
            return calls
        a, b = record(False), record(True)
        self.assertTrue(any(c[2][1].read for c in a))
        self.assertEqual(a, b)

    # ---- (e) telemetry cost ------------------------------------------------
    def _age_over_8h(self, cfg, regime, n):
        trials = E.generate_cases(cfg, regime, PILOT, n)
        raws, audits = E.generate_background(cfg, regime, PILOT, n)
        return sum(aware(t.view.query.at) - aware(E.policy_inputs(t.view, raws, audits)[2].last_completed_at)
                   > timedelta(hours=E.MAX_REVIEW_AGE_HOURS) for t in trials)

    def test_cost_charged_on_every_old_review_decision_even_insufficient(self):  # kills e3
        regime = 'outage_raw_loss_drift'
        res = E.run_regime(CFG, regime, PILOT, 60, 20, 1)
        self.assertGreater(res['insufficient_pair_decisions'], 0)
        self.assertEqual(res['methods'][C]['telemetry_reads'], self._age_over_8h(CFG, regime, 60))

    def test_cost_charged_on_alarm_decisions(self):                        # kills e4
        regime = 'outage_midstream_drift'
        cfg = _cfg(regime, drift_onset_step=20)        # fixture only: force alarms inside 60 steps
        res = E.run_regime(cfg, regime, PILOT, 60, 20, 1)
        self.assertGreater(res['alarm_rate_from_step_48'], 0)
        self.assertEqual(res['methods'][C]['telemetry_reads'], self._age_over_8h(cfg, regime, 60))

    def test_paired_bootstrap_and_gates_are_net_of_telemetry(self):        # kills e6, e7
        res = E.run_regime(CFG, 'outage_stable', PILOT, 40, 100, 1)
        m = res['methods']
        self.assertAlmostEqual(res['candidate_minus_conservative']['mean'],
                               m[C]['utility_per_case'] - m['conservative']['utility_per_case'], places=6)
        fake = _passing_results()
        fake['outage_midstream_drift']['methods'][C].update(utility_per_case=0.124, utility_per_case_gross=0.2)
        self.assertFalse(E.gates(fake)['G1_primary_beats_both'])

    # ---- (f) thresholds and boundaries --------------------------------------
    def test_inclusive_boundaries(self):                                    # kills f6, f7
        view = _view(); pulse = _old_pulse(view)
        self.assertEqual(E.select_mode(view, _votes(view, 18, 0), pulse, C)[0], 'fixed_voi')
        self.assertEqual(E.select_mode(view, _votes(view, 18, 0, hours_ago=12), pulse, C)[0], 'fixed_voi')
        late = [replace(v, available_at=view.query.at) for v in _votes(view, 18, 0)]
        self.assertEqual(E.select_mode(view, late, pulse, C)[0], 'fixed_voi')

    def test_gate_thresholds(self):                                         # kills f12, f13, g8
        self.assertTrue(all(E.gates(_passing_results()).values()))
        checks = [
            ('G1_primary_beats_both', 'outage_midstream_drift', 'fixed_voi', 'utility_per_case', 0.1001),
            ('G1_primary_beats_both', 'outage_midstream_drift', 'conservative', 'utility_per_case', 0.1001),
            ('G3_distinct_mistakes_avoided', 'outage_midstream_drift', C, 'false_assertions', 1),
            ('G3_distinct_mistakes_avoided', 'outage_midstream_drift', C, 'missed_true', 1),
            ('G4_stable_recovery', 'outage_stable', C, 'utility_per_case', 0.1249),
            ('G5_raw_loss_safe_fallback', 'outage_raw_loss_drift', C, 'utility_per_case', 0.0899),
            ('G6_syndication_harm_cap', 'outage_syndicated_drift', C, 'utility_per_case', 0.0499),
            ('G8_rumor_no_net_harm', 'outage_shared_rumor', C, 'utility_per_case', 0.0999),
        ]
        for gate, regime, p, key, value in checks:
            fake = _passing_results(); fake[regime]['methods'][p][key] = value
            self.assertFalse(E.gates(fake)[gate], gate)
        for gate, regime, key, value in (('G9_alarm_recall', 'outage_midstream_drift', 'alarm_rate_from_step_180', 0.4999),
                                         ('G10_stable_false_alarm', 'outage_stable', 'alarm_rate_from_step_48', 0.2501),
                                         ('G7_healthy_no_change', 'healthy_midstream_drift', 'candidate_identical_to_conservative', False)):
            fake = _passing_results(); fake[regime][key] = value
            self.assertFalse(E.gates(fake)[gate], gate)

    def test_conservative_parameters_pinned_to_core_003(self):             # kills f10, f11
        seen, real = [], E.plan_adaptive
        def spy(*a, **k):
            seen.append((k['window_hours'], k['min_class_n'], k['mode'])); return real(*a, **k)
        E.plan_adaptive = spy
        try:
            E.plan(_view(), (), 'conservative')
        finally:
            E.plan_adaptive = real
        self.assertEqual(seen, [(72, 12, 'conservative')])

    # ---- generator fidelity --------------------------------------------------
    def test_drift_ramp(self):                                              # kills g5
        g = CFG['generator']
        r = 'outage_midstream_drift'
        self.assertEqual(E._quality(CFG, r, 'origin', 150), tuple(g['quality_stable']['origin']))
        self.assertEqual(E._quality(CFG, r, 'origin', 180), tuple(g['quality_degraded']['origin']))
        self.assertEqual(E._quality(CFG, 'outage_stable', 'origin', 239), tuple(g['quality_stable']['origin']))

    def test_raw_loss_drops_and_delays_after_outage(self):                  # kills g2
        n = 60; start = aware(CFG['generator']['start_time_utc']) + timedelta(hours=24)
        def post(regime):
            raws, _ = E.generate_background(CFG, regime, PILOT, n)
            return [r.vote for r in raws if aware(r.vote.observed_at) >= start]
        lossy, clean = post('outage_raw_loss_drift'), post('outage_midstream_drift')
        self.assertTrue(0.3 < len(lossy)/len(clean) < 0.5)
        delays = [(aware(v.available_at) - aware(v.observed_at)).total_seconds()/3600 for v in lossy]
        self.assertTrue(min(delays) >= 4 and max(delays) <= 20)

    def test_syndication_and_rumor_reach_current_case_probes(self):        # kills g3, g4
        r = 'outage_syndicated_drift'
        a = E.generate_cases(CFG, r, PILOT, 60)
        b = E.generate_cases(_cfg(r, pair_syndication=0.0), r, PILOT, 60)
        self.assertTrue(any(x.hidden_answers != y.hidden_answers for x, y in zip(a, b)))
        r = 'outage_shared_rumor'
        for t in E.generate_cases(_cfg(r, test_rumor=1.0), r, PILOT, 60):
            if not t.truth:
                ans = dict(t.hidden_answers)
                self.assertTrue(ans['cheap'] and ans['balanced'] and ans['deep'])
                self.assertTrue(all(s.supports for s in t.view.signals if s.publisher_root == 'origin'))


def _passing_results():
    """Fabricated per-regime results that pass every gate with a 0.0001 margin."""
    def methods(c, cons, fv, fa_c=0, fa_cons=0, fa_fv=1, mt_c=0, mt_cons=1):
        mk = lambda u, fa, mt: {'utility_per_case': u, 'utility_per_case_gross': u,
                                'false_assertions': fa, 'missed_true': mt}
        return {C: mk(c, fa_c, mt_c), 'conservative': mk(cons, fa_cons, mt_cons),
                'fixed_voi': mk(fv, fa_fv, 0), 'audit_age_only': mk(fv, fa_fv, 0), 'never': mk(0, 0, 9)}
    base = {'candidate_minus_fixed_voi': {'bootstrap_95': [0.001, 0.1]},
            'candidate_minus_conservative': {'bootstrap_95': [0.001, 0.1]},
            'candidate_identical_to_conservative': True,
            'alarm_rate_from_step_180': 0.5, 'alarm_rate_from_step_48': 0.25}
    res = {r: copy.deepcopy(base) for r in E.REGIMES}
    res['outage_midstream_drift']['methods'] = methods(0.125, 0.1, 0.1)
    res['outage_stable']['methods'] = methods(0.125, 0.1, 0.1)
    res['outage_raw_loss_drift']['methods'] = methods(0.09, 0.1, 0.1)
    res['outage_syndicated_drift']['methods'] = methods(0.05, 0.1, 0.1)
    res['outage_shared_rumor']['methods'] = methods(0.1, 0.1, 0.1)
    res['healthy_midstream_drift']['methods'] = methods(0.1, 0.1, 0.1)
    return res


if __name__ == '__main__':
    unittest.main()
