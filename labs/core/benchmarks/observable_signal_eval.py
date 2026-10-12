"""KEP-OBS-001: synthetic feasibility of OBSERVABLE audit-outage diagnostics.

No new KEP decision module and no source acquisition. Evaluates whether:
  A) age of the last completed independent audit, or
  B) that age plus recent RAW disagreements across two approved publisher roots
can help choose existing frozen CORE-003 strategies at decision time.

Current truth and prospective sensor answers NEVER enter policy input. Audit
truth can enter the existing CORE-003 calibrator only once adjudicated as-of.
Unreviewed observations are projected into a distinct type WITHOUT truth.
This study is a locked, separate synthetic holdout, NOT a production result.
"""
from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import datetime,timedelta
from pathlib import Path
from random import Random
from decimal import Decimal
import json

from kepcore.calibration import aware
from benchmarks.adaptive_trust_eval import (
    generate_chronological, choose as core003_choose,
    execute_preplanned, TIME,
)
from benchmarks.budgeted_core_eval import (
    View, Trial, summarize as summarize_budgeted,
    _paired as paired_budgeted,
)

PROTOCOL=Path(__file__).resolve().parents[1]/'benchmarks/observable_signal_protocol.json'
REGIMES=('stable_outage','abrupt_outage','gradual_outage',
         'healthy','late_reviews','correlated_rumor')
POLICIES=('conservative','fixed_voi','audit_age_only','unlabelled_disagreement')


@dataclass(frozen=True)
class ObservedVote:
    """Previously observable claim; intentionally NO source-truth label."""
    entity_id:str
    publisher_root:str
    observed_at:str
    supports:bool

    def __post_init__(self):
        aware(self.observed_at)
        if (not self.entity_id or not self.publisher_root or
                type(self.supports) is not bool):
            raise ValueError('Invalid simulated raw source observation')


@dataclass(frozen=True)
class ReviewPulse:
    """Finished independent audit timestamp, deliberately NO answer/outcome."""
    completed_at:str

    def __post_init__(self):
        aware(self.completed_at)


@dataclass(frozen=True)
class ObservableSnapshot:
    completed_audit_age_hours:float | None
    independent_pairs:int
    discordant_pairs:int
    pair_disagreement_rate:float | None
    flagged_deterioration:bool
    requested_sensor_check:bool
    no_ground_truth_in_input:bool=True


def protocol():
    d=json.loads(PROTOCOL.read_text(encoding='utf-8'))
    f=d.get('frozen_protocol',{})
    g=d.get('precommitted_gate',{})
    s=f.get('telemetry_signal',{})
    if (d.get('study')!='KEP-OBS-001'
        or d.get('stage')!='PREREGISTRATION_BEFORE_FEATURE_IMPLEMENTATION_OR_HOLDOUT'
        or d.get('data_scope')!='STRICTLY_SYNTHETIC_NO_REAL_SOURCE_RETRIEVAL'
        or f.get('seed')!=202610121015
        or f.get('cases_per_regime')!=160
        or f.get('regimes')!=list(REGIMES)
        or f.get('comparators')!=list(POLICIES)
        or f.get('paired_bootstrap_draws')!=200
        or f.get('feedback_outage_start_step')!=55
        or f.get('feedback_delay_after_outage_hours')!=100000
        or s.get('pair_of_publisher_roots')!=['origin','deep_root']
        or s.get('observed_vote_lookback_hours')!=12
        or s.get('min_distinct_entities')!=18
        or s.get('disagreement_cutoff_fraction')!=0.35
        or s.get('max_last_completed_review_age_hours')!=8
        or g.get('primary_regime')!='stable_outage'
        or g.get('minimum_utility_lift_over_conservative')!=0.025
        or g.get('minimum_utility_lift_over_audit_age_only')!=0
        or g.get('maximum_false_assertions_over_fixed_voi_in_stable')!=0
        or g.get('maximum_utility_regret_vs_conservative_for_each_degraded_regime')!=0.05
        or g.get('maximum_extra_false_assertions_vs_conservative_in_correlated_rumor')!=0
        or g.get('minimum_abrupt_drift_alert_recall_after_step_85')!=0.50
        or g.get('maximum_stable_outage_false_alert_rate_after_step_85')!=0.25):
        raise ValueError('Attempt to modify preregistered observable signal study')
    return d


def generate_holdout(regime:str,seed:int,n:int):
    """Reuse CORE-003 simulator with a NEW seed and explicitly missing labels.

    Raw published synthetic source assertions CONTINUE to arrive during
    independent audit-adjudication outages, an authored observability assumption.
    """
    if regime not in REGIMES or type(seed) is not int or type(n) is not int or not 1<=n<=300:
        raise ValueError('Unregistered synthetic regime or population')
    underlying={
      'stable_outage':'stable',
      'abrupt_outage':'abrupt_degradation',
      'gradual_outage':'gradual_degradation',
      'healthy':'stable',
      'late_reviews':'late_adjudication',
      'correlated_rumor':'correlated_failure',
    }[regime]
    trials,audits=generate_chronological(underlying,seed,n)
    if regime in ('stable_outage','abrupt_outage',
                  'gradual_outage','correlated_rumor'):
        start=TIME+timedelta(hours=55)
        next_audits=[]
        for audit in audits:
            if aware(audit.observed_at)>=start:
                delayed=aware(audit.observed_at)+timedelta(hours=100000)
                next_audits.append(replace(audit,adjudicated_at=delayed.isoformat()))
            else:
                next_audits.append(audit)
        audits=tuple(next_audits)
    return trials,audits


def project_at(audits,*,as_of:str):
    """Narrow independent synthetic audits into safe telemetry and past labels.

    DO NOT pass a raw AuditFeedback containing hidden truth to the
    observability feature model. Raw publisher SUPPORT can be observed earlier
    than independent adjudication, but its physical correctness cannot.
    """
    cutoff=aware(as_of)
    raw=[];pulse=[];completed=[]
    for a in audits:
        seen=aware(a.observed_at)
        verified=aware(a.adjudicated_at)
        if seen<=cutoff:
            raw.append(ObservedVote(a.entity_id,a.publisher_root,a.observed_at,a.supports))
        if verified<=cutoff:
            completed.append(a)
            pulse.append(ReviewPulse(a.adjudicated_at))
    return (tuple(completed),tuple(raw),tuple(pulse))


def observable_snapshot(raw_votes,review_pulses,*,as_of:str):
    """Identifiable from past publisher messages and completed audit CLOCKS.

    The pair sampling frame contains unique background entities only. Reposts
    from a publisher cannot increase evidence sample size; contradictory same
    clock signals are conservatively omitted, never treated as ground truth.
    """
    cfg=protocol()['frozen_protocol']['telemetry_signal']
    cutoff=aware(as_of)
    start=cutoff-timedelta(hours=cfg['observed_vote_lookback_hours'])
    pair=set(cfg['pair_of_publisher_roots'])
    latest=defaultdict(dict)
    for v in raw_votes:
        if type(v) is not ObservedVote:
            raise TypeError('No hidden labels or arbitrary event envelopes allowed')
        obs=aware(v.observed_at)
        if not start<=obs<=cutoff or v.publisher_root not in pair:
            continue
        target=latest[v.entity_id]
        previous=target.get(v.publisher_root)
        if previous is None or obs>previous[0]:
            target[v.publisher_root]=(obs,v.supports,False)
        elif obs==previous[0] and v.supports!=previous[1]:
            target[v.publisher_root]=(obs,v.supports,True)
    total=0;disagree=0
    a,b=cfg['pair_of_publisher_roots']
    for row in latest.values():
        if a not in row or b not in row:
            continue
        if row[a][2] or row[b][2]:
            continue
        total+=1
        disagree+=row[a][1]!=row[b][1]

    completed=[]
    for pulse in review_pulses:
        if type(pulse) is not ReviewPulse:
            raise TypeError('No private adjudication result can become telemetry')
        t=aware(pulse.completed_at)
        if t<=cutoff:
            completed.append(t)
    hours=(cutoff-max(completed)).total_seconds()/3600 if completed else None
    fraction=disagree/total if total>=cfg['min_distinct_entities'] else None
    # This alert never implies factual correctness or a verified source outage.
    old=hours is not None and hours>cfg['max_last_completed_review_age_hours']
    flagged=bool(old and fraction is not None
                 and fraction>cfg['disagreement_cutoff_fraction'])
    allow_check=bool(old and fraction is not None
                     and fraction<=cfg['disagreement_cutoff_fraction'])
    return ObservableSnapshot(
        completed_audit_age_hours=None if hours is None else round(hours,6),
        independent_pairs=total,
        discordant_pairs=disagree,
        pair_disagreement_rate=round(fraction,6) if fraction is not None else None,
        flagged_deterioration=flagged,
        requested_sensor_check=allow_check
    )


def choose_policy(view:View, completed_audits,raw_votes,review_pulses,policy:str):
    """Only existing CORE-003 strategies, never a new product decision module."""
    if type(view) is not View or policy not in POLICIES:
        raise TypeError('Policy inputs must be a truth-free View')
    feature=observable_snapshot(raw_votes,review_pulses,as_of=view.query.at)
    if policy in ('fixed_voi','conservative'):
        return core003_choose(view,completed_audits,policy),feature,policy
    if policy=='audit_age_only':
        healthy=feature.completed_audit_age_hours is not None and (
            feature.completed_audit_age_hours<=8)
        chosen='conservative' if healthy else 'fixed_voi'
    else:
        chosen='fixed_voi' if feature.requested_sensor_check else 'conservative'
    return core003_choose(view,completed_audits,chosen),feature,chosen


def _delta(aa,bb):
    return round(aa-bb,6)


def evaluate_gate(results,diagnostics,cfg):
    g=cfg['precommitted_gate']
    a=results['stable_outage']['methods']
    proposal=a['unlabelled_disagreement']
    base=a['conservative']
    age=a['audit_age_only']
    fixed=a['fixed_voi']
    conditions={
      'stable_lift_over_conservative':(
          _delta(proposal['utility_per_case'],base['utility_per_case'])>=
          g['minimum_utility_lift_over_conservative']),
      'stable_lift_over_audit_age_only':(
          _delta(proposal['utility_per_case'],age['utility_per_case'])>=
          g['minimum_utility_lift_over_audit_age_only']),
      'stable_false_assertions_no_more_than_fixed':(
          proposal['false_assertions']<=fixed['false_assertions']+
          g['maximum_false_assertions_over_fixed_voi_in_stable']),
      'abrupt_regret_vs_conservative':(
          _delta(results['abrupt_outage']['methods']['conservative']['utility_per_case'],
                 results['abrupt_outage']['methods']['unlabelled_disagreement']['utility_per_case'])
          <=g['maximum_utility_regret_vs_conservative_for_each_degraded_regime']),
      'gradual_regret_vs_conservative':(
          _delta(results['gradual_outage']['methods']['conservative']['utility_per_case'],
                 results['gradual_outage']['methods']['unlabelled_disagreement']['utility_per_case'])
          <=g['maximum_utility_regret_vs_conservative_for_each_degraded_regime']),
      'correlated_false_assertions_no_increase':(
          results['correlated_rumor']['methods']['unlabelled_disagreement']['false_assertions']
          <=results['correlated_rumor']['methods']['conservative']['false_assertions']+
          g['maximum_extra_false_assertions_vs_conservative_in_correlated_rumor']),
      'abrupt_alert_recall':(
          diagnostics['abrupt_outage']['flagged_fraction_after_85'] is not None
          and diagnostics['abrupt_outage']['flagged_fraction_after_85']>=
          g['minimum_abrupt_drift_alert_recall_after_step_85']),
      'stable_false_alert_frequency':(
          diagnostics['stable_outage']['flagged_fraction_after_85'] is not None
          and diagnostics['stable_outage']['flagged_fraction_after_85']<=
          g['maximum_stable_outage_false_alert_rate_after_step_85']),
    }
    return {
      'decision':'GO_FOR_FURTHER_RESEARCH_ONLY' if all(conditions.values()) else 'NO_GO',
      'precommitted_checks':conditions,
      'failed_checks':sorted(k for k,v in conditions.items() if not v),
      'protocol_was_frozen_before_first_holdout':True,
      'acceptance_does_not_authorize_production':True
    }


def run():
    cfg=protocol()
    ex=cfg['frozen_protocol']
    outputs={}; diagnostics={}
    for ri,regime in enumerate(REGIMES):
        trials,audit_stream=generate_holdout(
            regime,ex['seed']+ri,ex['cases_per_regime'])
        outcomes={policy:[] for policy in POLICIES}
        feature_samples=[]
        chosen_counts={name:defaultdict(int) for name in POLICIES}
        for index,trial in enumerate(trials):
            asof=trial.view.query.at
            completed,votes,pulses=project_at(audit_stream,as_of=asof)
            for policy in POLICIES:
                proposal,features,chosen=choose_policy(
                    trial.view,completed,votes,pulses,policy)
                chosen_counts[policy][chosen]+=1
                if proposal.consumer_publish or proposal.authorized_to_fetch:
                    raise AssertionError('Observability experiment attempted external action')
                outcomes[policy].append(execute_preplanned(trial,proposal))
            if index>=85:
                feature_samples.append(features)
        methods={policy:summarize_budgeted(trials,outcomes[policy],
                     ex['false_assertion_penalty']) for policy in POLICIES}
        outputs[regime]={
            'methods':methods,
            'chosen_strategy_counts':{
                 key:dict(sorted(val.items())) for key,val in chosen_counts.items()},
            'paired_observable_minus_conservative':paired_budgeted(
                 trials,outcomes['unlabelled_disagreement'],outcomes['conservative'],
                 ex['false_assertion_penalty'],
                 seed=ex['seed']+ri+7100,draws=ex['paired_bootstrap_draws'])
        }
        diagnostics[regime]={
            'cases_after_step_85':len(feature_samples),
            'observable_pairs_min':min(s.independent_pairs for s in feature_samples),
            'observable_pairs_max':max(s.independent_pairs for s in feature_samples),
            'flagged_count_after_85':sum(s.flagged_deterioration for s in feature_samples),
            'flagged_fraction_after_85':round(
                sum(s.flagged_deterioration for s in feature_samples)/len(feature_samples),6),
            'most_recent_audit_age_1st_after_85':
                 feature_samples[0].completed_audit_age_hours,
            'most_recent_audit_age_last_after_85':
                 feature_samples[-1].completed_audit_age_hours,
        }
    return {
        'study':'KEP-OBS-001',
        'data_origin':'SYNTHETIC_PAST_RAW_VOTES_AND_AUDIT_HEARTBEATS_ONLY',
        'regimes':outputs,
        'observable_signal_diagnostics':diagnostics,
        'acceptance':evaluate_gate(outputs,diagnostics,cfg),
        'protocol':cfg,
        'real_world_sensor_calibration':False,
        'new_real_data_downloads':0,
        'external_model_calls':0,
        'real_human_labels_used':0,
        'consumer_publish':False,
        'hidden_test_truth_visible_to_policy':False,
        'future_audit_answers_visible_to_policy':False,
        'limitations':('Unlabelled publisher disagreement is an invented-world '
            'proxy. Raw claim observations continue during audit-adjudication '
            'outages by simulator assumption. Correlated false claims can agree '
            'and therefore defeat the proxy. No actual venue truth is proven.')
    }


if __name__=='__main__':
    print(json.dumps(run(),sort_keys=True,ensure_ascii=False,indent=2))
