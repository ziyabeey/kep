"""Deterministic artificial source-drift challenge for KEP-SCI-002.

Synthetic source correctness labels help test evaluation protocol, NEVER
make an inference about true Istanbul publishing reliability.
"""
from __future__ import annotations

import json
import hashlib
import random
from datetime import datetime,timedelta,timezone
from kepcore.calibration import ReviewedClaim,report

SEED=20261011
BASE=datetime(2026,1,1,tzinfo=timezone.utc)


def generate(seed=SEED,per_phase=450,drift=True):
    rng=random.Random(seed)
    roots=['official','secondary','community']
    fields=['starts_at','venue','price','cancelled']
    quality={'official':.975,'secondary':.85,'community':.72}
    result=[]
    for phase in range(3):
        for i in range(per_phase):
            publisher=roots[(i+phase)%len(roots)]
            field=fields[(i//3+phase)%len(fields)]
            correct_p=quality[publisher]
            if field=='price':correct_p-=.10
            if drift and phase==2 and publisher=='secondary':correct_p-=.30
            outcome='correct' if rng.random()<correct_p else 'incorrect'
            if i%31==0:outcome='unknown'
            if i%79==0:outcome='superseded'
            prediction=BASE+timedelta(days=phase*45,minutes=i*60)
            result.append(ReviewedClaim(
                claim_id=f'lab-{phase}-{i}',entity_id=f'lab-entity-{phase}-{i}',
                field=field,publisher_root=publisher,source_id=f'lab-{publisher}',
                city='Synthetic City',claimed_at=(prediction-timedelta(hours=6)).isoformat(),
                observed_at=(prediction-timedelta(minutes=10)).isoformat(),
                predicted_at=prediction.isoformat(),
                snapshot_sha256=hashlib.sha256(f'synthetic:{seed}/{phase}/{i}'.encode()).hexdigest(),
                rights_scope='research_ingest',
                checked_at=(prediction+timedelta(hours=2)).isoformat(),
                outcome=outcome,reviewer_id='simulator',
                evidence_ref=f'synthetic:generator/{seed}/{phase}/{i}',origin='synthetic'))
    return result


def run(seed=SEED,drift=True):
    claims=generate(seed,drift=drift)
    result=report(claims,train_end=(BASE+timedelta(days=45)).isoformat(),
                  calibration_end=(BASE+timedelta(days=90)).isoformat(),
                  evaluation_asof=(BASE+timedelta(days=140)).isoformat(),
                  target_risk=.20,min_published=25)
    result['seed']=seed
    result['synthetic_source_shift']=drift
    result['field_label_truth']='synthetic known at test generation, never available to KEP decision policy'
    return result

if __name__=='__main__':print(json.dumps(run(),ensure_ascii=False,indent=2))
