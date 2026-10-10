"""KEP-SCI-002 | Temporal claim reliability calibration research ONLY.

A correct source quote is not a verified occurrence; a model's self-reported
confidence is not a probability. This module scores independently adjudicated
FIELD claims, records abstention risk and enforces time-available evidence.
Never use its thresholds to auto-publish events, send push, or grant source rights.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from math import isfinite, sqrt
from collections import defaultdict
import re
import json
from pathlib import Path

FIELDS = frozenset({'starts_at', 'venue', 'price', 'cancelled', 'opening_hours'})
OUTCOMES = frozenset({'correct', 'incorrect', 'unknown', 'superseded'})
ORIGINS = frozenset({'human_review', 'synthetic'})


def aware(timestamp: str) -> datetime:
    """Parse chronological timestamps; naive clocks are rejected."""
    if not isinstance(timestamp, str):
        raise ValueError('Timestamp must be an ISO 8601 string')
    try:
        result = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
    except ValueError as exc:
        raise ValueError('Invalid ISO timestamp') from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError('Timezone-aware timestamp required')
    return result


@dataclass(frozen=True)
class ReviewedClaim:
    claim_id: str
    entity_id: str
    field: str
    publisher_root: str
    source_id: str
    city: str
    claimed_at: str | None
    observed_at: str
    predicted_at: str
    checked_at: str
    snapshot_sha256: str
    rights_scope: str
    outcome: str
    reviewer_id: str
    evidence_ref: str
    origin: str

    def __post_init__(self):
        for key in ('claim_id','entity_id','publisher_root','source_id','city','reviewer_id','evidence_ref'):
            x = getattr(self, key)
            if not isinstance(x,str) or not x.strip():
                raise ValueError(f'{key} must be nonempty')
        if self.field not in FIELDS or self.outcome not in OUTCOMES or self.origin not in ORIGINS:
            raise ValueError('Unrecognized field/outcome/origin')
        predicted, observed, checked=aware(self.predicted_at),aware(self.observed_at),aware(self.checked_at)
        if observed > predicted or checked < predicted:
            raise ValueError('Observation, prediction and adjudication timestamps are out of order')
        if self.claimed_at is not None and aware(self.claimed_at) > observed:
            raise ValueError('Claim cannot be published after its first observation')
        if not re.fullmatch(r'[0-9a-f]{64}', self.snapshot_sha256):
            raise ValueError('Immutable source snapshot SHA256 required')
        if self.rights_scope != 'research_ingest':
            raise PermissionError('Calibration only accepts approved research-use records')
        if self.origin == 'human_review':
            if not self.evidence_ref.startswith('https://') or self.reviewer_id.lower() in {'ai','model','simulator','unknown'}:
                raise ValueError('Human claims need independent reviewer and source URL')
        elif not self.evidence_ref.startswith('synthetic:'):
            raise ValueError('Synthetic fixture must be explicitly marked')

    @property
    def grouping(self):
        return (self.entity_id, self.field)

    @property
    def resolved(self):
        return self.outcome in {'correct','incorrect'}

    @property
    def correct(self):
        return self.outcome == 'correct'


def review_from_dict(v: dict) -> ReviewedClaim:
    expected = set(ReviewedClaim.__dataclass_fields__)
    if set(v) != expected:
        raise ValueError(f'Review schema mismatch: missing {sorted(expected-set(v))}, extra {sorted(set(v)-expected)}')
    return ReviewedClaim(**v)


def load_reviews(path: str | Path) -> list[ReviewedClaim]:
    reviews=[]
    for index, line in enumerate(Path(path).read_text(encoding='utf-8').splitlines(), 1):
        if line.strip():
            try:
                reviews.append(review_from_dict(json.loads(line)))
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                raise ValueError(f'Invalid review line {index}') from exc
    return validated(reviews)


def validated(reviews: list[ReviewedClaim]) -> list[ReviewedClaim]:
    ids=set()
    copies=set()
    for r in reviews:
        if not isinstance(r, ReviewedClaim):
            raise TypeError('ReviewedClaim records only')
        if r.claim_id in ids:
            raise ValueError('Repeated claim identifier')
        ids.add(r.claim_id)
        # A repost from the same publisher must not inflate the sample.
        root_copy=(r.entity_id,r.field,r.publisher_root,aware(r.predicted_at))
        if root_copy in copies:
            raise ValueError('Duplicated publisher-root field observation')
        copies.add(root_copy)
    return sorted(reviews,key=lambda r:(aware(r.predicted_at),r.claim_id))


@dataclass(frozen=True)
class Split:
    train: tuple[ReviewedClaim, ...]
    calibration: tuple[ReviewedClaim, ...]
    test: tuple[ReviewedClaim, ...]
    purged_late_adjudications: int
    purged_cross_split_entities: int
    not_yet_reviewed_test: int
    origin: str


def time_split(reviews: list[ReviewedClaim], *, train_end: str, calibration_end: str,
               evaluation_asof: str, purge_entities: bool=True) -> Split:
    """Global chronological split; labels must exist as of each boundary.

    Groups spanning several stages are excluded from the LATER stage, not
    smuggled into train. Unresolved cases survive as explicit unknowns.
    """
    a,b,c=map(aware,(train_end,calibration_end,evaluation_asof))
    if not a < b < c:
        raise ValueError('Non-increasing temporal boundaries')
    groups=[[],[],[]]
    missing=0
    late=0
    cross=0
    stage_by_entity={}
    origins=set()
    for r in validated(reviews):
        origins.add(r.origin)
        at=aware(r.predicted_at)
        if at>=c: continue
        stage = 0 if at < a else 1 if at < b else 2
        cutoff=(a,b,c)[stage]
        if aware(r.checked_at)>=cutoff:
            late+=1
            if stage==2:missing+=1
            continue
        key=r.grouping
        if purge_entities and key in stage_by_entity and stage_by_entity[key]!=stage:
            cross+=1
            continue
        stage_by_entity.setdefault(key,stage)
        groups[stage].append(r)
    if len(origins)>1:
        raise ValueError('Synthetic and human-reviewed claims cannot be pooled')
    return Split(tuple(groups[0]),tuple(groups[1]),tuple(groups[2]),late,cross,missing,
                 next(iter(origins),'unknown'))


class FieldRootCalibrator:
    """Shrink publisher+field accuracy toward field and global training rates.

    This estimates *historic field-claim correctness*, NOT event attendance,
    popularity, or proof of an individual event's truth.
    """
    def __init__(self, train: tuple[ReviewedClaim, ...], *, min_root_count: int=8,
                 field_pseudocount: float=12., root_pseudocount: float=16.):
        if min_root_count<1 or field_pseudocount<=0 or root_pseudocount<=0:
            raise ValueError('Invalid shrinkage parameters')
        if not train or any(not r.resolved for r in train):
            # unknown and superseded may be present in train, but not treated as wrong.
            train=tuple(r for r in train if r.resolved)
        self.n=len(train)
        self.root_counts=defaultdict(lambda:[0,0])
        self.field_counts=defaultdict(lambda:[0,0])
        for r in train:
            self.root_counts[(r.publisher_root,r.field)][0]+=int(r.correct)
            self.root_counts[(r.publisher_root,r.field)][1]+=1
            self.field_counts[r.field][0]+=int(r.correct)
            self.field_counts[r.field][1]+=1
        self.global_p=(1+sum(int(r.correct) for r in train))/(2+len(train))
        self.min_root_count=min_root_count
        self.field_pseudocount=field_pseudocount
        self.root_pseudocount=root_pseudocount

    def predict(self,r:ReviewedClaim,policy:str='root_field')->float:
        if policy not in {'global','field','root_field'}:
            raise ValueError('Unknown baseline')
        if policy=='global':return self.global_p
        positives,n=self.field_counts[r.field]
        field=(positives+self.field_pseudocount*self.global_p)/(n+self.field_pseudocount)
        if policy=='field':return field
        positives,n=self.root_counts[(r.publisher_root,r.field)]
        if n<self.min_root_count:return field
        return (positives+self.root_pseudocount*field)/(n+self.root_pseudocount)


def wilson_upper(errors:int,n:int,z:float=1.96)->float | None:
    if not isinstance(errors,int) or not isinstance(n,int) or n<0 or errors<0 or errors>n:
        raise ValueError('Invalid binomial counts')
    if n==0:return None
    p=errors/n
    z2=z*z
    return min(1.,(p+z2/(2*n)+z*sqrt(p*(1-p)/n+z2/(4*n*n)))/(1+z2/n))


def select_threshold(rows: tuple[ReviewedClaim,...], model:FieldRootCalibrator, *,
                     target_risk:float=.20,min_published:int=25,policy:str='root_field')->dict:
    if not 0<target_risk<1 or min_published<1:raise ValueError('Invalid risk threshold policy')
    labeled=[r for r in rows if r.resolved]
    if not labeled:
        return {'threshold':None,'reason':'NO_LABELED_CALIBRATION','eligible':0,'observations':0}
    candidates=sorted(set(model.predict(r,policy) for r in labeled))
    selected=None
    for threshold in candidates:
        published=[r for r in labeled if model.predict(r,policy)>=threshold]
        if len(published)<min_published:continue
        bad=sum(not r.correct for r in published)
        upper=wilson_upper(bad,len(published))
        if upper <= target_risk:
            selected={'threshold':round(threshold,12),'reason':'LAB_CALIBRATION_BOUND_ONLY',
                      'eligible':len(published),'observations':len(labeled),'calibration_errors':bad,
                      'calibration_wilson_upper':round(upper,6)}
            break # ascending thresholds -> maximum coverage respecting bound
    return selected or {'threshold':None,'reason':'INSUFFICIENT_EVIDENCE_OR_RISK_TOO_HIGH',
                         'eligible':0,'observations':len(labeled)}


def calibration_bins(rows:tuple[ReviewedClaim,...], model:FieldRootCalibrator,
                     policy:str, n_bins:int=5)->list[dict]:
    bins=[]
    labeled=[r for r in rows if r.resolved]
    for i in range(n_bins):
        members=[r for r in labeled if min(n_bins-1,int(model.predict(r,policy)*n_bins))==i]
        if not members:continue
        bins.append({'interval':[round(i/n_bins,3),round((i+1)/n_bins,3)],
                     'n':len(members),
                     'predicted_mean':round(sum(model.predict(r,policy) for r in members)/len(members),5),
                     'observed_accuracy':round(sum(r.correct for r in members)/len(members),5)})
    return bins


def assess(rows:tuple[ReviewedClaim,...], model:FieldRootCalibrator,
           threshold:float|None,policy:str='root_field')->dict:
    resolved=[r for r in rows if r.resolved]
    unknown=sum(r.outcome=='unknown' for r in rows)
    superseded=sum(r.outcome=='superseded' for r in rows)
    score=lambda r:model.predict(r,policy)
    brier=(sum((score(r)-int(r.correct))**2 for r in resolved)/len(resolved)) if resolved else None
    bins=calibration_bins(rows,model,policy)
    ece=sum(b['n']/len(resolved)*abs(b['predicted_mean']-b['observed_accuracy']) for b in bins) if resolved else None
    selected=[r for r in resolved if threshold is not None and score(r)>=threshold]
    errors=sum(not r.correct for r in selected)
    return {'evaluated':len(rows),'resolved':len(resolved),'unknown':unknown,'superseded':superseded,
            'brier':round(brier,6) if brier is not None else None,
            'ece':round(ece,6) if ece is not None else None,
            'coverage_of_resolved':round(len(selected)/len(resolved),6) if resolved else None,
            'observed_error_fraction':round(errors/len(selected),6) if selected else None,
            'wilson_error_upper_95':round(wilson_upper(errors,len(selected)),6) if selected else None,
            'published_lab_candidates':len(selected),'calibration_bins':bins,
            'risk_coverage_curve':risk_coverage(resolved,model,policy),
            'by_field':{field:{'resolved':len(g),'brier':round(sum((score(x)-int(x.correct))**2 for x in g)/len(g),6),
                               'errors_if_selected':sum((not x.correct) and threshold is not None and score(x)>=threshold for x in g)}
                        for field,g in sorted(_by_field(resolved).items())}}


def _by_field(rows):
    g=defaultdict(list)
    for r in rows:g[r.field].append(r)
    return g



def risk_coverage(resolved:list[ReviewedClaim],model:FieldRootCalibrator,policy:str)->list[dict]:
    """All test thresholds reported for diagnosis, NEVER used to select a policy."""
    if not resolved:return []
    unique=sorted({model.predict(r,policy) for r in resolved},reverse=True)
    result=[]
    for t in unique:
        accepted=[r for r in resolved if model.predict(r,policy)>=t]
        errors=sum(not r.correct for r in accepted)
        result.append({'threshold':round(t,6),'coverage':round(len(accepted)/len(resolved),6),
                       'error_fraction':round(errors/len(accepted),6),
                       'n':len(accepted)})
    return result

def assess_drift(cal_rows: tuple[ReviewedClaim,...],test_rows: tuple[ReviewedClaim,...], min_n:int=20)->list[dict]:
    """Descriptive drift diagnostic. Post-test alerts do not tune test threshold."""
    keys=sorted(set((r.publisher_root,r.field) for r in cal_rows+test_rows))
    alerts=[]
    for key in keys:
        a=[r for r in cal_rows if r.resolved and (r.publisher_root,r.field)==key]
        b=[r for r in test_rows if r.resolved and (r.publisher_root,r.field)==key]
        if len(a)<min_n or len(b)<min_n:continue
        fa=sum(not r.correct for r in a)/len(a)
        fb=sum(not r.correct for r in b)/len(b)
        # Operational flag only; NOT a significance test.
        alerts.append({'publisher_root':key[0],'field':key[1], 'calibration_n':len(a),
                       'test_n':len(b),'error_calibration':round(fa,4),'error_test':round(fb,4),
                       'absolute_change':round(fb-fa,4),'investigate':abs(fb-fa)>=.15})
    return alerts


def report(reviews:list[ReviewedClaim],*, train_end:str,calibration_end:str,evaluation_asof:str,
           target_risk:float=.20,min_published:int=25)->dict:
    s=time_split(reviews,train_end=train_end,calibration_end=calibration_end,evaluation_asof=evaluation_asof)
    model=FieldRootCalibrator(s.train)
    policies=('global','field','root_field')
    selections={p:select_threshold(s.calibration,model,target_risk=target_risk,
                                   min_published=min_published,policy=p) for p in policies}
    metrics={p:assess(s.test,model,selections[p]['threshold'],p) for p in policies}
    return {'study':'KEP-SCI-002','research_only':True,'allow_auto_publish':False,
            'data_origin':s.origin,'valid_real_world_calibration':False,
            'data_summary':{'train':len(s.train),'calibration':len(s.calibration),'test':len(s.test),
                            'train_labeled':sum(r.resolved for r in s.train),
                            'calibration_labeled':sum(r.resolved for r in s.calibration),
                            'test_labeled':sum(r.resolved for r in s.test),
                            'late_reviews_purged':s.purged_late_adjudications,
                            'cross_split_entities_purged':s.purged_cross_split_entities},
            'thresholds_from_calibration_only':selections,'test_metrics':metrics,
            'drift_diagnostics':assess_drift(s.calibration,s.test),
            'caution':'Lab threshold is not a statistical guarantee for new sources, cities or future observations.'}
