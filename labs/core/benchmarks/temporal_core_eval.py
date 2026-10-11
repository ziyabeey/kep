"""Paired, reproducible synthetic city-state challenge for temporal KEP Core.

Hidden simulation truth is carried ONLY by SimCase and scoring, never sent to
run_pipeline, Core, source signals or the model adapter. No new data downloads.
The deliberately naive baselines are authored controls, not competitors.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from random import Random
import copy
import hashlib
import json
import statistics

from kepcore.core import Query, decide, load_catalog
from kepcore.temporal_pipeline import Signal, evidence_snapshot, run_pipeline

ROOT=Path(__file__).resolve().parents[1]
PROTOCOL=ROOT/'benchmarks/temporal_core_protocol.json'
NOW=datetime(2026,10,10,9,tzinfo=timezone.utc)
REGIMES=('matched','mirror_attack','delivery_lag','source_degradation','rights_blocked')
POLICIES=('core_only','count_raw_messages','single_root','temporal_root','always_abstain')
ROOTS=('origin','partner')


@dataclass(frozen=True)
class CaseInput:
    """Policy-visible data. It has NO hidden-world reality/label attribute."""
    record: dict
    signals: tuple[Signal,...]
    query: Query
    regime: str


@dataclass(frozen=True)
class SimCase:
    """Evaluator-only wrapper; policy_actions accepts CaseInput, not this."""
    truth: bool
    view: CaseInput


def _draw(truth: bool, sensitivity: float, specificity: float, rng: Random) -> bool:
    return rng.random() < (sensitivity if truth else (1-specificity))


def generate(regime: str, seed: int, n: int) -> list[SimCase]:
    if regime not in REGIMES or type(seed) is not int or type(n) is not int or not 1<=n<=10_000:
        raise ValueError('Unknown regime or invalid frozen synthetic population')
    rng=Random(seed)
    base=next(r for r in load_catalog() if r['kind']=='place' and r['city']=='İstanbul')
    at=NOW.isoformat()
    out=[]
    for i in range(n):
        reality=(rng.random()<.78)  # Simulator truth, NOT a KEP input!
        record=copy.deepcopy(base)
        record.update({
            'id':f'syn:core001:{regime}:{seed}:{i}',
            'source_id':'synthetic_core_001',
            'publisher_root':'synthetic_catalog',
            'source_url':'synthetic://offline-simulator',
            'source_record_hash':hashlib.sha256(
                f'core001:{regime}:{seed}:{i}'.encode()).hexdigest(),
            'synthetic':True, 'synthetic_overlay':'CORE_001_KNOWN_TRUTH_ONLY_IN_EVALUATOR',
            'rights_scope':('pending' if regime=='rights_blocked' and i%3==0
                            else 'open_attribution'),
        })
        sens_a, spec_a=(.90,.87)
        sens_b, spec_b=(.85,.82)
        if regime=='source_degradation':
            sens_a,spec_a=.62,.60
            sens_b,spec_b=.62,.60
        a=_draw(reality,sens_a,spec_a,rng)
        b=_draw(reality,sens_b,spec_b,rng)
        events=[]
        def add(event_id,root,answer,observed,available,rights='research_ingest'):
            events.append(Signal(event_id,record['id'],root,observed.isoformat(),
                                 available.isoformat(),answer,rights))
        old=NOW-timedelta(hours=rng.randint(1,6))
        add(f'sensor-a-{i}','origin',a,old,old+timedelta(minutes=3))
        # Copies are deliberately from the SAME publisher root, never votes.
        copies=12 if regime=='mirror_attack' else 2
        for j in range(copies):
            add(f'mirror-{i}-{j}','origin',a,old,old+timedelta(minutes=5+j))
        if regime=='mirror_attack' and i%3==0:
            # Suppress truly independent evidence while making more echoes.
            pass
        else:
            t=NOW-timedelta(hours=rng.randint(1,8))
            delay=timedelta(hours=12) if regime=='delivery_lag' and i%2==0 else timedelta(minutes=1)
            add(f'sensor-b-{i}','partner',b,t,t+delay)
        if i%11==0:
            # Source with no research access; very strong-looking but forbidden.
            add(f'unapproved-{i}','unlicensed',reality,old,old,'blocked')
        if i%17==0:
            # Future information must be invisible at NOW.
            future=NOW+timedelta(hours=2)
            add(f'future-{i}','partner',reality,future,future)
        if i%19==0:
            # Very old information is intentionally stale.
            stale=NOW-timedelta(hours=72)
            add(f'stale-{i}','partner',reality,stale,stale)
        q=Query(city='İstanbul',kind='place',at=at,limit=1)
        out.append(SimCase(reality,CaseInput(record,tuple(events),q,regime)))
    return out


def policy_actions(case: CaseInput) -> dict[str,bool]:
    if not isinstance(case,CaseInput):
        raise TypeError('Never pass hidden ground-truth wrapper into the policy')
    """Return yes/no research assertions; never modify or inspect case.truth."""
    row=case.record
    core_decision=decide([row],case.query)
    permitted=core_decision.action in {'DISCOVER','RECOMMEND'} and bool(core_decision.selected)
    # An intentionally unsafe message-counting comparison that does NOT dedupe
    # publisher roots. Still obeys factual/rights Core exclusions for fair setup.
    positive_msgs=sum(e.supports and e.rights_scope=='research_ingest'
                      and e.publisher_root in ROOTS and
                      e.available_at<=case.query.at for e in case.signals)
    snapshot=evidence_snapshot(case.signals,as_of=case.query.at,
                               entity_ids=[row['id']],approved_roots=ROOTS)
    state=snapshot[row['id']]
    lab=run_pipeline([row],case.query,list(case.signals),approved_roots=ROOTS)
    if lab['consumer_publish'] or not lab['laboratory_only'] or lab['model_used']:
        raise AssertionError('Lab gate was silently promoted')
    return {
        'core_only':permitted,
        'count_raw_messages':permitted and positive_msgs>=2,
        'single_root':permitted and bool(state['positive_roots']),
        'temporal_root':lab['action']=='LAB_CORROBORATED' and bool(lab['selected_ids']),
        'always_abstain':False,
    }


def _summarize(cases:list[SimCase], decisions:list[bool],penalty_false:float)->dict:
    n=len(cases)
    selected=sum(decisions)
    false=sum(accepted and not case.truth for case,accepted in zip(cases,decisions))
    correct=sum(accepted and case.truth for case,accepted in zip(cases,decisions))
    return {
        'n':n,
        'asserted_n':selected,
        'correct_asserted_n':correct,
        'false_asserted_n':false,
        'assertion_coverage':round(selected/n,6),
        'false_assertion_fraction_if_asserted':round(false/selected,6) if selected else None,
        'missed_true_cases':sum(case.truth and not a for case,a in zip(cases,decisions)),
        'normalized_utility_per_case':round((correct-penalty_false*false)/n,6),
        'true_world_prevalence_simulated':round(sum(c.truth for c in cases)/n,6),
    }


def _paired(cases, left, right, *,penalty_false:float, seed:int, draws:int)->dict:
    utility=lambda truth,pick: (1. if truth else -penalty_false) if pick else 0.
    differences=[utility(c.truth,a)-utility(c.truth,b)
                 for c,a,b in zip(cases,left,right)]
    rng=Random(seed)
    sims=sorted(sum(rng.choices(differences,k=len(differences)))/len(differences)
                for _ in range(draws))
    return {'mean_difference':round(sum(differences)/len(differences),6),
            'synthetic_conditional_bootstrap_95':[
                round(sims[int(.025*draws)],6),
                round(sims[min(draws-1,int(.975*draws))],6)],
            'note':'Simulation-conditional paired resampling, NOT a real-field confidence interval.'}


def run(config:dict|None=None)->dict:
    cfg=json.loads(PROTOCOL.read_text()) if config is None else config
    keys={'study','fixed_before_simulation','seed','n_per_regime','regimes','policies',
          'false_assertion_penalty','paired_bootstrap_draws'}
    if (not isinstance(cfg,dict) or set(cfg)!=keys or cfg['study']!='KEP-CORE-001'
        or cfg['fixed_before_simulation'] is not True or cfg['policies']!=list(POLICIES)
        or cfg['regimes']!=list(REGIMES) or type(cfg['seed']) is not int
        or type(cfg['n_per_regime']) is not int or not 1<=cfg['n_per_regime']<=10_000
        or type(cfg['paired_bootstrap_draws']) is not int
        or not 100<=cfg['paired_bootstrap_draws']<=2000
        or type(cfg['false_assertion_penalty']) not in (int,float)
        or not 0<cfg['false_assertion_penalty']<=100):
        raise ValueError('Unregistered synthetic experiment configuration')
    results={}
    for j,regime in enumerate(REGIMES):
        cases=generate(regime,cfg['seed']+j,cfg['n_per_regime'])
        same_scenarios={name:[] for name in POLICIES}
        for case in cases:
            actions=policy_actions(case.view)
            for policy in POLICIES:
                same_scenarios[policy].append(actions[policy])
        report={p:_summarize(cases,same_scenarios[p],cfg['false_assertion_penalty'])
                for p in POLICIES}
        results[regime]={
            'policies':report,
            'paired_kernel_minus_core_only':_paired(
                cases,same_scenarios['temporal_root'],same_scenarios['core_only'],
                penalty_false=cfg['false_assertion_penalty'],seed=cfg['seed']+j+900,
                draws=cfg['paired_bootstrap_draws']),
        }
    return {
        'study':'KEP-CORE-001','scenario_origin':'wholly_synthetic_hidden_truth',
        'real_field_accuracy':None,'business_openings_or_closures_accuracy':None,
        'consumer_publish':False,'model_api_calls':0,'new_source_downloads':0,
        'test_truth_not_available_to_pipeline':True,
        'policies_predeclared':list(POLICIES),
        'config':cfg,'results':results,
        'note':'Rules and sensor errors are authored in this simulator. Reported advantages and failures are conditional on these assumptions, not observed KEP, competitor or Istanbul accuracy.',
    }


if __name__=='__main__':
    print(json.dumps(run(),ensure_ascii=False,indent=2,sort_keys=True))
