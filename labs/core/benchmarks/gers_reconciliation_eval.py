"""DATA-013 real source replay. No invented official events or human labels."""
from __future__ import annotations
import gc
import json
import platform
from statistics import median
from time import perf_counter
import tracemalloc
from kepcore.gers_reconciliation import load_pinned_pair, reconcile, public_summary
from kepcore.overture_delta import compare_snapshots


def naive_removal_as_closure(before, after):
    """Deliberately unsafe benchmark-only hypothesis; never exported as a POI label."""
    old={r['overture_id'] for r in before.records}
    new={r['overture_id'] for r in after.records}
    return {'old_ids':len(old),'new_ids':len(new),'retained_ids':len(old&new),
        'newly_listed_ids':len(new-old),'no_longer_listed_ids':len(old-new),
        'unsupported_closure_assertion_count':len(old-new),
        'assertions_independently_proven_false':None,
        'business_event_accuracy':None,'consumer_publish':False}


def _measure(fn, repeats=3):
    times=[]
    first=fn()  # Warm cache separately, not part of the timed sample.
    for _ in range(repeats):
        gc.collect();start=perf_counter();observed=fn();times.append(perf_counter()-start)
        if first!=observed:
            raise AssertionError('Non-deterministic research result')
    gc.collect();tracemalloc.start()
    try:
        fn();_,peak=tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return {'repeats':repeats,'warm_median_seconds':round(median(times),6),
        'warm_min_seconds':round(min(times),6),'warm_max_seconds':round(max(times),6),
        'separate_run_peak_python_allocation_bytes':peak}


def evaluate(*, profile=False):
    before,after=load_pinned_pair()
    naive=lambda:naive_removal_as_closure(before,after)
    deterministic=lambda:compare_snapshots(before,after,allow_historical_backfill=True)
    reconciliation=lambda:reconcile(before,after,allow_historical_backfill=True)
    n,d,r=naive(),deterministic(),reconciliation()
    ds=d['source_record_churn'];rs=r['source_record_delta']
    for key in ('retained_ids','newly_listed_ids','no_longer_listed_ids'):
        if not n[key]==ds[key]==rs[key]:
            raise AssertionError('Source-membership accounting disagrees across methods')
    routing=r['routing']
    stable={'study':'KEP-DATA-013','real_source_releases':[before.release,after.release],
        'human_labels':0,'paid_api_calls':0,'offline_replay_network_calls':0,
        'methods':{
            'naive_removal_as_closure':n,
            'kep_deterministic':{'source_record_delta':rs,
                'unsupported_closure_assertion_count':0,
                'identity_review_candidates':len(ds['possible_id_reassignment_hints']),
                'official_changelog_evidence_used':False,'business_event_accuracy':None},
            'kep_reconciliation':{'unsupported_closure_assertion_count':0,
                'identity_review_candidates':len(r['identity_review']['candidates']),
                'official_event_reconciliation_complete':False,
                'release_chain_compatibility_checked':True,'business_event_accuracy':None}},
        'reconciliation':public_summary(r),
        'review_policy_ablation':{
            'definition':'Separate all-changes review-everything policy, NOT the removal-only naive method',
            'all_changed_or_membership_ids':len(before.records)+rs['newly_listed_ids']-rs['unchanged_ids'],
            'source_membership_or_property_review_ids':routing['membership_review_ids']+routing['property_review_ids'],
            'technical_schema_only_ids':routing['schema_only_ids'],
            'metadata_only_ids':routing['metadata_only_ids'],
            'actually_unnecessary_inspections_measured':None,
            'no_claim_that_queued_cases_are_true_errors':True}}
    out={'stable_results':stable}
    if profile:
        out['performance']={'python':platform.python_version(),'platform':platform.platform(),
            'methodology':'3 warm untraced timings; 1 separate tracemalloc run; input loading excluded',
            'memory_scope':'Python allocation peak inside each method, NOT total RSS or input storage',
            'speed_comparison_is_not_quality_comparison':True,
            'methods':{name:_measure(fn) for name,fn in (
                ('naive_removal_as_closure',naive),('kep_deterministic',deterministic),
                ('kep_reconciliation',reconciliation))}}
    return out


if __name__=='__main__':
    print(json.dumps(evaluate(profile=True),indent=2,sort_keys=True,ensure_ascii=False))
