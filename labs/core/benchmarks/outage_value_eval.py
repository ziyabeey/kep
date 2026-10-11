"""CORE-004A: prerecorded, paired outage utility holdout (wholly SYNTHETIC).

This challenge is separate from the already-exposed CORE-003 seed and holdout.
Test truth and prospective check answers reside in Trial, NOT policy View.
Existing CORE-003 generators provide time-causal independent background audit
streams; new degraded-outage modes corrupt ONLY fictional test-world sensor
responses AFTER independent audits stop. The policies never see this corruption
flag, any true label, or future check answers.

This is a falsification experiment: protocol's GO/NO_GO thresholds were
committed before the candidate policy and holdout result were implemented.
Failed thresholds REQUIRE a negative report; no adaptive retuning on these data.
"""
from __future__ import annotations
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from random import Random
import json
import math

from kepcore.calibration import aware
from benchmarks.adaptive_trust_eval import (
    generate_chronological,choose as core003_choose,execute_preplanned,
    QUALITY,DEGRADED,
)
from benchmarks.budgeted_core_eval import (
    Trial,View,summarize as summarize_paired,_paired as paired_delta,
)
from kepcore.outage_grace import plan_outage_grace

ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/'benchmarks/outage_value_protocol.json'
REGIMES=('outage_stable','outage_abrupt_drift','outage_gradual_drift',
         'healthy','delayed_reviews','shared_rumor')
POLICIES=('never','fixed_voi','conservative','bounded_grace')
EXPECTED_GATES=(
  'main_regime','min_gain_utility_per_case_over_conservative',
  'min_gain_utility_per_case_over_never',
  'max_false_assertions_vs_fixed_voi_outage_stable',
  'max_drift_utility_regret_vs_fixed_voi_per_case',
  'main_regime_observed_fail_requires_report_not_tuning',
  'synthetic_results_are_not_generalizable',
  'successful_tests_are_not_accuracy_evidence',
)


def config()->dict:
    x=json.loads(CONFIG.read_text(encoding='utf-8'))
    e=x.get('experiment',{})
    g=x.get('go_no_go_frozen',{})
    p=x.get('proposed_rule_fixed_before_holdout',{})
    if (x.get('study')!='KEP-CORE-004A'
        or x.get('locked_before_policy_implementation') is not True
        or x.get('new_real_source_reads')!=0
        or e.get('seed')!=2026101204
        or e.get('regimes')!=list(REGIMES)
        or e.get('comparisons')!=list(POLICIES)
        or e.get('cases_per_regime')!=180
        or e.get('false_assertion_penalty',x.get('false_assertion_penalty'))!=4
        or e.get('paired_bootstrap_draws')!=200
        or set(g)!=set(EXPECTED_GATES)
        or g.get('main_regime')!='outage_stable'
        or g.get('min_gain_utility_per_case_over_conservative')!=.025
        or g.get('min_gain_utility_per_case_over_never')!=0
        or g.get('max_false_assertions_vs_fixed_voi_outage_stable')!=0
        or g.get('max_drift_utility_regret_vs_fixed_voi_per_case')!=.05
        or g.get('main_regime_observed_fail_requires_report_not_tuning') is not True
        or p.get('current_audit_window_hours')!=72
        or p.get('fallback_audit_window_hours')!=168
        or p.get('grace_max_hours_since_last_adjudication')!=48
        or p.get('require_lower_sensitivity_and_specificity_each_at_least')!=.62
        or p.get('min_positive_and_negative_independent_audits')!=12):
        raise ValueError('CORE-004A preregistration altered or malformed')
    return x


def _truth_draw(truth:bool,rates:tuple[float,float],rng:Random)->bool:
    return rng.random()<(rates[0] if truth else 1-rates[1])


def _drifted_rates(root:str,index:int,regime:str):
    old=QUALITY[root]
    if regime=='outage_abrupt_drift':
        ratio=1. if index>=70 else 0.
    else:
        ratio=min(1.,max(0.,(index-55)/115.))
    return tuple(a*(1-ratio)+b*ratio for a,b in zip(old,DEGRADED[root]))


def _corrupt_after_outage(trials:list[Trial],regime:str,seed:int):
    """Inject fictional sensor drift, no training-label update or hidden oracle."""
    rng=Random(seed+721055)
    updated=[]
    for i,trial in enumerate(trials):
        if i<56:
            updated.append(trial)
            continue
        group_decisions={}
        for root in QUALITY:
            group_decisions[root]=_truth_draw(
                trial.truth,_drifted_rates(root,i,regime),rng)
        edited=tuple(replace(signal,supports=group_decisions[signal.publisher_root])
              if signal.publisher_root in group_decisions else signal
              for signal in trial.view.signals)
        answers=dict(trial.hidden_answers)
        for name,root in (('cheap','cheap_root'),
                          ('balanced','balanced_root'),('deep','deep_root')):
            answers[name]=_truth_draw(
                trial.truth,_drifted_rates(root,i,regime),rng)
        updated.append(replace(trial,
            view=replace(trial.view,signals=edited),
            hidden_answers=tuple(sorted(answers.items()))))
    return updated


def generate(regime:str,seed:int,n:int):
    if regime not in REGIMES or type(seed) is not int or type(n) is not int or not 1<=n<=300:
        raise ValueError('Unregistered independent synthetic risk scenario')
    original={
        'outage_stable':'audit_outage',
        'outage_abrupt_drift':'audit_outage',
        'outage_gradual_drift':'audit_outage',
        'healthy':'stable',
        'delayed_reviews':'late_adjudication',
        'shared_rumor':'correlated_failure',
    }[regime]
    cases,audits=generate_chronological(original,seed,n)
    if regime in ('outage_abrupt_drift','outage_gradual_drift'):
        cases=_corrupt_after_outage(cases,regime,seed)
    return cases,audits


def choose(view:View,audits,policy:str):
    if type(view) is not View or policy not in POLICIES:
        raise TypeError('Planner may receive only policy-visible synthetic View')
    if policy!='bounded_grace':
        return core003_choose(view,audits,policy)
    return plan_outage_grace(
        [view.record],view.query,view.signals,view.probes,
        observed_channels=view.observed_sources,
        approved_roots=view.approved_roots,prior=view.prior,budget=view.budget,
        max_wait_minutes=view.max_wait_minutes,audits=list(audits),
        short_window_hours=72,long_window_hours=168,grace_hours=48,
        min_class_n=12)


def gate(results:dict,config:dict)->dict:
    """Preregistered decision criterion, no post-hoc optimizations."""
    params=config['go_no_go_frozen']
    a=results['outage_stable']['methods']
    test=a['bounded_grace'];fixed=a['fixed_voi']
    checks={
      'outage_utility_gain_over_conservative': (
        test['utility_per_case']-a['conservative']['utility_per_case']
        >=params['min_gain_utility_per_case_over_conservative']),
      'outage_utility_gain_over_never': (
        test['utility_per_case']-a['never']['utility_per_case']
        >params['min_gain_utility_per_case_over_never']),
      'outage_false_assertions_not_above_fixed':(
        test['false_assertions']<=fixed['false_assertions']+
        params['max_false_assertions_vs_fixed_voi_outage_stable']),
    }
    for scenario in ('outage_abrupt_drift','outage_gradual_drift'):
        methods=results[scenario]['methods']
        checks[scenario+'_bounded_regret_vs_fixed']=(
            methods['fixed_voi']['utility_per_case']-
            methods['bounded_grace']['utility_per_case']
            <=params['max_drift_utility_regret_vs_fixed_voi_per_case'])
    return {
      'decision':'GO' if all(checks.values()) else 'NO_GO',
      'predeclared_checks':checks,
      'failed':sorted(k for k,v in checks.items() if not v),
      'criteria_unmodified_after_outcomes':True,
      'GO_means':'Research-only acceptance for optional synthetic policy, NOT production deployment or real source calibration.'
    }


def run(config_override:dict|None=None):
    cfg=config()
    if config_override is not None:
        ex=config_override
        if type(ex) is not dict or set(ex)!={'cases_per_regime','paired_bootstrap_draws'}:
            raise ValueError('Only bounded unit-test smaller simulation permitted')
        if (type(ex['cases_per_regime']) is not int or
            not 1<=ex['cases_per_regime']<=15 or
            type(ex['paired_bootstrap_draws']) is not int or
            not 100<=ex['paired_bootstrap_draws']<=200):
            raise ValueError('Invalid small test settings')
        cfg=json.loads(json.dumps(cfg))
        cfg['experiment'].update(ex)
        # Contract tests deliberately use a DIFFERENT seed, never the full
        # preregistered 1,080-case holdout's earliest instances.
        cfg['experiment']['seed']=20260901
    e=cfg['experiment']
    all_results={}
    for ri,regime in enumerate(REGIMES):
        cases,audit_stream=generate(regime,e['seed']+ri,e['cases_per_regime'])
        outcomes={name:[] for name in POLICIES}
        actions={name:{} for name in POLICIES}
        for trial in cases:
            as_of=aware(trial.view.query.at)
            # No current or future case truth enters the planner. Only
            # separately generated background audits, already adjudicated.
            available=tuple(a for a in audit_stream if aware(a.adjudicated_at)<=as_of)
            for policy in POLICIES:
                proposal=choose(trial.view,available,policy)
                if proposal.consumer_publish or proposal.authorized_to_fetch:
                    raise AssertionError('Lab experiment attempted external action')
                actions[policy][proposal.action]=actions[policy].get(proposal.action,0)+1
                outcomes[policy].append(execute_preplanned(trial,proposal))
        all_results[regime]={
            'methods':{p:summarize_paired(cases,outcomes[p],4)
                       for p in POLICIES},
            'action_counts':{p:dict(sorted(actions[p].items())) for p in POLICIES},
            'paired_grace_minus_conservative':paired_delta(
                cases,outcomes['bounded_grace'],outcomes['conservative'],4,
                seed=e['seed']+ri+4400,draws=e['paired_bootstrap_draws']),
        }
    return {
      'study':'KEP-CORE-004A',
      'scenario_origin':'PREREGISTERED_WHOLLY_SYNTHETIC_NEW_HOLDOUT',
      'actual_business_accuracy':None,
      'external_data_downloads':0,'model_calls':0,'real_human_labels_used':0,
      'consumer_publish':False,
      'policy_received_hidden_truth_or_future_answers':False,
      'as_of_feedback_embargo_enforced':True,
      'config':cfg,'regimes':all_results,
      'acceptance':gate(all_results,cfg),
      'caution':('NO_GO is a valid scientific outcome. A positive synthetic '
        'score is conditional on authored sensor truth, labels, outage and '
        'normalized utility. Real independence, venue existence, user benefit '
        'and actual operational review cost remain unknown.'),
    }


if __name__=='__main__':
    print(json.dumps(run(),ensure_ascii=False,sort_keys=True,indent=2))
