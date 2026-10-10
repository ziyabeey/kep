"""Matched vs assumption-shifted offline evidence-acquisition benchmark.

Every policy receives identical situations and pre-sampled future observations.
Utility and source quality are synthetic. No live/paid API calls.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
import json
import math
import random
import statistics

from kepcore.evidence_lab import EvidenceChannel, Observation, route_research, action_utility

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / 'benchmarks/evidence_protocol.json'


@dataclass(frozen=True)
class Case:
    prior: float
    truth: bool
    existing: tuple[Observation, ...]
    channels: tuple[EvidenceChannel, ...]
    responses: dict[str, bool]


def _draw_sensor(truth: bool, sens: float, spec: float, rng: random.Random) -> bool:
    return rng.random() < (sens if truth else 1 - spec)


def generate(regime: str, seed: int, n: int) -> list[Case]:
    if regime not in {'matched','source_degradation','prior_shift'}:
        raise ValueError('Unknown regime')
    if n <= 0: raise ValueError('Positive number of cases needed')
    rng=random.Random(seed)
    cases=[]
    for _ in range(n):
        prior=rng.choice([.16,.30,.44,.55,.68,.76,.83,.91])
        ground_prior=prior if regime!='prior_shift' else .65*prior+.35*.5
        truth=rng.random()<ground_prior
        original=EvidenceChannel('official_or_partner','initial_org',.80,.79,0,True,True)
        cheap=EvidenceChannel('cheap','independent_cheap',.66,.65,.01,True)
        medium=EvidenceChannel('medium','independent_medium',.82,.81,.045,True)
        strong=EvidenceChannel('strong','independent_strong',.95,.94,.095,True)
        echo=EvidenceChannel('copied_post','initial_org',.99,.99,.0001,True)
        unlicensed=EvidenceChannel('unlicensed','no_rights',.999,.999,0,False)
        channels=(original,cheap,medium,strong,echo,unlicensed)
        degrade=.22 if regime=='source_degradation' else 0
        def observe(ch):
            return _draw_sensor(truth,max(.5,ch.sensitivity-degrade),
                                max(.5,ch.specificity-degrade),rng)
        first=observe(original)
        # Syndicated text intentionally copies the same underlying observation.
        # Never treated as a second independent vote.
        hits=(Observation(original.id,original.publisher_root,first),
              Observation(echo.id,echo.publisher_root,first))
        responses={ch.id:observe(ch) for ch in (cheap,medium,strong)}
        cases.append(Case(prior,truth,hits,channels,responses))
    return cases


def one_case(case: Case, policy: str, cfg: dict) -> dict:
    utility=cfg['decision_utility']
    step=route_research(case.prior,case.existing,case.channels,
                        budget=cfg['check_budget'],utility=utility,mode=policy)
    if step.action=='HUMAN_REVIEW':raise AssertionError('Synthetic generator should not emit contradictions')
    checked=False;cost=0.;posterior=step.belief.probability
    if step.action=='VERIFY':
        checked=True
        ch=next(c for c in case.channels if c.id==step.selected_probe)
        if not ch.approved or ch.publisher_root in step.belief.independent_roots:
            raise AssertionError('Forbidden evidence request')
        cost=ch.cost
        final=route_research(case.prior,case.existing+(
            Observation(ch.id,ch.publisher_root,case.responses[ch.id]),),
            case.channels,budget=0,utility=utility,mode='never')
        posterior=final.belief.probability
        outcome=final.action
    else:
        outcome=step.action
    is_accept=outcome=='LAB_ACCEPT'
    realized=(utility['reward_true'] if case.truth else -utility['penalty_false']) if is_accept else 0
    return {'utility':realized-cost,'accepted':is_accept,'false_accept':is_accept and not case.truth,
            'check':checked,'cost':cost,'brier':(posterior-int(case.truth))**2,
            'prior':case.prior, 'posterior':posterior,'truth':case.truth,
            'selected_probe':step.selected_probe, 'result':outcome}


def summarize(rows: list[dict]) -> dict:
    n=len(rows);a=sum(r['accepted'] for r in rows);bad=sum(r['false_accept'] for r in rows)
    return {'cases':n,
            'utility_per_case':round(statistics.mean(r['utility'] for r in rows),6),
            'accepted_fraction':round(a/n,6),
            'false_accept_fraction':round(bad/a,6) if a else None,
            'checks_per_case':round(statistics.mean(r['check'] for r in rows),6),
            'research_cost_per_case_utility_units':round(statistics.mean(r['cost'] for r in rows),6),
            'brier_score':round(statistics.mean(r['brier'] for r in rows),6)}


def paired_bootstrap(a: list[dict], b: list[dict], seed: int = 2702, draws: int=750) -> dict:
    differences=[x['utility']-y['utility'] for x,y in zip(a,b)]
    rng=random.Random(seed)
    means=sorted(statistics.mean(rng.choices(differences,k=len(differences))) for _ in range(draws))
    return {'mean_voi_minus_never':round(statistics.mean(differences),6),
            'conditional_simulation_CI95':[round(means[int(draws*.025)],6),round(means[int(draws*.975)],6)],
            'draws':draws,'interpretation':'Only repeated draws under this synthetic simulator, NOT field guarantee'}


def run(cfg: dict | None=None) -> dict:
    cfg = cfg or json.loads(PROTOCOL.read_text(encoding='utf-8'))
    results={}
    for offset,regime in enumerate(cfg['regimes']):
        cases=generate(regime,cfg['seed']+offset,cfg['cases_per_regime'])
        runs={policy:[one_case(c,policy,cfg) for c in cases] for policy in cfg['policies']}
        results[regime]={'methods':{p:summarize(data) for p,data in runs.items()},
                         'voi_vs_never':paired_bootstrap(runs['voi'],runs['never'],cfg['seed']+offset+700)}
    return {'study':'KEP-SCI-001','protocol':cfg,'regimes':results,
            'real_source_validation':False,'real_model_calls':0,'licensed_city_scrapes':0,
            'results_are_comparative_under_own_simulator':True,
            'note':'The posterior is only as good as source reliability, independence and prior assumptions. No automatic publish.'}


if __name__=='__main__':
    print(json.dumps(run(),ensure_ascii=False,indent=2))
