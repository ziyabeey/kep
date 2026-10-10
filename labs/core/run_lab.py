#!/usr/bin/env python3
"""Run real-record audits and designed contract cases; no network or LLM use."""
from __future__ import annotations
from collections import Counter
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path
import argparse, copy, csv, json, time
from kepcore.core import ROOT, load_catalog, load_json, dt, temporal_state, decide, Query, reconcile_claims, stable_hash
from kepcore.store import Store

def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def scenarios(catalog):
    cases=[]
    def add(name,records,query,expected,origin='real_record_designed_query'):
        cases.append(dict(id=name,records=records,query=asdict(query),expected_action=expected,origin=origin))
    for r in catalog:
        if r['kind']=='place':
            base=dict(city='İstanbul',kind='place',lat=r['lat'],lon=r['lon'],radius_km=.01)
            add('metadata/'+r['id'],[r],Query(**base),'DISCOVER')
            add('open_now/'+r['id'],[r],Query(**base,open_now=True),'REFRESH')
            add('budget/'+r['id'],[r],Query(**base,budget=500),'REFRESH')
            add('quiet/'+r['id'],[r],Query(**base,quiet=True),'CLARIFY')
        else:
            ended=dt(r.get('ends_at') or r['starts_at']).date()<dt('2026-10-10').date()
            add('today/'+r['id'],[r],Query(city='İzmir',kind='event'),'ABSTAIN' if ended else 'REFRESH')
            add('wrong_city/'+r['id'],[r],Query(city='İstanbul',kind='event'),'ABSTAIN')
            historical=dt(r['starts_at'])-timedelta(hours=1)
            add('historical_snapshot/'+r['id'],[r],Query(city='İzmir',kind='event',at=historical.isoformat()),'REFRESH')
    # Fault injection is explicitly isolated from the real immutable inputs.
    r=copy.deepcopy(next(r for r in catalog if r['id']=='izmir_event:6960'))
    r.update(synthetic=True,synthetic_overlay='test_only_fresh_observation',origin_live_verified=True,source_observed_at='2026-08-19T18:00:00+03:00')
    q=Query(city='İzmir',kind='event',at='2026-08-19T20:00:00+03:00',budget=0)
    add('injected/fresh_source',[r],q,'RECOMMEND','real_base_synthetic_observation')
    c=copy.deepcopy(r);c.update(lifecycle='cancelled')
    add('injected/cancelled',[c],q,'ABSTAIN','real_base_synthetic_cancellation')
    c=copy.deepcopy(r);c.update(price=100)
    add('injected/over_budget',[c],q,'ABSTAIN','real_base_synthetic_price')
    c=copy.deepcopy(r);c.update(evidence_status='disputed')
    add('injected/disputed',[c],q,'REFRESH','real_base_synthetic_conflict')
    c=copy.deepcopy(r);c.update(source_observed_at='2026-08-10T18:00:00+03:00')
    add('injected/stale',[c],q,'REFRESH','real_base_synthetic_age')
    add('injected/work_push',[r],Query(**{**asdict(q),'proactive':True,'push_opt_in':True,'mode':'work'}),'SILENT','real_base_synthetic_user_mode')
    add('injected/work_explicit_question',[r],Query(**{**asdict(q),'mode':'work'}),'RECOMMEND','real_base_synthetic_user_mode')
    add('injected/no_push_permission',[r],Query(**{**asdict(q),'proactive':True,'push_opt_in':False}),'SILENT','real_base_synthetic_permission')
    add('injected/capped_push',[r],Query(**{**asdict(q),'proactive':True,'push_opt_in':True,'already_sent_today':1}),'SILENT','real_base_synthetic_permission')
    return cases

def run(output):
    output.mkdir(parents=True,exist_ok=True)
    catalog=load_catalog();events=[r for r in catalog if r['kind']=='event'];places=[r for r in catalog if r['kind']=='place']
    save(ROOT/'data/normalized/catalog.json',catalog)
    raw=load_json(ROOT/'data/raw/izmir_events_excerpt.json')['records']
    # Extraction consistency checks, NOT independent real-world ground truth labels.
    checks=[]
    for a,b in zip(raw,events):
        checks.append(dict(id=b['id'],source_id_preserved=b['source_item_id']==str(a['Id']),start_preserved=dt(b['starts_at'])==dt(a['EtkinlikBaslamaTarihi']),price_not_invented=(b['price']==0 if a['UcretsizMi'] else b['price'] is None),city_correct=b['city']=='İzmir'))
    audit=dict(as_of='2026-10-10T18:00:00+03:00',real_event_records=len(events),real_place_records=len(places),fresh_event_observations=sum(r['origin_live_verified'] for r in events),events_with_equal_start_end=sum('END_EQUALS_START_DURATION_UNKNOWN' in r['flags'] for r in events),events_with_missing_price_amount=sum(r['price'] is None for r in events),events_with_unresolved_venue=sum(r['venue_precision']=='unresolved' for r in events),event_kinds=dict(Counter(r['event_kind'] for r in events)),temporal_states=dict(Counter(temporal_state(r,dt('2026-10-10T18:00:00+03:00')) for r in events)),places_with_known_hours=sum(r['opening_hours'] is not None for r in places),field_consistency=checks,interpretation='Source-to-schema consistency only; source observations are cached, not independently verified live.')
    save(output/'data_audit.json',audit)
    claims=load_json(ROOT/'data/raw/pera_conflict_research_fixture.json')['claims']
    conflicts=reconcile_claims(claims);save(output/'real_price_conflicts.json',conflicts)
    cases=scenarios(catalog);save(output/'designed_cases.json',cases)
    rows=[];predictions=[]
    for policy in ['simple_safe','blanket_verification','query_aware']:
        start=time.perf_counter(); correct=0;chosen=0;answers=Counter()
        for c in cases:
            result=decide(c['records'],Query(**c['query']),policy=policy).to_dict()
            ok=result['action']==c['expected_action'];correct+=ok;chosen+=bool(result['selected']);answers[result['action']]+=1
            predictions.append(dict(case_id=c['id'],origin=c['origin'],policy=policy,expected_action=c['expected_action'],contract_pass=ok,decision=result))
        rows.append(dict(policy=policy,contract_cases=len(cases),passed=correct,failed=len(cases)-correct,answering_cases=chosen,actions=dict(answers),runtime_ms=round((time.perf_counter()-start)*1000,3)))
    save(output/'contract_benchmark_predictions.json',predictions)
    # Fresh DB build reproducible. Not the user's repository or a production database.
    dbpath=output/'kep_core.sqlite'
    if dbpath.exists():dbpath.unlink()
    store=Store(dbpath)
    first=Counter(store.ingest(r) for r in catalog);second=Counter(store.ingest(r) for r in catalog)
    examples={}
    anchor=next(p for p in places if p['id']=='wikidata:Q91274')
    demo=[('galata_nearby',Query(city='İstanbul',kind='place',lat=anchor['lat'],lon=anchor['lon'],radius_km=1,limit=7)),('galata_open_budget',Query(city='İstanbul',kind='place',lat=anchor['lat'],lon=anchor['lon'],radius_km=1,budget=500,open_now=True)),('istanbul_events_today',Query(city='İstanbul',kind='event')),('izmir_events_today',Query(city='İzmir',kind='event'))]
    for name,q in demo:
        d=decide(catalog,q).to_dict();store.log_decision(asdict(q),d);examples[name]=d
    counts=store.counts();store.close();save(output/'examples.json',examples)
    results=dict(version='0.3_contract_suite',data_origin='real_cached_source_excerpts_plus_explicit_test_overlays',external_model_calls=0,real_user_trials=0,live_source_observations=0,github_changes=0,benchmark_type='designed_engineering_contract_suite_not_independent_generalization_benchmark',test_scope=dict(designed_cases=len(cases),real_base_designed_query_cases=sum(c['origin']=='real_record_designed_query' for c in cases),real_base_synthetic_overlay_cases=sum(c['origin']!='real_record_designed_query' for c in cases),unit_test_evidence='unit_test_log.txt; contract cases are also checked inside one unit test, counts must not be added as independent trials'),baselines=dict(simple_safe='Same hard-constraint gate and proximity ranking as KEP. Intentionally strong simple baseline; no expected advantage.',blanket_verification='Overcautious all-fields freshness policy. Ablation, not a market competitor.'),policies=rows,ingestion=dict(first=dict(first),second=dict(second),sqlite_counts=counts),real_conflicts=dict(fields=len(conflicts),disputed=sum(v['status']=='disputed' for v in conflicts.values()),publisher_roots=1,interpretation='Conflicting retrieved sections/versions, not confirmed simultaneous live website inconsistency'),audit=audit,limitations=['No Istanbul event stream or representative restaurant dataset was acquired.','This legacy contract suite does not use preferences; see the separate UCI ratings benchmark. No attendance, live update history or calibrated confidence.','No MiMo/Laya calls or peer-reviewed algorithm reproduction.','No synthetic outcome success-rate claims; test pass rate is not recommendation accuracy.','Synthetic overlays are labelled; current calendar is evaluated as of 2026-10-10.','Source cache may be stale; acquisition date is not origin verification date.'])
    save(output/'results.json',results)
    with (output/'benchmark_summary.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['policy','contract_cases','passed','failed','answering_cases','runtime_ms']);w.writeheader();w.writerows({k:r[k] for k in w.fieldnames} for r in rows)
    print(json.dumps({k:results[k] for k in ['version','policies','ingestion','real_conflicts']},ensure_ascii=False,indent=2))
    return results

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=ROOT/'results');args=p.parse_args();run(args.out)
