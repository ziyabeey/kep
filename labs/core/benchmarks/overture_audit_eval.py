"""Synthetic stress test of biased confidence-band sampling (NO real POIs)."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID
import json
import statistics

from benchmarks.overture_places_eval import example
from scripts.overture_istanbul import execute
from kepcore.overture_audit import design_existence_audit,estimate_existence_error
from kepcore.overture_places import PILOT

FREEZE='2026-10-11T08:00:00+00:00'
REVIEW='2026-10-12T08:00:00+00:00'
EVAL='2026-10-13T08:00:00+00:00'


def generate():
    """200 invented points; scarce low-confidence strata have more nonexistent POIs."""
    values={}
    cells={}
    i=2
    for cidx,cell in enumerate(sorted(PILOT)):
        rows=[]
        for j in range(100):
            conf=(None if j<5 else .28 if j<15 else .65 if j<35 else .94)
            invalid=(j%5==0 if j<5 else j%10<6 if j<15 else j%4==0 if j<35 else j%22==0)
            row=example(i,cell,f'Invented place {cell} {j}','cafe',confidence=conf)
            values[str(UUID(int=i))]=invalid
            rows.append(row)
            i+=1
        cells[cell]=rows
    return cells,values


def synthetic_vote(name,outcome):
    return {'reviewer_id':name,'outcome':outcome,'checked_at':REVIEW,
            'evidence_url':'https://example.org/synthetic-lab-only'}


def run(repeats=60,budget=16)->dict:
    if repeats<1:raise ValueError('Positive repeat count required')
    cells,truth=generate()
    with TemporaryDirectory() as tmp:
        folder=Path(tmp)
        inputs={}
        for cell,rows in cells.items():
            p=folder/f'{cell}.json'
            p.write_text(json.dumps({'type':'FeatureCollection','features':rows},ensure_ascii=False))
            inputs[cell]=p
        out=folder/'normalized'
        execute(output=out,inputs=inputs,fetch=False,seed_file=None)
        errors=[]
        naive=[];weighted=[]
        for i in range(repeats):
            seed=f'synthetic-selection-seed-for-KEP-{i:05d}'
            plan=design_existence_audit(out,budget=budget,seed=seed,sampled_at=FREEZE)
            labels=[]
            for row in plan['selected']:
                outcome='does_not_exist' if truth[row['overture_id']] else 'exists'
                labels.append({'overture_id':row['overture_id'],
                               'votes':[synthetic_vote('reviewer_a',outcome),synthetic_vote('reviewer_b',outcome)]})
            report=estimate_existence_error(out,plan=plan,seed=seed,labels=labels,evaluation_asof=EVAL)
            assert report['status']=='COMPLETE_DESIGN_BASED_DIAGNOSTIC'
            naive.append(sum(truth[s['overture_id']] for s in plan['selected'])/budget)
            weighted.append(report['error_fraction_estimate'])
        actual=sum(truth.values())/len(truth)
        return {
            'study':'KEP-DATA-002-synthetic-bias-challenge',
            'origin':'synthetic', 'real_istanbul_places':0, 'human_audited_count':0,
            'population_n':len(truth), 'sample_budget_per_repeat':budget,
            'repeats':repeats, 'true_generated_nonexistence_fraction':round(actual,6),
            'unweighted_sample_mean':round(statistics.mean(naive),6),
            'weighted_sample_mean':round(statistics.mean(weighted),6),
            'unweighted_absolute_bias':round(abs(statistics.mean(naive)-actual),6),
            'weighted_absolute_bias':round(abs(statistics.mean(weighted)-actual),6),
            'unweighted_rmse':round(statistics.mean((p-actual)**2 for p in naive)**.5,6),
            'weighted_rmse':round(statistics.mean((p-actual)**2 for p in weighted)**.5,6),
            'can_extrapolate_to_istanbul':False,
            'note':'Naive sample means can be biased under unequal inclusion probabilities. Design-based weighted estimates require a correct frame, random draw, complete and valid reviews.',
        }


if __name__=='__main__':
    print(json.dumps(run(),ensure_ascii=False,indent=2,sort_keys=True))
