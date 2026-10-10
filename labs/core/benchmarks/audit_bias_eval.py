"""KEP-SCI-003: demonstrative, wholly SYNTHETIC verification-selection bias.

The lab knows generated truth; the audit planner sees only candidate metadata,
never true error labels. This is NOT Istanbul measured source reliability.
"""
from __future__ import annotations

from datetime import timedelta
from hashlib import sha256
from math import sqrt
from pathlib import Path
from random import Random
from tempfile import TemporaryDirectory
import json

from kepcore.audit_sampling import design_random_audit, estimate_population_error
from kepcore.calibration import ReviewedClaim, aware
from kepcore.review_intake import ReviewCandidate
from kepcore.radar import Source

OBSERVED='2026-10-01T08:00:00+03:00'
DECISION='2026-10-02T08:00:00+03:00'
DRAW='2026-10-03T08:00:00+03:00'
CHECKED='2026-10-04T08:00:00+03:00'
ASOF='2026-10-05T08:00:00+03:00'
CONTENT=b'SYNTHETIC_AUDIT_DOCUMENT_NOT_REAL_WORLD_EVIDENCE'
HASH=sha256(CONTENT).hexdigest()


def source():
    return Source.parse({'id':'demo_source','url':'https://example.org/events',
        'city':'Synthetic City','format':'izmir_event_json','status':'approved',
        'approved_uses':['research_ingest'],'license':'synthetic_fixture',
        'rights_evidence_url':'https://example.org/synthetic','rights_reviewed_at':'2026-10-01',
        'review_note':'Artificial benchmark only'})


def generate_truth(seed:int=43)->tuple[list[ReviewCandidate],dict[str,bool]]:
    rng=Random(seed)
    population=[]
    truth={}
    for root, count, error_fraction in [('official',600,.06),('editorial',250,.25),('community',150,.60)]:
        # Ground truth exists solely inside this oracle generator. The planner
        # does not inspect it. Exact counts avoid accidental Monte-Carlo drift.
        flags=[False]*round(count*error_fraction)+[True]*(count-round(count*error_fraction))
        rng.shuffle(flags)
        for j in range(count):
            id_=f'{root}-{j:04d}'
            field='starts_at' if j%2 else 'venue'
            c=ReviewCandidate(claim_id=id_,entity_id=f'event-{id_}',field=field,
                claimed_value='Synthetic claim',publisher_root=root,
                source_id='demo_source',source_url='https://example.org/events/fixture',
                city='Synthetic City',claimed_at=OBSERVED,observed_at=OBSERVED,
                predicted_at=DECISION,snapshot_sha256=HASH,rights_scope='research_ingest')
            population.append(c)
            truth[id_]=flags[j]
    return population,truth


def label(c:ReviewCandidate, truth:dict[str,bool], *, late:bool=False)->ReviewedClaim:
    return ReviewedClaim(claim_id=c.claim_id,entity_id=c.entity_id,field=c.field,
        publisher_root=c.publisher_root,source_id=c.source_id,city=c.city,
        claimed_at=c.claimed_at,observed_at=c.observed_at,predicted_at=c.predicted_at,
        checked_at='2026-11-01T10:00:00Z' if late else CHECKED,
        snapshot_sha256=c.snapshot_sha256,rights_scope='research_ingest',
        outcome='correct' if truth[c.claim_id] else 'incorrect',
        reviewer_id='simulator',evidence_ref='synthetic:oracle',origin='synthetic')


def run(seed:int=20261011,repeats:int=40,budget:int=120)->dict:
    if not 1 <= repeats <= 100 or not 20 <= budget <= 1000:
        raise ValueError('Benchmark repetitions or budget outside safe range')
    population,truth=generate_truth()
    actual=sum(not ok for ok in truth.values())/len(truth)
    source_registry={'demo_source':source()}
    samples=[]
    with TemporaryDirectory() as tmp:
        folder=Path(tmp)
        (folder/f'{HASH}.snapshot').write_bytes(CONTENT)
        for iteration in range(repeats):
            plan=design_random_audit(population,sources=source_registry,snapshot_dir=folder,
                                     asof=DRAW,budget=budget,
                                     seed=f'secret-simulation-seed-{seed}-{iteration}',synthetic=True)
            selected={v['claim_id'] for v in plan['selected']}
            observations=[label(c,truth) for c in population if c.claim_id in selected]
            result=estimate_population_error(plan,population,observations,
                sources=source_registry,snapshot_dir=folder,evaluation_asof=ASOF,
                replay_seed=f'secret-simulation-seed-{seed}-{iteration}')
            if result['status']!='COMPLETE_STRATIFIED_AUDIT':
                raise AssertionError('Synthetic adjudication unexpectedly incomplete')
            samples.append(result)
        first=design_random_audit(population,sources=source_registry,snapshot_dir=folder,
                                  asof=DRAW,budget=budget,seed=f'secret-simulation-seed-{seed}-nonresponse',synthetic=True)
        ids={v['claim_id'] for v in first['selected']}
        partial=[label(c,truth) for c in population if c.claim_id in ids]
        partial[0]=label(next(c for c in population if c.claim_id==partial[0].claim_id),truth,late=True)
        noresponse=estimate_population_error(first,population,partial,sources=source_registry,
                           snapshot_dir=folder,evaluation_asof=ASOF,
                           replay_seed=f'secret-simulation-seed-{seed}-nonresponse')
    # Operational targeted queue deliberately focuses on flagged 'community'
    # sources, but DOES NOT peek at the outcome label to choose individual rows.
    targeted=sorted((c for c in population if c.publisher_root=='community'),key=lambda x:x.claim_id)[:budget]
    targeted_naive=sum(not truth[c.claim_id] for c in targeted)/len(targeted)
    predictions=[r['error_rate_estimate'] for r in samples]
    rms_error=sqrt(sum((p-actual)**2 for p in predictions)/len(predictions))
    in_bands=sum(r['confidence_band']['lower']<=actual<=r['confidence_band']['upper'] for r in samples)
    return {'study':'KEP-SCI-003','origin':'synthetic','research_only':True,
            'source_population_n':len(population),'budget_per_trial':budget,
            'repeats':repeats, 'truth_error_fraction':round(actual,6),
            'targeted_only_naive_error_fraction':round(targeted_naive,6),
            'stratified_audit_mean_error_fraction':round(sum(predictions)/len(predictions),6),
            'stratified_audit_rmse':round(rms_error,6),
            'stratified_audit_mean_absolute_error':round(sum(abs(p-actual) for p in predictions)/len(predictions),6),
            'stratified_mean_confidence_band_width':round(sum(r['confidence_band']['upper']-r['confidence_band']['lower'] for r in samples)/len(samples),6),
            'truth_in_conservative_band_trials':in_bands,
            'no_response_policy':{'status':noresponse['status'],'error_rate_estimate':noresponse['error_rate_estimate']},
            'limitation':'Numbers are fabricated source-error regimes, not observed event or review correctness. Bands require accurate audit labels and complete random-sample response.'}

if __name__=='__main__':
    print(json.dumps(run(),ensure_ascii=False,indent=2))
