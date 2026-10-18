"""KEP-OBS-002: second, independently generated synthetic test of the OBS-001
unlabelled-disagreement selector. Research only; nothing here ships to Core.

The generator is NEW (not CORE-002/003 case generation). It varies raw vote
delivery loss, upstream syndication between the telemetry pair, drift that
starts in the middle of a review outage, and charges telemetry overhead.

Policy inputs are the truth-free View, truth-free ObservedVote rows that were
DELIVERED by the decision time, and the latest completed review timestamp.
Truth and hidden probe answers reach only the executor. No network, no real
labels, no model calls, no publishing.

Frozen protocol: benchmarks/obs_002_protocol.json (SHA-256 pinned below).
"""
from __future__ import annotations
from dataclasses import dataclass, fields, replace
from datetime import datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from random import Random
import argparse
import copy
import json
import sys

from kepcore.calibration import aware
from kepcore.core import Query, load_catalog
from kepcore.evidence_lab import EvidenceChannel
from kepcore.temporal_pipeline import Signal
from kepcore.adaptive_trust import AuditFeedback, plan_adaptive
from kepcore.budgeted_verify import plan_research
from benchmarks.budgeted_core_eval import (
    View, Trial, ROOTS, _check_options, _case_value, _rounded6)
from benchmarks.adaptive_trust_eval import execute_preplanned

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT/'benchmarks/obs_002_protocol.json'
PROTOCOL_SHA256 = 'e8445240f230cec8377441b88aefd92d26d4c931ee78bc3ed844e7236e8423fe'

REGIMES = ('outage_stable', 'outage_midstream_drift', 'outage_syndicated_drift',
           'outage_raw_loss_drift', 'healthy_midstream_drift', 'outage_shared_rumor')
POLICIES = ('never', 'conservative', 'fixed_voi', 'audit_age_only',
            'unlabelled_disagreement')
CANDIDATE = 'unlabelled_disagreement'
MODEL_ROOTS = ('balanced_root', 'cheap_root', 'deep_root', 'origin')
PAIR = ('origin', 'deep_root')
PROBE_ROOT = {'cheap': 'cheap_root', 'balanced': 'balanced_root', 'deep': 'deep_root'}

# Candidate rule, unchanged from OBS-001 and frozen in the protocol.
LOOKBACK_HOURS = 12
MIN_ENTITIES = 18
CUTOFF = 0.35
MAX_REVIEW_AGE_HOURS = 8
TELEMETRY_COST = Decimal('0.004')


def load_protocol(path: Path = PROTOCOL) -> dict:
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != PROTOCOL_SHA256:
        raise ValueError('OBS-002 protocol differs from the frozen preregistration')
    cfg = json.loads(raw)
    rule = cfg['candidate_rule_unchanged_from_obs_001']
    if (tuple(cfg['generator']['regimes']) != REGIMES or tuple(cfg['policies']) != POLICIES
            or tuple(rule['pair_of_publisher_roots']) != PAIR
            or rule['observed_vote_lookback_hours'] != LOOKBACK_HOURS
            or rule['min_distinct_entities'] != MIN_ENTITIES
            or rule['disagreement_cutoff_fraction'] != CUTOFF
            or rule['max_last_completed_review_age_hours'] != MAX_REVIEW_AGE_HOURS
            or Decimal(str(cfg['accounting']['telemetry_cost_per_decision_reading_pairs']))
            != TELEMETRY_COST):
        raise ValueError('Evaluator constants do not match the frozen protocol')
    return cfg


# ---------------------------------------------------------------- policy view

@dataclass(frozen=True)
class ObservedVote:
    """A delivered raw publisher claim. Deliberately has NO truth field."""
    root: str
    entity_id: str
    observed_at: str
    available_at: str
    supports: bool


@dataclass(frozen=True)
class ReviewPulse:
    """Only WHEN the last independent review finished, never its outcome."""
    last_completed_at: str | None


@dataclass(frozen=True)
class Telemetry:
    read: bool
    pairs: int | None
    disagreement: float | None
    alarm: bool


def pair_disagreement(votes, *, as_of: str, exclude_entity: str) -> tuple[int, float | None]:
    cutoff = aware(as_of)
    start = cutoff - timedelta(hours=LOOKBACK_HOURS)
    latest = {}
    for v in votes:
        if type(v) is not ObservedVote:
            raise TypeError('Selector accepts only truth-free ObservedVote rows')
        if v.entity_id == exclude_entity:
            raise ValueError('Current case cannot feed its own telemetry')
        if v.root not in PAIR:
            continue
        seen, got = aware(v.observed_at), aware(v.available_at)
        if got > cutoff or seen > cutoff or seen < start:
            continue
        key = (v.root, v.entity_id)
        if key not in latest or seen > latest[key][0]:
            latest[key] = (seen, v.supports)
    entities = sorted({e for r, e in latest if r == PAIR[0]} &
                      {e for r, e in latest if r == PAIR[1]})
    if len(entities) < MIN_ENTITIES:
        return len(entities), None
    mismatch = sum(latest[(PAIR[0], e)][1] != latest[(PAIR[1], e)][1] for e in entities)
    return len(entities), mismatch/len(entities)


def select_mode(view: View, votes, pulse: ReviewPulse, mode: str) -> tuple[str, Telemetry]:
    """Map audit_age_only / unlabelled_disagreement onto an existing policy."""
    if type(view) is not View or type(pulse) is not ReviewPulse:
        raise TypeError('Only truth-free policy inputs are accepted')
    none = Telemetry(False, None, None, False)
    if mode not in ('audit_age_only', CANDIDATE):
        raise ValueError('Unknown selector')
    as_of = aware(view.query.at)
    if pulse.last_completed_at is None:
        return 'conservative', none
    age = as_of - aware(pulse.last_completed_at)
    if age < timedelta(0):
        raise ValueError('Review pulse from the future')
    if age <= timedelta(hours=MAX_REVIEW_AGE_HOURS):
        return 'conservative', none
    if mode == 'audit_age_only':
        return 'fixed_voi', none
    n, frac = pair_disagreement(votes, as_of=view.query.at, exclude_entity=view.record['id'])
    if frac is None:
        return 'conservative', Telemetry(True, n, None, False)
    alarm = frac > CUTOFF
    return ('conservative' if alarm else 'fixed_voi'), Telemetry(True, n, round(frac, 6), alarm)


def plan(view: View, audits, mode: str):
    kw = dict(observed_channels=view.observed_sources, approved_roots=view.approved_roots,
              prior=view.prior, budget=view.budget, max_wait_minutes=view.max_wait_minutes)
    if mode in ('never', 'fixed_voi'):
        return plan_research([view.record], view.query, view.signals, view.probes,
                             policy={'never': 'never', 'fixed_voi': 'voi'}[mode], **kw)
    if mode == 'conservative':
        return plan_adaptive([view.record], view.query, view.signals, view.probes,
                             audits=list(audits), mode='conservative',
                             window_hours=72, min_class_n=12, **kw)
    raise ValueError('Unknown base policy')


# ------------------------------------------------------------------ generator

def _quality(cfg: dict, regime: str, root: str, step: float) -> tuple[float, float]:
    g = cfg['generator']
    stable = tuple(g['quality_stable'][root])
    onset = g['regimes'][regime]['drift_onset_step']
    if onset is None or step < onset:
        return stable
    alpha = min(1.0, (step - onset)/g['drift_ramp_hours'])
    degraded = tuple(g['quality_degraded'][root])
    return tuple(s*(1-alpha) + d*alpha for s, d in zip(stable, degraded))


def _draw(truth: bool, rates, rng: Random) -> bool:
    return rng.random() < (rates[0] if truth else 1 - rates[1])


@dataclass(frozen=True)
class RawVote:
    """Executor-side background record; truth is kept for audits only."""
    vote: ObservedVote
    truth: bool


def generate_background(cfg: dict, regime: str, seed: int, n: int):
    g = cfg['generator']; b = g['background_stream']; r = g['regimes'][regime]
    start = aware(g['start_time_utc'])
    rng = Random(f'obs002:{seed}:{regime}:background')
    outage = r['outage_start_step']
    outage_at = None if outage is None else start + timedelta(hours=outage)
    lo_min, hi_min = b['normal_delivery_delay_minutes_uniform']
    raws, audits = [], []
    for hour in range(-g['warmup_hours_before_first_case'], n):
        for j in range(b['entities_per_hour']):
            entity = f'synthetic:obs002-background:{regime}:{seed}:{hour}:{j}'
            truth = rng.random() < b['background_truth_rate']
            observed = start + timedelta(hours=hour, minutes=rng.randrange(60))
            upstream = _draw(truth, _quality(cfg, regime, 'origin', hour), rng)
            syndicated = rng.random() < r['pair_syndication']
            for root in MODEL_ROOTS:
                if root == 'origin':
                    answer = upstream
                elif root == 'deep_root' and syndicated:
                    answer = upstream
                else:
                    answer = _draw(truth, _quality(cfg, regime, root, hour), rng)
                if rng.random() >= b['per_root_observation_probability']:
                    continue
                lossy = r['raw_loss'] and outage_at is not None and observed >= outage_at
                if lossy:
                    if rng.random() < 0.6:
                        continue
                    delay = timedelta(hours=rng.uniform(4, 20))
                else:
                    delay = timedelta(minutes=rng.uniform(lo_min, hi_min))
                vote = ObservedVote(root, entity, observed.isoformat(),
                                    (observed + delay).isoformat(), answer)
                raws.append(RawVote(vote, truth))
                adjudicated = observed + timedelta(hours=b['audit_adjudication_delay_hours_when_healthy'])
                if outage_at is not None and adjudicated >= outage_at:
                    continue
                if observed + delay > adjudicated:
                    continue  # only delivered votes are audited
                audits.append(AuditFeedback(
                    audit_id=f'obs002-audit:{regime}:{seed}:{hour}:{j}:{root}',
                    entity_id=entity, publisher_root=root,
                    observed_at=observed.isoformat(), adjudicated_at=adjudicated.isoformat(),
                    supports=answer, truth=truth))
    return tuple(raws), tuple(audits)


def generate_cases(cfg: dict, regime: str, seed: int, n: int) -> list[Trial]:
    g = cfg['generator']; r = g['regimes'][regime]; s = g['test_case_signals']
    start = aware(g['start_time_utc'])
    rng = Random(f'obs002:{seed}:{regime}:cases')
    base = next(x for x in load_catalog() if x['kind'] == 'place' and x['city'] == 'İstanbul')
    options = _check_options()
    source_model = EvidenceChannel('source', 'origin', *g['quality_stable']['origin'], 0., True, True)
    trials = []
    for i in range(n):
        at = start + timedelta(hours=i)
        truth = rng.random() < g['test_truth_rate']
        record = copy.deepcopy(base)
        record.update(
            id=f'synthetic:obs002:{regime}:{seed}:{i}',
            source_url='synthetic://obs002-created-in-memory',
            source_id='obs002_synthetic_fixture', publisher_root='synthetic_source',
            source_record_hash=sha256(f'obs002/{regime}/{seed}/{i}'.encode()).hexdigest(),
            synthetic=True, rights_scope='open_attribution')
        claim = _draw(truth, _quality(cfg, regime, 'origin', i), rng)
        rumor = (not truth) and rng.random() < r['test_rumor']
        if rumor:
            claim = True
        events = []
        def emit(name, root, yes, minutes_before):
            t = (at - timedelta(minutes=minutes_before)).isoformat()
            events.append(Signal(name, record['id'], root, t, t, yes, 'research_ingest'))
        emit(f'obs002-origin:{i}', 'origin', claim, 90)
        for k in range(rng.randrange(4)):
            emit(f'obs002-repost:{i}:{k}', 'origin', claim, 90)
        if rng.random() < 0.08:
            emit(f'obs002-second:{i}', 'balanced_root',
                 _draw(truth, _quality(cfg, regime, 'balanced_root', i), rng), 60)
        if rng.random() < 0.04:
            emit(f'obs002-negative:{i}', 'cheap_root', False, 45)
        answers = {key: _draw(truth, _quality(cfg, regime, root, i), rng)
                   for key, root in PROBE_ROOT.items()}
        if rng.random() < r['pair_syndication']:
            answers['deep'] = claim
        if rumor:
            answers.update(cheap=True, balanced=True, deep=True)
        answers['mirror'] = truth
        answers['unlicensed'] = truth
        q = Query(city='İstanbul', kind='place', at=at.isoformat(), limit=1)
        view = View(record, q, tuple(events), options, (source_model,), ROOTS,
                    g['prior'], g['budget'], g['max_wait_minutes'])
        trials.append(Trial(truth, view, tuple(sorted(answers.items()))))
    return trials


def policy_inputs(view: View, raws, audits):
    """Executor-side causal filter; returns only what a policy may see."""
    as_of = aware(view.query.at)
    done = [a for a in audits if aware(a.adjudicated_at) <= as_of]
    pulse = ReviewPulse(max((a.adjudicated_at for a in done), key=aware) if done else None)
    votes = tuple(rv.vote for rv in raws if aware(rv.vote.available_at) <= as_of)
    return tuple(done), votes, pulse


# ----------------------------------------------------------------- evaluation

def _value(trial, out, penalty) -> Decimal:
    return _case_value(trial, out, penalty) - out['telemetry_cost']


def _summary(trials, outs, penalty) -> dict:
    n = len(trials)
    total = sum((_value(t, o, penalty) for t, o in zip(trials, outs)), Decimal('0'))
    gross = sum((_case_value(t, o, penalty) for t, o in zip(trials, outs)), Decimal('0'))
    return {
        'cases': n,
        'assertions': sum(o['accepted'] for o in outs),
        'correct_assertions': sum(o['correct_assertion'] for o in outs),
        'false_assertions': sum(o['false_assertion'] for o in outs),
        'missed_true': sum(t.truth and not o['accepted'] for t, o in zip(trials, outs)),
        'checks': sum(o['checked'] for o in outs),
        'telemetry_reads': sum(o['telemetry_cost'] > 0 for o in outs),
        'utility_per_case_gross': _rounded6(gross/Decimal(n)),
        'utility_per_case': _rounded6(total/Decimal(n)),
    }


def _paired(trials, a, b, penalty, seed, draws) -> dict:
    diff = [_value(t, x, penalty) - _value(t, y, penalty) for t, x, y in zip(trials, a, b)]
    rng = Random(seed)
    sims = sorted(sum(rng.choices(diff, k=len(diff)), Decimal('0'))/Decimal(len(diff))
                  for _ in range(draws))
    return {'mean': _rounded6(sum(diff, Decimal('0'))/Decimal(len(diff))),
            'bootstrap_95': [_rounded6(sims[int(.025*draws)]),
                             _rounded6(sims[min(draws-1, int(.975*draws))])]}


def run_regime(cfg: dict, regime: str, seed: int, n: int, draws: int, boot_seed: int) -> dict:
    penalty = cfg['accounting']['false_assertion_penalty']
    trials = generate_cases(cfg, regime, seed, n)
    raws, audits = generate_background(cfg, regime, seed, n)
    case_ids = {t.view.record['id'] for t in trials}
    if case_ids & {rv.vote.entity_id for rv in raws}:
        raise AssertionError('Background telemetry overlaps current cases')
    outs = {p: [] for p in POLICIES}
    proposals = {p: [] for p in POLICIES}
    tele = []
    for step, trial in enumerate(trials):
        done, votes, pulse = policy_inputs(trial.view, raws, audits)
        cache = {}
        def base(mode):
            if mode not in cache:
                cache[mode] = plan(trial.view, done, mode)
            return cache[mode]
        for p in POLICIES:
            info = Telemetry(False, None, None, False)
            if p in ('never', 'conservative', 'fixed_voi'):
                decision = base(p)
            else:
                mode, info = select_mode(trial.view, votes, pulse, p)
                decision = base(mode)
            out = execute_preplanned(trial, decision)
            out['telemetry_cost'] = TELEMETRY_COST if info.read else Decimal('0')
            outs[p].append(out)
            proposals[p].append((decision.action, decision.probe_id))
            if p == CANDIDATE:
                tele.append({'step': step, **info.__dict__})
    methods = {p: _summary(trials, outs[p], penalty) for p in POLICIES}
    def alarm_rate(first):
        rows = [x for x in tele if x['step'] >= first]
        return round(sum(x['alarm'] for x in rows)/len(rows), 6) if rows else None
    gain = methods[CANDIDATE]['utility_per_case_gross'] - methods['conservative']['utility_per_case']
    reads = methods[CANDIDATE]['telemetry_reads']
    return {
        'methods': methods,
        'candidate_minus_fixed_voi': _paired(trials, outs[CANDIDATE], outs['fixed_voi'],
                                             penalty, boot_seed, draws),
        'candidate_minus_conservative': _paired(trials, outs[CANDIDATE], outs['conservative'],
                                                penalty, boot_seed + 1, draws),
        'candidate_identical_to_conservative': proposals[CANDIDATE] == proposals['conservative'],
        'candidate_identical_to_audit_age_only': proposals[CANDIDATE] == proposals['audit_age_only'],
        # D1 transparency: the pre-D1 (action-only) reading is reported too.
        'action_only_identical_to_conservative': [a for a, _ in proposals[CANDIDATE]]
            == [a for a, _ in proposals['conservative']],
        'action_only_identical_to_audit_age_only': [a for a, _ in proposals[CANDIDATE]]
            == [a for a, _ in proposals['audit_age_only']],
        'candidate_proposals_differ_from_conservative': sum(
            a != b for a, b in zip(proposals[CANDIDATE], proposals['conservative'])),
        'candidate_proposals_differ_from_audit_age_only': sum(
            a != b for a, b in zip(proposals[CANDIDATE], proposals['audit_age_only'])),
        'insufficient_pair_decisions': sum(x['read'] and x['pairs'] is not None
                                           and x['disagreement'] is None for x in tele),
        'mean_pairs_when_read': (round(sum(x['pairs'] for x in tele if x['read'])/reads, 3)
                                 if reads else None),
        'alarm_rate_from_step_48': alarm_rate(48),
        'alarm_rate_from_step_180': alarm_rate(180),
        'extra_false_assertions_vs_conservative': (methods[CANDIDATE]['false_assertions']
                                                   - methods['conservative']['false_assertions']),
        'break_even_telemetry_cost': (round(gain/reads*n, 6) if reads else None),
        'background_votes': len(raws), 'background_audits': len(audits),
    }


def gates(res: dict) -> dict:
    m = lambda r, p, k: res[r]['methods'][p][k]
    u = lambda r, p: m(r, p, 'utility_per_case')
    P, S, Y, L, H, R = REGIMES[1], REGIMES[0], REGIMES[2], REGIMES[3], REGIMES[4], REGIMES[5]
    C = CANDIDATE
    eps = 1e-9
    return {
        'G1_primary_beats_both': (u(P, C) - u(P, 'fixed_voi') >= 0.025 - eps and
                                  u(P, C) - u(P, 'conservative') >= 0.025 - eps),
        'G2_primary_paired_interval': (res[P]['candidate_minus_fixed_voi']['bootstrap_95'][0] > 0 and
                                       res[P]['candidate_minus_conservative']['bootstrap_95'][0] > 0),
        'G3_distinct_mistakes_avoided': (m(P, C, 'false_assertions') < m(P, 'fixed_voi', 'false_assertions') and
                                         m(P, C, 'missed_true') < m(P, 'conservative', 'missed_true')),
        'G4_stable_recovery': (u(S, C) - u(S, 'conservative') >= 0.025 - eps and
                               m(S, C, 'false_assertions') <= m(S, 'fixed_voi', 'false_assertions')),
        'G5_raw_loss_safe_fallback': (u(L, 'conservative') - u(L, C) <= 0.01 + eps and
                                      m(L, C, 'false_assertions') <= m(L, 'conservative', 'false_assertions')),
        'G6_syndication_harm_cap': u(Y, 'conservative') - u(Y, C) <= 0.05 + eps,
        'G7_healthy_no_change': res[H]['candidate_identical_to_conservative'],
        'G8_rumor_no_net_harm': (u(R, C) >= u(R, 'conservative') - eps and
                                 m(R, C, 'false_assertions') <= m(R, 'fixed_voi', 'false_assertions')),
        # D2: missing alarm data fails a gate instead of passing it.
        'G9_alarm_recall': res[P]['alarm_rate_from_step_180'] is not None and
                           res[P]['alarm_rate_from_step_180'] >= 0.5,
        'G10_stable_false_alarm': res[S]['alarm_rate_from_step_48'] is not None and
                                  res[S]['alarm_rate_from_step_48'] <= 0.25,
    }


def run(stage: str, cfg: dict | None = None, *, _guarded: bool = False) -> dict:
    if stage == 'holdout' and not _guarded:
        raise PermissionError('Holdout runs only through the guarded CLI, once')
    cfg = load_protocol() if cfg is None else cfg
    block = cfg['frozen_holdout'] if stage == 'holdout' else cfg['pilot']
    if stage not in ('pilot', 'holdout'):
        raise ValueError('Unknown stage')
    seed, n = block['seed'], block['cases_per_regime']
    draws = cfg['accounting']['paired_bootstrap_draws']
    off = cfg['accounting']['bootstrap_seed_offset']
    results = {regime: run_regime(cfg, regime, seed + i, n, draws, seed + i + off)
               for i, regime in enumerate(REGIMES)}
    g = gates(results)
    discriminating = not all(r['candidate_identical_to_conservative'] and
                             r['candidate_identical_to_audit_age_only']
                             for r in results.values())
    discriminating_action_only = not all(r['action_only_identical_to_conservative'] and
                                         r['action_only_identical_to_audit_age_only']
                                         for r in results.values())
    telemetry_changed_a_decision = not all(r['candidate_identical_to_audit_age_only']
                                           for r in results.values())
    if stage == 'pilot':
        verdict = 'PILOT_ONLY_NOT_EVIDENCE' if discriminating else 'NO_GO_NOT_DISCRIMINATING'
    else:
        verdict = 'GO_FOR_FURTHER_RESEARCH_ONLY' if all(g.values()) else 'NO_GO'
    return {
        'study': 'KEP-OBS-002', 'stage': stage, 'seed': seed, 'cases_per_regime': n,
        'protocol_sha256': PROTOCOL_SHA256, 'verdict': verdict,
        'discriminating': discriminating,
        'discriminating_action_only_pre_d1': discriminating_action_only,
        'telemetry_changed_any_decision_vs_audit_age_only': telemetry_changed_a_decision,
        'gates': g,
        'gates_passed': sum(g.values()), 'gates_failed': len(g) - sum(g.values()),
        'results': results,
        'fail_safe_boundaries': {'real_human_reviews': 0, 'source_downloads': 0,
                                 'model_calls': 0, 'consumer_publish': False,
                                 'real_business_accuracy': None},
    }


def source_hashes() -> dict:
    files = ['benchmarks/obs_002_eval.py', 'benchmarks/obs_002_protocol.json',
             'benchmarks/budgeted_core_eval.py', 'benchmarks/adaptive_trust_eval.py',
             'kepcore/adaptive_trust.py', 'kepcore/budgeted_verify.py',
             'kepcore/temporal_pipeline.py', 'kepcore/core.py', 'kepcore/evidence_lab.py',
             'tests/test_obs_002_eval.py', 'tests/test_obs_002_audit.py']
    return {f: sha256((ROOT/f).read_bytes()).hexdigest() for f in files}


def _holdout_guard(commit: str, out_path: Path) -> None:
    import subprocess
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, check=True,
                          capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(['git', 'status', '--porcelain', '--', '.'], cwd=ROOT, check=True,
                           capture_output=True, text=True).stdout.strip()
    if commit != head or dirty:
        sys.exit('Holdout refused: audited commit must equal a clean HEAD')
    if out_path.exists():
        sys.exit('Holdout refused: it has already been run once')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--stage', choices=('pilot', 'holdout'), default='pilot')
    ap.add_argument('--confirm-audited-evaluator-commit', default=None,
                    help='Required for holdout: the audited evaluator commit SHA')
    a = ap.parse_args()
    if a.stage == 'holdout' and not a.confirm_audited_evaluator_commit:
        sys.exit('Holdout runs once, only after the independent audit; pass the audited commit SHA')
    once = ROOT/'reports/KEP_OBS_002_HOLDOUT_FULL.json'
    if a.stage == 'holdout':
        _holdout_guard(a.confirm_audited_evaluator_commit, once)
    out = run(a.stage, _guarded=a.stage == 'holdout')
    out['source_sha256'] = source_hashes()
    if a.stage == 'holdout':
        out['audited_evaluator_commit'] = a.confirm_audited_evaluator_commit
    text = json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True)
    if a.stage == 'holdout':
        with open(once, 'x', encoding='utf-8') as fh:  # O_EXCL: a second run fails
            fh.write(text + '\n')
    print(text)
