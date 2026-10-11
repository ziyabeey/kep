"""CORE-004A experimental outage grace, only for LAB source checks.

This is NOT a production trust override. It may propose one bounded synthetic
sensor check when CORE-003 withheld the check solely for insufficient recent
independent audit samples. Older, independently sampled, already-adjudicated
audits may support a SHORT grace interval; past quality is still uncertain.

The only effect is an optional proposal. Core's rights/factual/time veto,
uncertain-origin veto, source independence, budget, deadline and no-fetch
policy remain STRICT. A proposal never proves physical business existence.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

from .adaptive_trust import (AuditFeedback,estimate_sources,plan_adaptive,
                             LOWER_ROOT_GATE)
from .calibration import aware
from .temporal_pipeline import evidence_snapshot

POLICY='KEP-CORE-004A-SHORT-HISTORICAL-GRACE-LAB-v1'
RESCUE=frozenset(('NO_CHECK_INSUFFICIENT_AUDITS',
                  'NO_CHECK_INSUFFICIENT_OR_UNCERTAIN_PROBES'))


def plan_outage_grace(catalog,q,signals,options,*,observed_channels,
                      approved_roots,prior,budget,max_wait_minutes,audits,
                      short_window_hours:int=72,long_window_hours:int=168,
                      grace_hours:int=48,min_class_n:int=12):
    """Choose at most one legal check using RECENT PAST independent audit truth.

    No future adjudications, same-entity labels, unlicensed candidates, unseen
    vendor identities or observed-sensor failures may be made invisible. The
    currently conservative model is authoritative whenever it already has a
    decision; it may be relaxed ONLY on missing/insufficient audit volume.
    """
    if (type(short_window_hours) is not int or not 1<=short_window_hours<=720
            or type(long_window_hours) is not int
            or not short_window_hours<long_window_hours<=720
            or type(grace_hours) is not int or not 1<=grace_hours<=72
            or type(min_class_n) is not int or not 1<=min_class_n<=1000):
        raise ValueError('Non-preregistered historical audit safety windows')

    args=dict(observed_channels=observed_channels,approved_roots=approved_roots,
              prior=prior,budget=budget,max_wait_minutes=max_wait_minutes,
              audits=audits,min_class_n=min_class_n)
    baseline=plan_adaptive(catalog,q,signals,options,
                           mode='conservative',window_hours=short_window_hours,
                           **args)
    if baseline.action not in RESCUE:
        # NEVER relax CORE_REFUSED / HUMAN_REVIEW / NO_CHECK_UNCERTAIN_ORIGIN,
        # or a already-supported claim. This is also the normal no-outage path.
        return replace(baseline,policy=POLICY)

    if not isinstance(catalog,(list,tuple)) or len(catalog)!=1:
        raise ValueError('Only one prequalified synthetic Core record')
    candidate_id=catalog[0]['id']
    cutoff=aware(q.at)
    long_history=estimate_sources(
        audits,as_of=q.at,approved_roots=approved_roots,
        exclude_entity_id=candidate_id,
        window_hours=long_window_hours,min_class_n=min_class_n)
    state=evidence_snapshot(signals,as_of=q.at,
        entity_ids=[candidate_id],
        approved_roots=approved_roots)[candidate_id]
    if state['status']!='ONE_ROOT_ONLY' or len(state['positive_roots'])!=1:
        return replace(baseline,policy=POLICY)

    origin=state['positive_roots'][0]
    recent_roots=set()
    for audit in audits:
        if not isinstance(audit,AuditFeedback):
            # estimate_sources has already validated all records too.
            raise ValueError('Unexpected non-independent history')
        verified=aware(audit.adjudicated_at)
        observed=aware(audit.observed_at)
        if (audit.entity_id!=candidate_id and verified<=cutoff
                and observed<=cutoff
                and cutoff-verified<=timedelta(hours=grace_hours)
                and cutoff-observed<=timedelta(hours=long_window_hours)):
            recent_roots.add(audit.publisher_root)

    def eligible(root:str)->bool:
        model=long_history.get(root)
        return bool(
            root in recent_roots and model is not None
            and model.status=='READY'
            and min(model.sensitivity_lower,
                    model.specificity_lower)>=LOWER_ROOT_GATE)

    if not eligible(origin):
        return replace(baseline,action='NO_CHECK_GRACE_ORIGIN_UNCERTAIN',
                       policy=POLICY)

    fresh_options=tuple(option for option in options
                        if eligible(option.channel.publisher_root))
    if not fresh_options:
        return replace(baseline,action='NO_CHECK_GRACE_NO_SAFE_PROBE',
                       policy=POLICY)

    candidate=plan_adaptive(
        catalog,q,signals,fresh_options,
        mode='conservative',window_hours=long_window_hours,**args)
    return replace(candidate,policy=POLICY)
