"""KEP-CORE-003: causal synthetic-only source audits and uncertainty-aware routing.

Audit labels are INDEPENDENTLY GENERATED SYNTHETIC historical outcomes. This
code neither authenticates humans nor learns real provider reliability.
Only source audits adjudicated before the query can affect the *next* proposal.
All hard Core, as-of, publisher independence and consent guards are reused.

Prospective sensor responses and the current case's hidden truth are NEVER
an input to this module. This returns a plan; it does not fetch anything.
"""
from __future__ import annotations
from dataclasses import dataclass, replace
from datetime import timedelta
from math import sqrt

from .calibration import aware
from .evidence_lab import EvidenceChannel
from .budgeted_verify import CheckOption, plan_research
from .temporal_pipeline import _identifier, _validate_roots

POLICY='KEP-CORE-003-CAUSAL-SYNTHETIC-CALIBRATION-v1'
MODES=('fixed','posterior_mean','conservative')
MAX_AUDITS=20_000
MIN_WINDOW_HOURS=1
MAX_WINDOW_HOURS=24*30
LOWER_ROOT_GATE=.62


@dataclass(frozen=True)
class AuditFeedback:
    audit_id:str
    entity_id:str
    publisher_root:str
    observed_at:str
    adjudicated_at:str
    supports:bool
    truth:bool
    origin:str='synthetic_independent_audit'
    sampling:str='independent_uniform'

    def __post_init__(self):
        for field in ('audit_id','entity_id','publisher_root'):
            _identifier(getattr(self,field),field)
        if type(self.supports) is not bool or type(self.truth) is not bool:
            raise ValueError('Audited signal and independent truth must be Boolean')
        if (self.origin!='synthetic_independent_audit' or
                self.sampling!='independent_uniform'):
            raise ValueError('Only independently sampled synthetic audit history allowed')
        if aware(self.adjudicated_at)<aware(self.observed_at):
            raise ValueError('Future truth cannot be adjudicated before source observation')


@dataclass(frozen=True)
class RootEstimate:
    publisher_root:str
    observations_used:int
    positive_truth_n:int
    negative_truth_n:int
    sensitivity_mean:float
    specificity_mean:float
    sensitivity_lower:float
    specificity_lower:float
    status:str
    real_world_calibrated:bool=False


def _wilson_lower(success:int, total:int)->float:
    """One-sided conservative lower end of nominal 95% Wilson two-sided band.

    Requires independently reviewed Bernoulli cases; the simulator imposes
    those assumptions, but field reality does NOT supply them yet.
    """
    if total<=0:
        return 0.
    z=1.96
    observed=success/total
    denom=1+z*z/total
    lower=(observed+z*z/(2*total)-
           z*sqrt(observed*(1-observed)/total+z*z/(4*total*total)))/denom
    return max(0.,min(1.,lower))


def estimate_sources(audits, *, as_of:str, approved_roots,
                     exclude_entity_id:str|None=None,
                     window_hours:int=96,min_class_n:int=12)->dict[str,RootEstimate]:
    """Use only already available, independent, recent audit truth.

    Reposts from the SAME (publisher_root, entity_id) are ONE audited case.
    The most recent actual observation wins; contradictory same-timestamp
    ballots or reused audit IDs with differing payload are rejected.
    Unknown roots, future adjudications and out-of-window cases do not count.
    """
    cutoff=aware(as_of)
    roots=_validate_roots(approved_roots)
    if (type(window_hours) is not int or not MIN_WINDOW_HOURS<=window_hours<=MAX_WINDOW_HOURS
            or type(min_class_n) is not int or not 1<=min_class_n<=1000):
        raise ValueError('Unreviewed calibration window or sample threshold')
    if exclude_entity_id is not None:
        _identifier(exclude_entity_id,'excluded candidate ID')
    if not isinstance(audits,(list,tuple)) or len(audits)>MAX_AUDITS:
        raise ValueError('Bounded historical independent audits required')
    unique={}
    for a in audits:
        if not isinstance(a,AuditFeedback):
            raise ValueError('Only validated synthetic historical audit envelopes')
        if exclude_entity_id is not None and a.entity_id==exclude_entity_id:
            raise ValueError('The case being decided cannot carry its own truth label')
        old=unique.get(a.audit_id)
        if old is not None and old!=a:
            raise ValueError('Reused audit ID with conflicting labels')
        unique[a.audit_id]=a

    window_start=cutoff-timedelta(hours=window_hours)
    per_key={}
    for a in unique.values():
        if a.publisher_root not in roots:
            continue
        t=aware(a.observed_at);verified=aware(a.adjudicated_at)
        if verified>cutoff or t>cutoff or t<window_start:
            continue
        key=(a.publisher_root,a.entity_id)
        prior=per_key.get(key)
        if prior is None or t>aware(prior.observed_at):
            per_key[key]=a
        elif t==aware(prior.observed_at):
            if (a.supports,a.truth)!=(prior.supports,prior.truth):
                raise ValueError('Contradictory copied audit at same source clock')
            if (verified, a.audit_id)<(aware(prior.adjudicated_at),prior.audit_id):
                per_key[key]=a

    by_root={root:[] for root in roots}
    for a in per_key.values():
        by_root[a.publisher_root].append(a)
    result={}
    for root in roots:
        rows=by_root[root]
        yes=[a for a in rows if a.truth]
        no=[a for a in rows if not a.truth]
        tp=sum(a.supports for a in yes)
        tn=sum(not a.supports for a in no)
        # Beta(2,2) prior is a SIMULATION SMOOTHER, not field calibration.
        sens=(tp+2)/(len(yes)+4)
        spec=(tn+2)/(len(no)+4)
        lower_s=_wilson_lower(tp,len(yes))
        lower_t=_wilson_lower(tn,len(no))
        result[root]=RootEstimate(
            root,len(rows),len(yes),len(no),
            sens,spec,lower_s,lower_t,
            'READY' if len(yes)>=min_class_n and len(no)>=min_class_n
            else 'INSUFFICIENT_CLASS_SUPPORT')
    return result


def plan_adaptive(catalog,q,signals,options,*,observed_channels,
                  approved_roots,prior,budget,max_wait_minutes,
                  audits,mode='conservative',window_hours:int=96,
                  min_class_n:int=12):
    """Only modify modeled check quality from PAST synthetic independent audits.

    No ordinary source claim is equivalent to a ground-truth adjudication.
    Missing or uncertain calibration is a NO_CHECK proposal, not a path to
    accepting a source's unverified existence claim.
    """
    if mode not in MODES:
        raise ValueError('Unknown temporal source reliability policy')
    # CORE-002 validates hard policy and causal evidence before an optional
    # cost calculation. Calling it with 'never' does not trigger I/O.
    baseline=plan_research(catalog,q,signals,options,
        observed_channels=observed_channels,approved_roots=approved_roots,
        prior=prior,budget=budget,max_wait_minutes=max_wait_minutes,
        policy='never')
    if mode=='fixed':
        return plan_research(catalog,q,signals,options,
            observed_channels=observed_channels,approved_roots=approved_roots,
            prior=prior,budget=budget,max_wait_minutes=max_wait_minutes,
            policy='voi')
    if baseline.action!='NO_CHECK_POLICY':
        return replace(baseline,policy=POLICY+'-'+mode)

    from .temporal_pipeline import evidence_snapshot
    root_state=evidence_snapshot(signals,as_of=q.at,
        entity_ids=[catalog[0]['id']],approved_roots=approved_roots)[catalog[0]['id']]
    used=root_state['positive_roots']
    if root_state['status']!='ONE_ROOT_ONLY' or len(used)!=1:
        raise ValueError('Unexpected one-root-only scenario')
    history=estimate_sources(audits,as_of=q.at,approved_roots=approved_roots,
        exclude_entity_id=catalog[0]['id'],
        window_hours=window_hours,min_class_n=min_class_n)
    seed=history[used[0]]
    if seed.status!='READY':
        return replace(baseline,action='NO_CHECK_INSUFFICIENT_AUDITS',
                       policy=POLICY+'-'+mode)
    if mode=='conservative' and min(seed.sensitivity_lower,seed.specificity_lower)<LOWER_ROOT_GATE:
        return replace(baseline,action='NO_CHECK_UNCERTAIN_ORIGIN',
                       policy=POLICY+'-'+mode)

    def rates(root):
        a=history[root]
        if a.status!='READY':
            return None
        s,t=(a.sensitivity_mean,a.specificity_mean) if mode=='posterior_mean' else (
            a.sensitivity_lower,a.specificity_lower)
        if mode=='conservative' and min(s,t)<LOWER_ROOT_GATE:
            return None
        return (max(.001,min(.999,s)),max(.001,min(.999,t)))

    rewritten_sources=[]
    for ch in observed_channels:
        estimate=rates(ch.publisher_root)
        # Only the used one-root source needs learned rates for this step.
        if ch.publisher_root==used[0] and estimate is None:
            return replace(baseline,action='NO_CHECK_INSUFFICIENT_AUDITS',
                           policy=POLICY+'-'+mode)
        rewritten_sources.append(replace(ch,sensitivity=estimate[0],
               specificity=estimate[1]) if estimate else ch)

    rewritten_options=[]
    for option in options:
        ch=option.channel
        estimate=rates(ch.publisher_root) if ch.publisher_root in history else None
        if not ch.approved or estimate is None:
            continue
        rewritten_options.append(replace(option,channel=replace(ch,
                         sensitivity=estimate[0],specificity=estimate[1])))
    if not rewritten_options:
        return replace(baseline,action='NO_CHECK_INSUFFICIENT_OR_UNCERTAIN_PROBES',
                       policy=POLICY+'-'+mode)
    plan=plan_research(catalog,q,signals,rewritten_options,
        observed_channels=rewritten_sources,approved_roots=approved_roots,
        prior=prior,budget=budget,max_wait_minutes=max_wait_minutes,
        policy='voi')
    return replace(plan,policy=POLICY+'-'+mode)
