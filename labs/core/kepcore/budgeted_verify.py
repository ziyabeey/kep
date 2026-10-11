"""KEP-CORE-002: optional synthetic budgeted evidence decision, never a fetch.

Reuses original factual Core and CORE-001 temporal root state before applying
KEP-SCI-001's explicitly assumed Bayesian source reliability & decision utility.
An acquisition is ONLY PROPOSED, never executed. The choice itself cannot
change rights, factual claims, model selections or consumer publication.

One predeclared, independent, affordable and deadline-feasible research check
may be selected for ONE candidate with ONE fresh positive original source.
This constraint is deliberate: it models the final corroboration step, not
full multi-step active learning or a production model.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import isfinite

from .core import Query
from .evidence_lab import (EvidenceChannel, Observation, _prob, bayes_update,
                           expected_information_gain, fuse_roots, action_utility)
from .temporal_pipeline import run_pipeline, _validate_roots

POLICY='KEP-CORE-002-ONE-STEP-SYNTHETIC-VOI-v1'
MODES=('voi','cheapest','max_information','always_strong','never')
MAX_OPTIONS=32
MAX_WAIT_MINUTES=60


@dataclass(frozen=True)
class CheckOption:
    channel: EvidenceChannel
    latency_minutes: int

    def __post_init__(self):
        if not isinstance(self.channel,EvidenceChannel):
            raise TypeError('Validated experimental evidence channel required')
        if type(self.latency_minutes) is not int or not 0 <= self.latency_minutes <= 1440:
            raise ValueError('Invalid hypothetical sensor response latency')


@dataclass(frozen=True)
class ResearchPlan:
    action: str
    core_action: str
    evidence_status: str
    probe_id: str | None
    probe_root: str | None
    estimated_latency_minutes: int | None
    proposed_cost: float
    assumed_expected_net_gain: float
    assumed_current_probability: float | None
    budget_units: float
    simulated_max_wait_minutes: int
    policy: str = POLICY
    one_check_limit: int = 1
    laboratory_only: bool = True
    authorized_to_fetch: bool = False
    consumer_publish: bool = False
    model_used: bool = False
    real_world_accuracy: float | None = None
    physical_business_openings: int | None = None
    physical_business_closures: int | None = None


def plan_research(catalog, q, signals, options, *, observed_channels,
                  approved_roots, prior, budget, max_wait_minutes,
                  policy='voi') -> ResearchPlan:
    """Plan one optional step, without looking at any prospective observation.

    Assumed source sensitivity/specificity are NOT calibrated from Istanbul or
    business data. Do not interpret modeled posterior as a truth probability.
    """
    if (not isinstance(catalog,(list,tuple)) or len(catalog)!=1 or
            not isinstance(catalog[0],dict) or not isinstance(q,Query)):
        raise ValueError('Only one valid synthetic research candidate supported')
    _prob(prior)
    if policy not in MODES:
        raise ValueError('Unknown experimental routing policy')
    if (type(budget) not in (float,int) or not isfinite(budget) or
            not 0<=budget<=1):
        raise ValueError('Invalid bounded utility-unit check budget')
    if type(max_wait_minutes) is not int or not 0<=max_wait_minutes<=MAX_WAIT_MINUTES:
        raise ValueError('Invalid user-visible simulated decision deadline')
    if not isinstance(options,(tuple,list)) or len(options)>MAX_OPTIONS:
        raise ValueError('Bounded check-option tuple required')
    if not isinstance(observed_channels,(tuple,list)) or len(observed_channels)>64:
        raise ValueError('Bounded current source model required')
    if any(not isinstance(ch,EvidenceChannel) for ch in observed_channels):
        raise ValueError('Invalid assumed current source channel')
    if any(not isinstance(o,CheckOption) for o in options):
        raise ValueError('Unvalidated prospective check option')
    roots=_validate_roots(approved_roots)
    if (len({c.id for c in observed_channels})!=len(observed_channels) or
            len({c.publisher_root for c in observed_channels})!=len(observed_channels) or
            len({x.channel.id for x in options})!=len(options) or
            len({x.channel.publisher_root for x in options})!=len(options)):
        raise ValueError('Ambiguous observed or prospective source authority')
    if set(c.id for c in observed_channels)&set(x.channel.id for x in options):
        raise ValueError('Duplicate old/new channel ID')

    base=run_pipeline([catalog[0]],q,list(signals),approved_roots=roots)
    core_action=base['base_action']
    eid=catalog[0]['id']
    state=base['evidence'].get(eid,{'status':'NOT_EVALUATED',
                                   'positive_roots':[],'negative_roots':[]})
    status=state['status']

    def result(action,option=None,gain=0.,p=None):
        return ResearchPlan(action=action,core_action=core_action,
            evidence_status=status,
            probe_id=option.channel.id if option else None,
            probe_root=option.channel.publisher_root if option else None,
            estimated_latency_minutes=option.latency_minutes if option else None,
            proposed_cost=round(option.channel.cost,9) if option else 0.,
            assumed_expected_net_gain=round(gain,9),
            assumed_current_probability=round(p,9) if p is not None else None,
            budget_units=float(budget),simulated_max_wait_minutes=max_wait_minutes)

    # Prevent both hard-gate override AND unnecessary probes on already
    # corroborated, conflicting, negative or absent source claims.
    if core_action not in {'DISCOVER','RECOMMEND'}:
        return result('CORE_REFUSED')
    if status=='MULTI_ROOT_SUPPORT':
        return result('NO_CHECK_ALREADY_SUPPORTED')
    if status in {'DISPUTED','NEGATIVE_REPORTS_REQUIRE_REVIEW'}:
        return result('HUMAN_REVIEW')
    if status!='ONE_ROOT_ONLY':
        return result('NO_CHECK_NO_INDEPENDENT_SEED')
    if policy=='never':
        return result('NO_CHECK_POLICY')

    used=state['positive_roots']
    if len(used)!=1:
        raise ValueError('One-root evidence state contradicts its authority')
    old={c.publisher_root:c for c in observed_channels}
    if used[0] not in old or not old[used[0]].approved or used[0] not in roots:
        raise ValueError('Current root is uncalibrated or not approved for research')
    belief=fuse_roots(prior,[Observation(old[used[0]].id,used[0],True)],
                      tuple(observed_channels))
    if belief.status!='modeled' or belief.independent_roots!=(used[0],):
        raise ValueError('Modeled evidence does not match observed source roots')
    p=belief.probability
    candidates=[]
    for option in options:
        ch=option.channel
        if (not ch.approved or ch.publisher_root not in roots or
                ch.publisher_root in used or ch.cost>budget or
                option.latency_minutes>max_wait_minutes):
            continue
        # The final positive root MUST make a real difference to the same
        # two-root gate used by CORE-001. After a negative response we abstain.
        p_yes=p*ch.sensitivity+(1-p)*(1-ch.specificity)
        conditional_yes=bayes_update(p,ch,True)
        net=p_yes*action_utility(conditional_yes,
            reward_true=1.,penalty_false=4.,min_probability=.8)[1]-ch.cost
        entropy_gain=expected_information_gain(p,ch)
        candidates.append((option,net,entropy_gain))
    if not candidates:
        return result('NO_CHECK_NO_ELIGIBLE_PROBE',p=p)
    if policy=='voi':
        option,gain,_=sorted(candidates,key=lambda x:(-x[1],x[0].channel.id))[0]
        if gain<=1e-12:
            return result('NO_CHECK_LOW_VALUE',p=p)
    elif policy=='cheapest':
        option,gain,_=sorted(candidates,key=lambda x:(x[0].channel.cost,x[0].channel.id))[0]
    elif policy=='max_information':
        option,gain,_=sorted(candidates,key=lambda x:(-x[2],x[0].channel.id))[0]
    else:  # always_strong, explicitly ignores cost effectiveness
        option,gain,_=sorted(candidates,key=lambda x:(
            -(x[0].channel.sensitivity+x[0].channel.specificity),
            x[0].channel.id))[0]
    return result('PROPOSE_CHECK',option,gain,p)
