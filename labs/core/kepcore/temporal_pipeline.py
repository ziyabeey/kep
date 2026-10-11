"""KEP-CORE-001: time-aware synthetic/research decision pipeline.

Combines EXISTING Core hard query/rights gates and structured model boundary
with independent publisher-root evidence. No learning, network, live labels,
source-data refresh, production authorization or numerical truth probability.

A second copy from the same publisher can never create independent support.
Time of observation and time of system availability are both enforced, so
out-of-order arrival cannot leak future information into an earlier decision.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import timedelta

from .calibration import aware
from .core import Query, Decision, decide, stable_hash
from .model_boundary import context_for_model

POLICY = 'KEP-CORE-001-TEMPORAL-ROOT-REPLAY-v1'
DEFAULT_TTL_HOURS = 48
MAX_TTL_HOURS = 720
MAX_EVENTS = 20_000


def _identifier(value, field):
    if (type(value) is not str or not value or not value.strip() or
            value!=value.strip() or len(value)>128 or any(ord(ch)<32 for ch in value)):
        raise ValueError('Invalid '+field)
    return value


@dataclass(frozen=True)
class Signal:
    """Source says an entity exists, NOT a true existence/closure label.

    observed_at is when that claim was observed by source;
    available_at is when KEP could first use it.
    """
    event_id: str
    entity_id: str
    publisher_root: str
    observed_at: str
    available_at: str
    supports: bool
    rights_scope: str = 'research_ingest'

    def __post_init__(self):
        for f in ('event_id','entity_id','publisher_root'):
            _identifier(getattr(self,f), f)
        if type(self.supports) is not bool:
            raise ValueError('Source support must be a boolean claim')
        if self.rights_scope not in {'research_ingest','blocked'}:
            raise ValueError('Unreviewed signal rights scope')
        obs=aware(self.observed_at)
        available=aware(self.available_at)
        if available<obs:
            raise ValueError('Claim available before it was observed')


def _validate_roots(approved_roots) -> tuple[str,...]:
    if not isinstance(approved_roots,(tuple,list,frozenset,set)):
        raise ValueError('Explicit reviewed roots required')
    roots=tuple(sorted(approved_roots))
    if (not roots or len(roots)>64 or len(roots)!=len(set(roots)) or
            any(_identifier(r,'approved root')!=r for r in roots)):
        raise ValueError('Missing or ambiguous publisher-root authority')
    return roots


def evidence_snapshot(signals, *, as_of: str, entity_ids,
                      approved_roots, ttl_hours: int=DEFAULT_TTL_HOURS) -> dict:
    """Collapse available, fresh observations per independent publisher root.

    The latest observation timestamp takes precedence over arrival order.
    Equal-clock contradictions within one source remain disputed. Negative
    claims can create a HUMAN REVIEW queue, never physical closure facts.
    """
    cutoff=aware(as_of)
    if (type(ttl_hours) is not int or not 1<=ttl_hours<=MAX_TTL_HOURS):
        raise ValueError('Invalid observation age cutoff')
    roots=_validate_roots(approved_roots)
    if not isinstance(entity_ids,(list,tuple)) or len(entity_ids)>50:
        raise ValueError('Bounded ordered candidate IDs required')
    for entity_id in entity_ids:
        _identifier(entity_id,'candidate ID')
    if len(entity_ids)!=len(set(entity_ids)):
        raise ValueError('Repeated candidate ID')
    if not isinstance(signals,(list,tuple)) or len(signals)>MAX_EVENTS:
        raise ValueError('Unbounded or malformed source events')
    unique={}
    for event in signals:
        if not isinstance(event,Signal):
            raise ValueError('Only validated source events are accepted')
        old=unique.get(event.event_id)
        if old is not None and old!=event:
            raise ValueError('Conflicting reuse of source event identity')
        unique[event.event_id]=event

    minimum=cutoff-timedelta(hours=ttl_hours)
    by_entity={eid:{} for eid in entity_ids}
    available_seen={eid:False for eid in entity_ids}
    for event in unique.values():
        if event.entity_id not in by_entity:
            continue
        available_seen[event.entity_id]=True
        if event.rights_scope!='research_ingest' or event.publisher_root not in roots:
            continue
        observed=aware(event.observed_at)
        available=aware(event.available_at)
        if observed>cutoff or available>cutoff or observed<minimum:
            continue
        grouped=by_entity[event.entity_id].setdefault(event.publisher_root,[])
        grouped.append((observed,event.supports))

    result={}
    for entity_id in entity_ids:
        positive=[];negative=[];contradictory=[];latest={}
        for root,items in sorted(by_entity[entity_id].items()):
            newest=max(t for t,_ in items)
            votes={supports for t,supports in items if t==newest}
            if len(votes)>1:
                contradictory.append(root)
                latest[root]=['disputed',newest.isoformat()]
            else:
                agree=votes.pop()
                (positive if agree else negative).append(root)
                latest[root]=[agree,newest.isoformat()]
        distinct=sorted(latest)
        if contradictory or (positive and negative):
            status='DISPUTED'
        elif negative:
            status='NEGATIVE_REPORTS_REQUIRE_REVIEW'
        elif len(positive)>=2:
            status='MULTI_ROOT_SUPPORT'
        elif len(positive)==1:
            status='ONE_ROOT_ONLY'
        elif available_seen[entity_id]:
            status='STALE_OR_UNAVAILABLE'
        else:
            status='NO_EVIDENCE'
        result[entity_id]={
            'status':status,
            'independent_roots':distinct,
            'positive_roots':positive,
            'negative_roots':negative,
            'contradictory_roots':contradictory,
            'effective_latest_claims':latest,
            'consumed_source_messages_not_independent_votes':True,
            'physical_truth_established':False,
        }
    return result


def run_pipeline(catalog: list[dict], q: Query, signals,
                 *, approved_roots, ttl_hours: int=DEFAULT_TTL_HOURS) -> dict:
    """Core eligibility FIRST; evidence research overlay SECOND; model context LAST.

    This module NEVER promotes research observations to consumer publication.
    It also does not change Core's default suitability, rights or query policy.
    """
    if not isinstance(catalog,list) or len(catalog)>50:
        raise ValueError('Bounded synthetic lab catalog required')
    if not isinstance(q,Query):
        raise TypeError('Validated Query required')
    ids=[r['id'] for r in catalog]
    if len(ids)!=len(set(ids)):
        raise ValueError('Duplicate catalog candidate IDs')
    base=decide(catalog,q)
    selected=[row['id'] for row in base.selected]
    evidence=evidence_snapshot(signals,as_of=q.at,entity_ids=selected,
                               approved_roots=approved_roots,ttl_hours=ttl_hours)
    corroborated=[row for row in base.selected
                  if evidence[row['id']]['status']=='MULTI_ROOT_SUPPORT']
    # The model receives only the subset allowed by BOTH preexisting core
    # hard gates and new research-side root/temporal checks.
    guarded=[]
    for row in corroborated:
        guarded.append({**row,'caveats':list(dict.fromkeys(row['caveats']+
            ['UNCALIBRATED_SOURCE_CORROBORATION_NOT_PHYSICAL_PROOF']))})
    action=('CORE_REFUSED' if base.action not in {'DISCOVER','RECOMMEND'}
            else ('LAB_CORROBORATED' if guarded else 'LAB_ABSTAIN'))
    gate=Decision(action,guarded,base.reasons,base.considered,base.blocked,
                  model_used=False,policy_version=POLICY)
    context=context_for_model(gate)
    snap=stable_hash({
        'policy':POLICY, 'as_of':q.at, 'query':asdict(q),
        'base_action':base.action,'eligible_ids':selected,'evidence':evidence,
        'allowed_model_ids':[r['id'] for r in guarded],
        'ttl_hours':ttl_hours,
    })
    return {
        'policy':POLICY, 'action':action, 'base_action':base.action,
        'selected_ids':[r['id'] for r in guarded],
        'evidence':evidence, 'core_blocked':base.blocked,
        'snapshot_sha256':snap, 'model_context':context,
        'model_used':False,'consumer_publish':False,
        'laboratory_only':True,'real_world_accuracy':None,
        'official_source_agreement':None,'physical_openings':None,
        'physical_closures':None,
        'unseen_catalog_candidates_not_certified':True,
    }
