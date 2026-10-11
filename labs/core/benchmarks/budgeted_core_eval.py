"""Paired budget/latency/abstention challenge on wholly synthetic source events.

Truth and future probe answers are NEVER passed to the planning function.
All methods get the same initial view and pre-sampled potential probe outcomes.
If one check is chosen, its answer is revealed ONLY to the simulation executor.
No new factual data, real-world site, browser, model or paid API is consulted.
"""
from __future__ import annotations
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from random import Random
from hashlib import sha256
import copy
import json
import statistics

from kepcore.core import Query,load_catalog
from kepcore.calibration import aware
from kepcore.evidence_lab import EvidenceChannel
from kepcore.temporal_pipeline import Signal,run_pipeline
from kepcore.budgeted_verify import CheckOption,plan_research,MODES

ROOT=Path(__file__).resolve().parents[1]
PROTOCOL=ROOT/'benchmarks/budgeted_core_protocol.json'
TIME=datetime(2026,10,10,9,0,tzinfo=timezone.utc)
REGIMES=('matched','tight_budget','short_deadline','quality_degradation',
         'echo_storm','rights_and_disputes')
POLICIES=('never','cheapest','max_information','always_strong','voi')
ROOTS=('origin','cheap_root','balanced_root','deep_root')
SOURCE_MODEL=EvidenceChannel('source','origin',.88,.82,0.,True,True)


@dataclass(frozen=True)
class View:
    record:dict
    query:Query
    signals:tuple[Signal,...]
    probes:tuple[CheckOption,...]
    observed_sources:tuple[EvidenceChannel,...]
    approved_roots:tuple[str,...]
    prior:float
    budget:float
    max_wait_minutes:int


@dataclass(frozen=True)
class Trial:
    """Reality is not a field of the policy-visible View."""
    truth:bool
    view:View
    hidden_answers:tuple[tuple[str,bool],...]


def _draw(truth:bool,sensitivity:float,specificity:float,rng:Random)->bool:
    return rng.random()<(sensitivity if truth else 1-specificity)


def _check_options()->tuple[CheckOption,...]:
    return (
        CheckOption(EvidenceChannel('cheap','cheap_root',.74,.72,.020,True),2),
        CheckOption(EvidenceChannel('balanced','balanced_root',.88,.86,.065,True),7),
        CheckOption(EvidenceChannel('deep','deep_root',.97,.95,.115,True),16),
        # Deliberately tempting but FORBIDDEN sensor options:
        CheckOption(EvidenceChannel('mirror','origin',.999,.999,0,True),0),
        CheckOption(EvidenceChannel('unlicensed','external_unapproved',.999,.999,0,False),0),
    )


def generate(regime:str,seed:int,n:int)->list[Trial]:
    if regime not in REGIMES or type(seed) is not int or type(n) is not int or not 1<=n<=10_000:
        raise ValueError('Invalid wholly synthetic regime or size')
    rng=Random(seed)
    base=next(r for r in load_catalog() if r['kind']=='place' and r['city']=='İstanbul')
    prior=.72 if regime!='quality_degradation' else .72
    options=_check_options()
    cases=[]
    for i in range(n):
        truth=rng.random() < (.70 if regime!='quality_degradation' else .67)
        source=copy.deepcopy(base)
        source.update(
            id=f'synthetic:core002:{regime}:{seed}:{i}',
            source_url='synthetic://core002-created-in-memory',
            source_id='core002_synthetic_fixture',
            publisher_root='synthetic_source',
            source_record_hash=sha256(f'{regime}/{seed}/{i}'.encode()).hexdigest(),
            synthetic=True,
            rights_scope=('pending' if regime=='rights_and_disputes' and i%4==0
                          else 'open_attribution'),
        )
        start=TIME-timedelta(hours=2)
        original_quality=(.60,.58) if regime=='quality_degradation' else (.88,.82)
        original=_draw(truth,*original_quality,rng)
        incoming=[]
        def emit(name,root,yes,observed=start,available=None,rights='research_ingest'):
            arrival=observed if available is None else available
            incoming.append(Signal(name,source['id'],root,observed.isoformat(),
                                   arrival.isoformat(),yes,rights))
        if i%13!=0:
            emit(f'origin:{i}','origin',original)
        if regime=='echo_storm':
            for j in range(25):
                emit(f'echo:{i}:{j}','origin',original)
        else:
            for j in range(2):
                emit(f'echo:{i}:{j}','origin',original)
        if regime=='rights_and_disputes' and i%7==0:
            # Equal-time source conflict. Two publication links never settle it.
            emit(f'dispute:{i}','origin',not original)
        if i%11==0:
            second=_draw(truth,.78,.76,rng)
            emit(f'previous-independent:{i}','balanced_root',second)
        if i%17==0:
            # A second observation will be available only after the planner's
            # original query time, but sometimes before the final deadline.
            t=TIME+timedelta(minutes=3)
            emit(f'delayed:{i}','cheap_root',truth,t,t)

        actual_quality=(
            {'cheap':(.55,.54),'balanced':(.58,.57),'deep':(.64,.62)}
            if regime=='quality_degradation' else
            {'cheap':(.74,.72),'balanced':(.88,.86),'deep':(.97,.95)}
        )
        answers={key:_draw(truth,*actual_quality[key],rng) for key in
                 ('cheap','balanced','deep')}
        # These are also pre-sampled, but they are never available to a policy
        # because their source roots are forbidden.
        answers['mirror']=truth
        answers['unlicensed']=truth

        budget=.03 if regime=='tight_budget' else .15
        wait=3 if regime=='short_deadline' else 20
        q=Query(city='İstanbul',kind='place',at=TIME.isoformat(),limit=1)
        cases.append(Trial(truth,View(source,q,tuple(incoming),options,
                           (SOURCE_MODEL,),ROOTS,prior,budget,wait),
                           tuple(sorted(answers.items()))))
    return cases


def action_for(view:View,policy:str):
    if type(view) is not View:
        raise TypeError('Policy must never receive hidden world truth or answers')
    return plan_research([view.record],view.query,view.signals,view.probes,
        observed_channels=view.observed_sources,approved_roots=view.approved_roots,
        prior=view.prior,budget=view.budget,
        max_wait_minutes=view.max_wait_minutes,policy=policy)


def execute(trial:Trial,policy:str)->dict:
    """Only executor sees pre-sampled answer AFTER the chosen plan is frozen."""
    if policy not in POLICIES or not isinstance(trial,Trial):
        raise ValueError('Unsupported predeclared synthetic control')
    view=trial.view
    planned=action_for(view,policy)
    if planned.consumer_publish or planned.authorized_to_fetch or planned.model_used:
        raise AssertionError('Research planner escaped LAB_ONLY boundary')
    new_events=list(view.signals)
    spent=0.
    if planned.action=='PROPOSE_CHECK':
        choice=next((x for x in view.probes if x.channel.id==planned.probe_id),None)
        if choice is None or choice.channel.publisher_root!=planned.probe_root:
            raise AssertionError('Unknown unapproved simulated probe')
        # One-time costs count even if future answer disagrees or abstains.
        spent=choice.channel.cost
        answer=dict(trial.hidden_answers)[choice.channel.id]
        arrived=aware(view.query.at)+timedelta(minutes=choice.latency_minutes)
        if arrived>aware(view.query.at)+timedelta(minutes=view.max_wait_minutes):
            raise AssertionError('Probe result breached the deadline')
        new_events.append(Signal('simulated-response:'+choice.channel.id+':'+view.record['id'],
                                 view.record['id'],choice.channel.publisher_root,
                                 arrived.isoformat(),arrived.isoformat(),answer,
                                 'research_ingest'))
    # Every policy sees exactly the same deadline and existing late arrivals;
    # comparisons do not give VERIFY extra clock time or early hidden truth.
    deadline=aware(view.query.at)+timedelta(minutes=view.max_wait_minutes)
    later=replace(view.query,at=deadline.isoformat())
    verdict=run_pipeline([view.record],later,new_events,
                         approved_roots=view.approved_roots)
    accept=verdict['action']=='LAB_CORROBORATED' and bool(verdict['selected_ids'])
    if verdict['consumer_publish'] or not verdict['laboratory_only']:
        raise AssertionError('Simulation cannot authorize public publishing')
    return {
        'accepted':accept,
        'false_assertion':bool(accept and not trial.truth),
        'correct_assertion':bool(accept and trial.truth),
        'checked':planned.action=='PROPOSE_CHECK',
        'check_cost_utility_units':spent,
        'proposal':planned.action,
        'human_review':planned.action=='HUMAN_REVIEW',
        'accepted_with_model':False,
        'final_lab_verdict':verdict['action'],
    }


def summarize(trials:list[Trial],results:list[dict],false_penalty:float)->dict:
    n=len(trials); asserted=sum(x['accepted'] for x in results)
    wrong=sum(x['false_assertion'] for x in results)
    correct=sum(x['correct_assertion'] for x in results)
    checks=sum(x['checked'] for x in results)
    spent=sum(x['check_cost_utility_units'] for x in results)
    value=correct-false_penalty*wrong-spent
    return {
        'cases':n,'assertions':asserted,'correct_assertions':correct,
        'false_assertions':wrong,'missed_true':sum(c.truth and not r['accepted']
                                                for c,r in zip(trials,results)),
        'assertion_coverage':round(asserted/n,6),
        'false_fraction_given_assertion':round(wrong/asserted,6) if asserted else None,
        'checks':checks,'checks_per_case':round(checks/n,6),
        'human_review_proposals':sum(x['human_review'] for x in results),
        'total_check_cost_utility_units':round(spent,6),
        'utility_per_case':round(value/n,6),
    }


def _paired(trials,aa,bb,penalty,seed,draws):
    def value(trial,out):
        return ((1 if trial.truth else -penalty) if out['accepted'] else 0)-out['check_cost_utility_units']
    differences=[value(t,a)-value(t,b) for t,a,b in zip(trials,aa,bb)]
    rng=Random(seed)
    sims=sorted(sum(rng.choices(differences,k=len(differences)))/len(differences)
                for _ in range(draws))
    return {
        'mean_voi_minus_never':round(sum(differences)/len(differences),6),
        'conditional_bootstrap_95':[
            round(sims[int(.025*draws)],6),
            round(sims[min(draws-1,int(.975*draws))],6)],
        'draws':draws,
        'caution':'Synthetic matched-case bootstrap, not independent real-user confidence.'
    }


def run(config:dict|None=None)->dict:
    cfg=json.loads(PROTOCOL.read_text()) if config is None else config
    expected={'study','fixed_before_simulation','seed','cases_per_regime',
              'regimes','policies','false_assertion_penalty','paired_draws',
              'max_checks_per_case'}
    if (not isinstance(cfg,dict) or set(cfg)!=expected or cfg['study']!='KEP-CORE-002'
        or cfg['fixed_before_simulation'] is not True
        or cfg['regimes']!=list(REGIMES) or cfg['policies']!=list(POLICIES)
        or cfg['max_checks_per_case']!=1 or type(cfg['seed']) is not int
        or type(cfg['cases_per_regime']) is not int or
        not 1<=cfg['cases_per_regime']<=10_000
        or type(cfg['paired_draws']) is not int or not 100<=cfg['paired_draws']<=2000
        or type(cfg['false_assertion_penalty']) not in (float,int)
        or not 0<cfg['false_assertion_penalty']<=100):
        raise ValueError('CORE-002 experiment is not the registered synthetic protocol')
    all_results={}
    for j,regime in enumerate(REGIMES):
        trials=generate(regime,cfg['seed']+j,cfg['cases_per_regime'])
        outcomes={policy:[] for policy in POLICIES}
        for trial in trials:
            for p in POLICIES:
                outcomes[p].append(execute(trial,p))
        all_results[regime]={
            'methods':{p:summarize(trials,outcomes[p],cfg['false_assertion_penalty'])
                       for p in POLICIES},
            'voi_vs_never':_paired(trials,outcomes['voi'],outcomes['never'],
                                  cfg['false_assertion_penalty'],
                                  cfg['seed']+j+1900,cfg['paired_draws']),
        }
    return {
        'study':'KEP-CORE-002','scenario_origin':'fully_synthetic_paired_hidden_truth',
        'source_downloads':0,'model_calls':0,
        'real_world_business_accuracy':None,
        'calibrated_source_reliability':False,
        'real_field_labels_used':0,'consumer_publish':False,
        'policy_inputs_cannot_access_truth_or_future_answers':True,
        'config':cfg,'regimes':all_results,
        'caution':'Reliability priors, signal delays, outcomes and utility are authored synthetic assumptions; no empirical validity, real API-cost savings or competitor lift.'
    }


if __name__=='__main__':
    print(json.dumps(run(),ensure_ascii=False,sort_keys=True,indent=2))
