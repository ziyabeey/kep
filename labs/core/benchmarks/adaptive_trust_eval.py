"""CORE-003 independent-audit synthetic benchmark, strict chronological evaluation.

Source truth is from hand-authored fictional simulator only. Every independent
audit concerns a DIFFERENT synthetic background case, not the current trial.
Only audits adjudicated before the decision enter the planner. All methods
see the same hidden case, prospective answers, clock, rights and deadline.

No real dataset acquisition, network calls, field labels, or model requests.
"""
from __future__ import annotations
from dataclasses import replace
from datetime import datetime,timedelta
from decimal import Decimal
from pathlib import Path
from random import Random
import json
import math

from kepcore.calibration import aware
from kepcore.temporal_pipeline import Signal,run_pipeline
from kepcore.adaptive_trust import AuditFeedback,plan_adaptive
from kepcore.budgeted_verify import plan_research
from benchmarks.budgeted_core_eval import (
    View,Trial,generate,TIME,SOURCE_MODEL,ROOTS,
    summarize as summarize_budgeted,_paired as paired_budgeted,
)

ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/'benchmarks/adaptive_trust_protocol.json'
REGIMES=('stable','abrupt_degradation','gradual_degradation',
         'late_adjudication','audit_outage','correlated_failure')
POLICIES=('never','fixed_voi','cheapest','posterior_mean','conservative')
QUALITY={
    'origin':(.88,.82),
    'cheap_root':(.74,.72),
    'balanced_root':(.88,.86),
    'deep_root':(.97,.95),
}
DEGRADED={
    'origin':(.57,.56),
    'cheap_root':(.55,.54),
    'balanced_root':(.56,.55),
    'deep_root':(.58,.56),
}
MODEL_ROOTS=tuple(sorted(QUALITY))
WARMUP_HOURS=72
BACKGROUND_AUDITS_PER_HOUR=3
OUTAGE_AT_STEP=55


def _quality(root:str,regime:str,step:int)->tuple[float,float]:
    stable=QUALITY[root]
    degraded=DEGRADED[root]
    if regime=='abrupt_degradation' and step>=60:
        return degraded
    if regime=='gradual_degradation' and step>=0:
        alpha=min(1.,step/130)
        return tuple(s*(1-alpha)+d*alpha for s,d in zip(stable,degraded))
    return stable


def _draw(truth:bool,rates:tuple[float,float],rng:Random)->bool:
    sensitivity,specificity=rates
    return rng.random() < (sensitivity if truth else (1.-specificity))


def _shift_sources(view:View,delta:timedelta,truth:bool,rng:Random,
                   regime:str,step:int)->tuple[Signal,...]:
    """Remap existing CORE-002 signals to a new decision time."""
    by_root={}
    for root in ('origin','balanced_root','cheap_root'):
        by_root[root]=_draw(truth,_quality(root,regime,step),rng)
    if regime=='correlated_failure' and not truth and rng.random()<.37:
        # Publisher roots can share one upstream bad rumor. This violates the
        # statistical independence assumptions of the Core corroboration rule.
        for root in by_root:
            by_root[root]=True
    signals=[]
    for event in view.signals:
        observed=aware(event.observed_at)+delta
        available=aware(event.available_at)+delta
        answer=event.supports
        if event.publisher_root in by_root:
            answer=by_root[event.publisher_root]
        signals.append(replace(event,observed_at=observed.isoformat(),
                  available_at=available.isoformat(),supports=answer))
    return tuple(signals)


def _background_audits(regime:str,seed:int,test_cases:int)->tuple[AuditFeedback,...]:
    """Unselected independent audit stream with predetermined label delay.

    The *current test case* never appears here. Each publisher root is
    evaluated on its own sample of independently labeled fictional worlds.
    """
    rng=Random(seed+734_331)
    audit=[]
    for hour in range(-WARMUP_HOURS,test_cases):
        observation_time=TIME+timedelta(hours=hour)
        adjudication_hours=24 if regime=='late_adjudication' else 3
        if regime=='audit_outage' and hour>=OUTAGE_AT_STEP:
            adjudication_hours=100_000  # definitely not available in horizon
        for j in range(BACKGROUND_AUDITS_PER_HOUR):
            truth=rng.random()<.55
            for root in MODEL_ROOTS:
                answer=_draw(truth,_quality(root,regime,hour),rng)
                audit.append(AuditFeedback(
                    audit_id=f'audit-{regime}-{hour}-{j}-{root}',
                    entity_id=f'synthetic:independent-background:{regime}:{hour}:{j}',
                    publisher_root=root,
                    observed_at=observation_time.isoformat(),
                    adjudicated_at=(observation_time+
                        timedelta(hours=adjudication_hours)).isoformat(),
                    supports=answer,truth=truth,
                ))
    return tuple(audit)


def generate_chronological(regime:str,seed:int,n:int):
    """Return evaluation-only trials and independent historical audit stream."""
    if regime not in REGIMES or type(seed) is not int or type(n) is not int or not 1<=n<=500:
        raise ValueError('Unreviewed synthetic regime or scenario population')
    original=generate('matched',seed,n)
    rng=Random(seed+3_000_003)
    trials=[]
    for i,case in enumerate(original):
        v=case.view
        delta=timedelta(hours=i)
        query=replace(v.query,at=(aware(v.query.at)+delta).isoformat())
        signals=_shift_sources(v,delta,case.truth,rng,regime,i)
        answers={}
        for option in v.probes:
            id=option.channel.id
            if option.channel.publisher_root in QUALITY:
                answers[id]=_draw(case.truth,_quality(option.channel.publisher_root,regime,i),rng)
            else:
                answers[id]=case.truth  # inaccessible same-root/unapproved fake probe
        if regime=='correlated_failure' and not case.truth and rng.random()<.37:
            # Independent URLs in the source graph may share correlated origin.
            for key in ('cheap','balanced','deep'):
                answers[key]=True
        trials.append(Trial(case.truth,replace(v,query=query,signals=signals),
                            tuple(sorted(answers.items()))))
    return trials,_background_audits(regime,seed,n)


def choose(view:View,audits,mode:str):
    """Pure policy input: no trial.truth and no hidden prospective answers."""
    if type(view) is not View or mode not in POLICIES:
        raise ValueError('Only predeclared policy-visible scenario accepted')
    kw=dict(observed_channels=view.observed_sources,
            approved_roots=view.approved_roots,
            prior=view.prior,budget=view.budget,
            max_wait_minutes=view.max_wait_minutes)
    if mode in ('never','cheapest','fixed_voi'):
        return plan_research([view.record],view.query,view.signals,view.probes,
                             policy={'fixed_voi':'voi','cheapest':'cheapest',
                                     'never':'never'}[mode],**kw)
    return plan_adaptive([view.record],view.query,view.signals,view.probes,
                          audits=list(audits),
                          mode={'posterior_mean':'posterior_mean',
                                'conservative':'conservative'}[mode],
                          window_hours=72,min_class_n=12,**kw)


def execute_preplanned(case:Trial,decision)->dict:
    """Only the executor can open its own chosen synthetic sensor result."""
    v=case.view
    if decision.authorized_to_fetch or decision.consumer_publish or decision.model_used:
        raise AssertionError('The research proposal attempted production I/O')
    signals=list(v.signals)
    checked=decision.action=='PROPOSE_CHECK'
    spent=Decimal('0')
    if checked:
        matched=[o for o in v.probes if o.channel.id==decision.probe_id]
        if len(matched)!=1 or matched[0].channel.publisher_root!=decision.probe_root:
            raise ValueError('Selected source does not match the signed research proposal')
        option=matched[0]
        if (not option.channel.approved or
            option.channel.publisher_root not in v.approved_roots or
            option.channel.cost>v.budget or
            option.latency_minutes>v.max_wait_minutes):
            raise AssertionError('Source/budget/deadline authority bypass')
        arrived=aware(v.query.at)+timedelta(minutes=option.latency_minutes)
        answer=dict(case.hidden_answers)[option.channel.id]
        signals.append(Signal(f'fictional-check:{option.channel.id}:{v.record["id"]}',
            v.record['id'],option.channel.publisher_root,
            arrived.isoformat(),arrived.isoformat(),answer,'research_ingest'))
        spent=Decimal(str(option.channel.cost))
    decision_clock=aware(v.query.at)+timedelta(minutes=v.max_wait_minutes)
    final=run_pipeline([v.record],replace(v.query,at=decision_clock.isoformat()),
                       signals,approved_roots=v.approved_roots)
    accepted=final['action']=='LAB_CORROBORATED' and bool(final['selected_ids'])
    if final['consumer_publish'] or not final['laboratory_only']:
        raise AssertionError('Fictional observations were promoted to real business facts')
    return {
        'accepted':accepted,
        'correct_assertion':accepted and case.truth,
        'false_assertion':accepted and not case.truth,
        'checked':checked,'check_cost_utility_units':float(spent),
        'human_review':decision.action=='HUMAN_REVIEW',
        'proposed_action':decision.action,
        'proposal_without_external_io':True,
    }


def run(config:dict|None=None)->dict:
    cfg=json.loads(CONFIG.read_text()) if config is None else config
    keys={'study','fixed_before_simulation','seed','cases_per_regime',
          'regimes','policies','false_assertion_penalty','paired_draws',
          'audit_window_hours','audit_label_delay_hours','per_hour_background_audits'}
    if (not isinstance(cfg,dict) or set(cfg)!=keys or cfg['study']!='KEP-CORE-003'
        or cfg['fixed_before_simulation'] is not True
        or cfg['regimes']!=list(REGIMES) or cfg['policies']!=list(POLICIES)
        or type(cfg['seed']) is not int
        or type(cfg['cases_per_regime']) is not int or
        not 1<=cfg['cases_per_regime']<=500
        or type(cfg['paired_draws']) is not int or
        not 100<=cfg['paired_draws']<=1000
        or type(cfg['false_assertion_penalty']) not in (int,float)
        or not 0<cfg['false_assertion_penalty']<=50
        or cfg['audit_window_hours']!=72
        or cfg['audit_label_delay_hours']!=3
        or cfg['per_hour_background_audits']!=BACKGROUND_AUDITS_PER_HOUR):
        raise ValueError('Changed or unsafe synthetic adaptive protocol')
    results={}
    for regime_i,regime in enumerate(REGIMES):
        cases,audit_stream=generate_chronological(
            regime,cfg['seed']+regime_i,cfg['cases_per_regime'])
        measures={policy:[] for policy in POLICIES}
        action_counts={policy:{} for policy in POLICIES}
        audited_seen_min=None
        audited_seen_max=0
        for case in cases:
            # History selection is intentionally executed outside the policy:
            # its inputs never contain the current/future audit label.
            asof=aware(case.view.query.at)
            available=tuple(a for a in audit_stream if aware(a.adjudicated_at)<=asof)
            audited_seen_min=len(available) if audited_seen_min is None else min(audited_seen_min,len(available))
            audited_seen_max=max(audited_seen_max,len(available))
            for policy in POLICIES:
                proposal=choose(case.view,available,policy)
                action_counts[policy][proposal.action]=action_counts[policy].get(proposal.action,0)+1
                measures[policy].append(execute_preplanned(case,proposal))
        results[regime]={
            'methods':{policy:summarize_budgeted(
                cases,measures[policy],cfg['false_assertion_penalty'])
                for policy in POLICIES},
            'decision_counts':{p:dict(sorted(action_counts[p].items())) for p in POLICIES},
            'independent_audits_available_first':audited_seen_min,
            'independent_audits_available_last':audited_seen_max,
            'paired_conservative_minus_fixed_voi':paired_budgeted(
                cases,measures['conservative'],measures['fixed_voi'],
                cfg['false_assertion_penalty'],cfg['seed']+regime_i+7800,
                cfg['paired_draws']),
        }
    return {
        'study':'KEP-CORE-003',
        'scenario_origin':'WHOLLY_SYNTHETIC_INDEPENDENT_BACKGROUND_AUDITS',
        'real_human_reviews_used':0,
        'actual_field_source_calibration':False,
        'real_business_accuracy':None,
        'source_downloads':0,'model_calls':0,'consumer_publish':False,
        'truth_and_future_answers_absent_from_policy_view':True,
        'audit_feedback_independent_of_policy_check_selection':True,
        'results':results,'config':cfg,
        'limitations':('Historical sensor adjudications are fictional independent samples. '
           'Causal replay, source errors, label delay and drift are authored. '
           'Any estimated reliability is conditional on those inputs, not Istanbul truth. '
           'Correlated publisher failure can fool root-based independence.')
    }


if __name__=='__main__':
    print(json.dumps(run(),ensure_ascii=False,indent=2,sort_keys=True))
