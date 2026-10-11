"""KEP-DATA-011: empirical Overture *source-record* drift and review triage.

This module is a read-only, dependency-free research diagnostic. It is NOT a
probability-of-truth calibrator, authoritative business state, spatial route,
or source license validator. It never claims new/missing records are physical
business openings/closures. Reviewer queues are TARGETED, not random samples;
never use their outcomes to estimate the source-wide error rate.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from hashlib import sha256
from math import isfinite
import json

POLICY_VERSION = 'KEP-DATA-011-TRIAGE-v1'
FIELDS = ('name', 'address', 'basic_category', 'taxonomy_primary',
          'operating_status', 'locality', 'country', 'source_provenance',
          'lon', 'lat', 'cell')
SCHEMA_SENSITIVE = frozenset({'basic_category', 'taxonomy_primary'})
LANES = ('no_longer_listed', 'newly_listed', 'property_or_location',
         'schema_only', 'confidence_only_over_0_10')
DEFAULT_QUOTAS = {'no_longer_listed': 12, 'newly_listed': 12,
                  'property_or_location': 16, 'schema_only': 8,
                  'confidence_only_over_0_10': 12}
REQUIRED = frozenset({'overture_id','name','address','basic_category',
                      'taxonomy_primary','operating_status','locality','country',
                      'source_provenance','lon','lat','cell','confidence'})
MINIMAL_FIELDS = REQUIRED | frozenset({'active_event','administrative_district',
    'consumer_verified','live_price','open_now','opening_hours'})
PILOT_CELLS = frozenset({'besiktas_center','karakoy_center'})


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def _index(rows: list[dict], label: str) -> dict[str, dict]:
    if not isinstance(rows, list) or not rows:
        raise ValueError(f'{label} must be a non-empty finite data snapshot')
    lookup: dict[str, dict] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row)!=MINIMAL_FIELDS:
            raise ValueError(f'{label} row missing expected research fields')
        key = row['overture_id']
        if not isinstance(key, str) or not key or len(key)>128 or key in lookup:
            raise ValueError(f'{label} has invalid or repeated place ID')
        if row['cell'] not in PILOT_CELLS:
            raise ValueError('Sampling cell missing')
        if not isinstance(row['source_provenance'], list):
            raise ValueError('Invalid source provenance entries')
        if (row['consumer_verified'] is not False
            or any(row[key] is not None for key in
                   ('active_event','administrative_district','live_price',
                    'open_now','opening_hours'))):
            raise ValueError('Research-only records cannot claim live or verified facts')
        for coord, lower, upper in [('lat', -90, 90), ('lon', -180, 180)]:
            x = row[coord]
            if isinstance(x, bool) or not isinstance(x, (int, float)) or not isfinite(x) or not lower<=x<=upper:
                raise ValueError('Invalid coordinates')
        score = row['confidence']
        if score is not None and (type(score) not in (int,float) or not isfinite(score) or not 0<=score<=1):
            raise ValueError('Invalid supplier confidence')
        try:
            _canonical(row)
        except (ValueError, TypeError) as exc:
            raise ValueError('Unserializable or nonfinite research record') from exc
        lookup[key] = row
    return lookup


def _changed(x:dict,y:dict)->list[str]:
    result=[]
    for field in FIELDS:
        if field=='source_provenance':
            a=sorted(_canonical(v) for v in x[field]);b=sorted(_canonical(v) for v in y[field])
        else:
            a,b=x[field],y[field]
        if a!=b:
            result.append('geometry' if field in ('lat','lon') else field)
    return sorted(set(result))


def _percentile(sorted_values:list[float],percent:float)->float|None:
    if not sorted_values:
        return None
    pos=(len(sorted_values)-1)*percent
    low=int(pos);high=min(low+1,len(sorted_values)-1)
    return round(sorted_values[low]+(sorted_values[high]-sorted_values[low])*(pos-low),6)


def inspect_releases(before:list[dict],after:list[dict])->dict:
    """Whole-frame paired drift, with mutually exclusive change categories."""
    old,new=_index(before,'August'),_index(after,'September')
    a,b=set(old),set(new)
    common=a&b
    by_lane:dict[str,list[dict]]=defaultdict(list)
    by_field=Counter()
    cell_counts=Counter()
    changed_score_deltas=[]
    paired_deltas=[]
    unchanged=0
    with_unavailable_score=0
    over_001=over_005=over_010=0
    confidence_only_over_005=0
    confidence_only_over_010=0
    both_score_and_fields=0
    schema_only=0
    for rid in sorted(a-b):
        row=old[rid];by_lane['no_longer_listed'].append({'overture_id':rid,'cell':row['cell'],
            'review_reason':'SOURCE_NOT_LISTED_NOT_BUSINESS_CLOSED'})
    for rid in sorted(b-a):
        row=new[rid];by_lane['newly_listed'].append({'overture_id':rid,'cell':row['cell'],
            'review_reason':'SOURCE_NEW_ID_NOT_BUSINESS_OPENED'})
    for rid in sorted(common):
        x,y=old[rid],new[rid]
        change=_changed(x,y)
        by_field.update(change)
        if x['confidence'] is None or y['confidence'] is None:
            with_unavailable_score+=1
            score_changed=x['confidence']!=y['confidence']
            magnitude=None
        else:
            delta=float(y['confidence'])-float(x['confidence'])
            paired_deltas.append(delta)
            magnitude=abs(delta)
            score_changed=delta!=0
            if score_changed:
                changed_score_deltas.append(magnitude)
            if magnitude>0.01:over_001+=1
            if magnitude>0.05:over_005+=1
            if magnitude>0.10:over_010+=1
        if change:
            both_score_and_fields+=int(score_changed)
            if set(change).issubset(SCHEMA_SENSITIVE):
                schema_only+=1
                lane='schema_only'
            else:
                lane='property_or_location'
            by_lane[lane].append({'overture_id':rid,'cell':y['cell'],
                'review_reason':'SOURCE_FIELD_REVISION_ONLY',
                'changed_fields':change})
        elif score_changed:
            if magnitude is not None and magnitude>0.05:
                confidence_only_over_005+=1
            if magnitude is not None and magnitude>0.10:
                confidence_only_over_010+=1
                by_lane['confidence_only_over_0_10'].append({
                    'overture_id':rid,'cell':y['cell'],
                    'review_reason':'LARGE_SUPPLIER_SCORE_REVISION_NOT_TRUTH',
                    'confidence_delta_abs':round(magnitude,6)})
        else:
            unchanged+=1
        cell_counts[y['cell']]+=1
    changed_score_deltas.sort()
    def rv(x):return round(x,6) if x is not None else None
    base={
        'policy':POLICY_VERSION,
        'study_scope':'TWO_OVERTURE_SOURCE_RELEASES_NOT_REAL_WORLD_BUSINESS_EVENTS',
        'research_only':True,'consumer_publish':False,
        'source_ids_old':len(old),'source_ids_new':len(new),'retained_ids':len(common),
        'newly_listed_ids':len(b-a),'no_longer_listed_ids':len(a-b),
        'source_fields_revised':len(by_lane['property_or_location'])+schema_only,
        'source_field_revisions_excluding_schema_only':len(by_lane['property_or_location']),
        'schema_only_revisions_cross_version_not_truth':schema_only,
        'confidence_only_revisions':len(common)-unchanged-len(by_lane['property_or_location'])-schema_only,
        'confidence_only_abs_delta_over_0_05':confidence_only_over_005,
        'confidence_only_abs_delta_over_0_10':confidence_only_over_010,
        'score_and_field_changes_overlap':both_score_and_fields,
        'confidence_missing_in_pair':with_unavailable_score,
        'retained_ids_no_changes':unchanged,
        'paired_confidence_count':len(paired_deltas),
        'confidence_changed_count':len(changed_score_deltas),
        'confidence_abs_delta_over_0_01':over_001,
        'confidence_abs_delta_over_0_05':over_005,
        'confidence_abs_delta_over_0_10':over_010,
        'confidence_abs_change_p50':_percentile(changed_score_deltas,.50),
        'confidence_abs_change_p90':_percentile(changed_score_deltas,.90),
        'confidence_abs_change_p99':_percentile(changed_score_deltas,.99),
        'paired_confidence_delta_mean':rv(sum(paired_deltas)/len(paired_deltas)) if paired_deltas else None,
        'field_revision_counts_nonexclusive':dict(sorted(by_field.items())),
        'retained_ids_by_new_cell':dict(sorted(cell_counts.items())),
        'category_semantics_comparable':False,
        'human_truth_labels':0,
        'physical_openings':None,'physical_closures':None,'business_moves':None,
        'score_calibrated_truth_probability':False,
        'triage_queue_is_unbiased_audit':False,
    }
    if (base['retained_ids'] != (base['source_fields_revised']+base['confidence_only_revisions']+unchanged)
        or base['retained_ids']+base['newly_listed_ids']!=len(new)
        or base['retained_ids']+base['no_longer_listed_ids']!=len(old)):
        raise AssertionError('Mutually exclusive change accounting failed')
    return {'summary':base,'lanes':{key:by_lane[key] for key in LANES}}


def build_targeted_queue(inspection:dict, *, quotas:dict|None=None)->dict:
    """Deterministic, deliberately biased triage; do not estimate error from it.

    The underlying random SCI-003 probability sample must remain completely
    separate. Priorities are fixed beforehand and never tuned on human labels.
    """
    lanes=inspection.get('lanes')
    if not isinstance(lanes,dict) or set(lanes)!=set(LANES):
        raise ValueError('Missing exclusive review lanes')
    quotas=DEFAULT_QUOTAS if quotas is None else quotas
    if not isinstance(quotas,dict) or set(quotas)!=set(LANES) or any(
        type(v)!=int or not 0<=v<=100 for v in quotas.values()):
        raise ValueError('Invalid pre-registered queue quotas')
    choices=[];counts={}
    for name in LANES:
        if not isinstance(lanes[name],list) or any(
            not isinstance(x,dict) or not isinstance(x.get('overture_id'),str) for x in lanes[name]):
            raise ValueError('Malformed review lane')
        selected=sorted(lanes[name], key=lambda x:(
            sha256((POLICY_VERSION+'|'+name+'|'+x['overture_id']).encode()).hexdigest(),
            x['overture_id']))[:quotas[name]]
        for item in selected:
            choices.append({'overture_id':item['overture_id'],'lane':name,
                            'reason':item['review_reason']})
        counts[name]={'available':len(lanes[name]),'selected':len(selected)}
    ids=[x['overture_id'] for x in choices]
    if len(ids)!=len(set(ids)):
        raise ValueError('One source ID entered multiple exclusive review lanes')
    return {'study':'KEP-DATA-011','policy':POLICY_VERSION,
            'selection':'DETERMINISTIC_TARGETED_NOT_RANDOM',
            'unbiased_audit':False,'can_estimate_error_rate':False,
            'human_labels_observed':0,'publishable':False,
            'total_selected':len(choices),'counts':counts,
            'items':choices}


def safe_public_summary(inspection:dict)->dict:
    """JSON summary without business names, addresses, coordinates, or IDs."""
    if not isinstance(inspection,dict) or not isinstance(inspection.get('summary'),dict):
        raise ValueError('Invalid inspection')
    result=dict(inspection['summary'])
    if result.get('human_truth_labels')!=0 or result.get('consumer_publish') is not False:
        raise ValueError('Cannot publish review labels or approved status via this diagnostic')
    return result
