"""Retrospective held-out UCI ratings benchmark; no simulated preference labels."""
from __future__ import annotations
from pathlib import Path
from collections import defaultdict,Counter
import csv, hashlib, json, math, random, statistics, time
from kepcore.preferences import Rating,PreferenceModel

ROOT=Path(__file__).resolve().parents[1]
EXPECTED='d2072b911d10edf52a1b01c4a481e02490e651ca'


def load_ratings(path=None):
    path=Path(path or ROOT/'data/raw/uci/rating_final.csv')
    b=path.read_bytes(); blob=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
    if blob != EXPECTED: raise ValueError('Dataset integrity check failed; benchmark stopped')
    raw=list(csv.DictReader(b.decode('utf-8').splitlines()))
    rows=[Rating(r['userID'],r['placeID'],float(r['rating'])) for r in raw]
    assert len(rows)==1161 and len({(r.user,r.item) for r in rows})==1161
    return rows,dict(rows=len(rows),users=len({r.user for r in rows}),items=len({r.item for r in rows}),
                     git_blob_sha1=blob,sha256=hashlib.sha256(b).hexdigest(),bytes=len(b),
                     rating_counts=dict(Counter(str(int(r.value)) for r in rows)),
                     origin='historical_UCI_ratings_reconstructed_from_connector_and_byte_verified_against_two_GitHub_mirrors',
                     live_istanbul_data=False,geographic_generalization_test=False,timestamps_available=False)


def split_rows(rows,seed):
    groups=defaultdict(list)
    for r in rows:groups[r.user].append(r)
    train=[];valid=[];test=[];eligible=[]
    for idx,(u,rs) in enumerate(sorted(groups.items())):
        rs=sorted(rs,key=lambda r:r.item)
        if len(rs)<6:train.extend(rs);continue
        random.Random(seed+idx).shuffle(rs)
        test.extend(rs[:3]);valid.extend(rs[3:4]);train.extend(rs[4:]);eligible.append(u)
    keys=lambda xs:{(r.user,r.item) for r in xs}
    assert not (keys(train)&keys(valid) or keys(train)&keys(test) or keys(valid)&keys(test))
    assert len(train)+len(valid)+len(test)==len(rows)
    return train,valid,test,eligible


def mae(model,rows):return statistics.mean(abs(model.predict(r.user,r.item)-r.value) for r in rows)


def tie_ndcg(values,scores,k=3):
    gains=[2**v-1 for v in values]
    denom=sum(g/math.log2(i+2) for i,g in enumerate(sorted(gains,reverse=True)[:k]))
    if denom==0:return None
    # Average DCG over all permutations within exactly tied model scores.
    blocks=defaultdict(list)
    for score,gain in zip(scores,gains):blocks[score].append(gain)
    pos=0;dcg=0.
    for score,gs in sorted(blocks.items(),reverse=True):
        mean=statistics.mean(gs)
        for i in range(pos,min(pos+len(gs),k)):dcg+=mean/math.log2(i+2)
        pos+=len(gs)
    return dcg/denom


def evaluate(model,test):
    groups=defaultdict(list);predictions=[]
    for r in test:
        score=model.predict(r.user,r.item)
        row=dict(user=r.user,item=r.item,actual=r.value,predicted=score,absolute_error=abs(score-r.value))
        predictions.append(row);groups[r.user].append(row)
    users={}
    for u,rs in groups.items():
        users[u]=dict(mae=statistics.mean(r['absolute_error'] for r in rs),
                      ndcg=tie_ndcg([r['actual'] for r in rs],[r['predicted'] for r in rs]),ratings=len(rs))
    applicable=[v['ndcg'] for v in users.values() if v['ndcg'] is not None]
    return dict(mae=statistics.mean(r['absolute_error'] for r in predictions),
                rmse=math.sqrt(statistics.mean((r['actual']-r['predicted'])**2 for r in predictions)),
                ndcg_at_3_observed_only=statistics.mean(applicable) if applicable else None,
                rankable_users=len(applicable),users=users,predictions=predictions)


def paired_bootstrap(a,b,metric,seed=89213,n=2000):
    vals=[a[u][metric]-b[u][metric] for u in sorted(set(a)&set(b)) if a[u][metric] is not None and b[u][metric] is not None]
    if not vals:return None
    rng=random.Random(seed)
    draws=sorted(statistics.mean(rng.choices(vals,k=len(vals))) for _ in range(n))
    return dict(delta_a_minus_b=statistics.mean(vals),ci95_conditional=[draws[int(.025*n)],draws[int(.975*n)]],users=len(vals),resamples=n,
                caveat='Paired evaluation-user resampling, conditional on fitted model and fixed split; no population/causal claim')


def one_run(rows,seed,full=True):
    train,valid,test,eligible=split_rows(rows,seed)
    methods=['global_mean','item_mean','user_mean','bias','item_knn']
    fitted={};scores={};grids={};chosen={}
    for method in methods:
        options=[(5.,15)] if method=='global_mean' else ([(r,k) for r in [1.,5.,20.] for k in [5,15]] if method=='item_knn' else [(r,15) for r in [1.,5.,20.]])
        evaluations=[]
        for reg,k in options:
            m=PreferenceModel(method,reg,k).fit(train)
            evaluations.append((mae(m,valid),reg,k))
        best=min(evaluations,key=lambda t:(t[0],options.index((t[1],t[2]))))
        grids[method]=[dict(validation_mae=v,regularization=r,k=k) for v,r,k in evaluations]
        chosen[method]=dict(validation_mae=best[0],regularization=best[1],k=best[2])
        m=PreferenceModel(method,best[1],best[2]).fit(train+valid)
        assert not (m.training_pairs & {(r.user,r.item) for r in test})
        fitted[method]=m;scores[method]=evaluate(m,test)
    selected=min(methods,key=lambda m:(chosen[m]['validation_mae'],methods.index(m)))
    comparisons={}
    for a,b in [('bias','item_mean'),('bias','user_mean'),('item_knn','bias'),('item_knn','item_mean')]:
        comparisons[a+'_vs_'+b]={metric:paired_bootstrap(scores[a]['users'],scores[b]['users'],metric) for metric in ['mae','ndcg']} if full else {}
    result=dict(seed=seed,split=dict(train=len(train),validation=len(valid),test=len(test),test_users=len(eligible),
                                    train_only_users=len({r.user for r in rows})-len(eligible),test_items_per_user=3),
                hyperparameters=chosen,selected_by_validation=selected,
                models={m:{k:v for k,v in s.items() if k not in {'users','predictions'}} for m,s in scores.items()},paired_comparisons=comparisons)
    if full:
        result['validation_search']=grids
        result['split_manifest']=[dict(user=r.user,item=r.item,split=name) for name,rs in [('train',train),('validation',valid),('test',test)] for r in rs]
        result['predictions_by_method']={m:s['predictions'] for m,s in scores.items()}
        result['per_user']={m:s['users'] for m,s in scores.items()}
    return result


def cold_users_run(rows):
    # Fixed 20% whole-user holdout, fixed regularization, no evaluation-label tuning.
    users=sorted({r.user for r in rows});random.Random(97313).shuffle(users)
    held=set(users[:math.ceil(.2*len(users))]);train=[r for r in rows if r.user not in held];test=[r for r in rows if r.user in held]
    return dict(held_out_users=len(held),test_ratings=len(test),models={m:evaluate(PreferenceModel(m,5,15).fit(train),test)['mae'] for m in ['global_mean','item_mean','user_mean','bias','item_knn']},
                interpretation='Entirely unseen users; all user histories withheld. Not a temporal or new-city test.')


def run(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    protocol=json.loads((ROOT/'benchmarks/preference_protocol.json').read_text());rows,audit=load_ratings()
    start=time.perf_counter();primary=one_run(rows,protocol['primary_seed'])
    sensitivity=[one_run(rows,s,False) for s in protocol['sensitivity_seeds']]
    result=dict(version='0.3',dataset=audit,protocol=protocol,primary=primary,sensitivity=sensitivity,cold_start=cold_users_run(rows),
                runtime_seconds=time.perf_counter()-start,live_model_calls=0,paid_api_calls=0,
                limitations=['Historical ratings, not live Istanbul evidence','No timestamps; random holdout not temporal prediction',
                             'Observed-rating selection bias; unrated restaurants are not negatives',
                             'NDCG only reorders 3 held-out rated choices; not full-catalog recommendation quality',
                             'No user intent, source dynamics, real app behavior or causal effects in these data',
                             'Additional seeds overlap in users/ratings and are NOT independent trials',
                             'No published research algorithm replication or market competitor comparison'])
    (out/'preference_results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    with (out/'preference_summary.csv').open('w',newline='') as f:
        fields=['method','mae','rmse','ndcg_at_3_observed_only','rankable_users'];w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for m,metrics in primary['models'].items():w.writerow({'method':m,**metrics})
    print(json.dumps({k:result[k] for k in ['dataset','runtime_seconds','cold_start']},indent=2));print(json.dumps({k:primary[k] for k in ['split','selected_by_validation','models','paired_comparisons']},indent=2))
    return result
