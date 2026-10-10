"""KEP-SCI-003: designed randomized source audits, separate from targeted reviews.

This is OFFLINE research infrastructure. Only a frozen, rights-checked finite
population can be audited. No scraper, AI, or consumer publish functionality.

Do not interpret an audit label as proof of truth: actual human independence,
label correctness and sampling assumptions require an external process.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from hashlib import sha256
from math import isfinite, log, sqrt
from pathlib import Path
from random import Random
from typing import Mapping
import json

from .calibration import ReviewedClaim, aware
from .review_intake import ReviewCandidate, verify_research_snapshots

POLICY = 'KEP-SCI-003-SRS-STRATIFIED-v1'


def _population(candidates: list[ReviewCandidate], *, sources: Mapping,
                asof: str, snapshot_dir: str | Path) -> tuple[list[ReviewCandidate], str]:
    cutoff = aware(asof)
    if not candidates:
        raise ValueError('Audit population cannot be empty')
    ids, roots = set(), set()
    for c in candidates:
        if not isinstance(c, ReviewCandidate):
            raise TypeError('ReviewCandidate records required')
        if c.claim_id in ids:
            raise ValueError('Repeated candidate identifier')
        ids.add(c.claim_id)
        key = (c.entity_id, c.field, c.publisher_root, aware(c.predicted_at))
        if key in roots:
            raise ValueError('Same publisher-root repost cannot be sampled twice')
        roots.add(key)
        if aware(c.observed_at) > cutoff or aware(c.predicted_at) >= cutoff:
            raise ValueError('Cannot sample future or not-yet-decided claims')
    # Requires the approved registry and immutable local source bytes. Does NOT
    # assert that an event is true or that a human evaluator was independent.
    verify_research_snapshots(candidates, snapshot_dir, registry=dict(sources))
    ordered = sorted(candidates, key=lambda x: x.claim_id)
    canonical = [
        (c.claim_id, c.entity_id, c.field, c.claimed_value, c.publisher_root,
         c.source_id, c.source_url, c.city, c.claimed_at, c.observed_at,
         c.predicted_at, c.snapshot_sha256, c.rights_scope)
        for c in ordered
    ]
    digest = sha256(json.dumps(canonical, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    return ordered, digest


def _stratum(c: ReviewCandidate) -> tuple[str, str]:
    return c.publisher_root, c.field


def _allocated(groups: dict[tuple[str,str], list], budget: int,
               min_per_stratum: int) -> dict[tuple[str,str], int]:
    if not isinstance(budget, int) or isinstance(budget, bool) or budget < 1:
        raise ValueError('Positive integer audit budget required')
    if not isinstance(min_per_stratum, int) or isinstance(min_per_stratum, bool) or min_per_stratum < 1:
        raise ValueError('Invalid minimum audit sample')
    total = sum(map(len, groups.values()))
    if budget > total:
        raise ValueError('Budget exceeds frozen population')
    minimum = {k: min(min_per_stratum, len(v)) for k, v in groups.items()}
    if budget < sum(minimum.values()):
        raise ValueError('Budget cannot cover the minimum for each stratum')
    allocated = dict(minimum)
    # Largest deficit from proportional allocation, with deterministic ties.
    # Counts are fixed BEFORE drawing any random sample or seeing any label.
    while sum(allocated.values()) < budget:
        eligible = [k for k in groups if allocated[k] < len(groups[k])]
        if not eligible:
            raise AssertionError('Budget allocation has no remaining capacity')
        chosen = min(eligible, key=lambda k: (
            -(budget*len(groups[k])/total - allocated[k]), k))
        allocated[chosen] += 1
    return allocated


def design_random_audit(candidates: list[ReviewCandidate], *, sources: Mapping,
                        snapshot_dir: str | Path, asof: str, budget: int,
                        seed: str, min_per_stratum: int=2,
                        synthetic: bool=False) -> dict:
    """Select a stratified SRS without using outcome labels or model scores.

    In a live deployment seed must be generated privately and stored off-repo;
    only its hash is recorded. Synthetic tests use fixed public seeds.
    """
    if not isinstance(seed, str) or len(seed) < 16:
        raise ValueError('Sampling seed must be a private 16+ character string')
    ordered, population_hash = _population(candidates, sources=sources,
                                           asof=asof, snapshot_dir=snapshot_dir)
    strata: dict[tuple[str, str], list[ReviewCandidate]] = defaultdict(list)
    for c in ordered:
        strata[_stratum(c)].append(c)
    counts = _allocated(strata, budget, min_per_stratum)
    selected = []
    details = []
    for key in sorted(strata):
        members = sorted(strata[key], key=lambda c: c.claim_id)
        k = counts[key]
        salt = sha256((seed + '|' + population_hash + '|' + '\x00'.join(key)).encode()).hexdigest()
        picked = sorted(Random(int(salt,16)).sample(members,k), key=lambda x:x.claim_id)
        pi = k/len(members)
        details.append({'publisher_root':key[0], 'field':key[1],
                        'population_n':len(members), 'selected_n':k,
                        'inclusion_probability':pi})
        for c in picked:
            selected.append({'claim_id':c.claim_id,'entity_id':c.entity_id,
                             'field':c.field,'publisher_root':c.publisher_root,
                             'source_id':c.source_id,'snapshot_sha256':c.snapshot_sha256,
                             'inclusion_probability':pi, 'method':'stratified_random'})
    return {'study':'KEP-SCI-003','policy_version':POLICY,
            'research_only':True, 'allow_auto_publish':False,
            'origin':'synthetic' if synthetic else 'human_review',
            'asof':asof,'population_sha256':population_hash,
            'seed_sha256':sha256(seed.encode()).hexdigest(),
            'population_n':len(ordered),'budget':budget,
            'min_per_stratum':min_per_stratum,
            'strata':details,'selected':sorted(selected,key=lambda x:x['claim_id']),
            'targeted_reviews_in_estimator':False,
            'caution':'SRS is only valid for a frozen frame; review nonresponse and reviewer mistakes can bias findings.'}


def estimate_population_error(plan: dict, candidates: list[ReviewCandidate],
                              reviews: list[ReviewedClaim], *, sources: Mapping,
                              snapshot_dir: str | Path, evaluation_asof: str, replay_seed: str,
                              alpha: float=.05) -> dict:
    """Estimate the finite population's error rate from FULLY adjudicated random audit.

    The optional confidence band is conservative via per-stratum Hoeffding +
    union bound. It assumes truly random without-replacement samples within
    frozen strata, accurate reviews and no unobserved label nonresponse. Not a
    guarantee for future data, clustered error processes or publisher drift.
    """
    if plan.get('policy_version') != POLICY or not plan.get('research_only'):
        raise ValueError('Unrecognized research audit plan')
    if not isinstance(alpha,(int,float)) or not isfinite(alpha) or not 0<alpha<1:
        raise ValueError('Alpha must be between zero and one')
    cutoff = aware(evaluation_asof)
    if cutoff < aware(plan['asof']):
        raise ValueError('Cannot evaluate an audit before its sampling time')
    population, digest = _population(candidates,sources=sources,
                                    asof=plan['asof'],snapshot_dir=snapshot_dir)
    if plan['population_sha256'] != digest or plan['population_n'] != len(population):
        raise ValueError('Audit population changed since randomization')
    # A cryptographic commitment to the seed, plus exact deterministic replay,
    # prevents post-review cherry-picking of random audit IDs. The private seed
    # must be archived outside git until the frame and draw have been frozen.
    if not isinstance(replay_seed, str) or sha256(replay_seed.encode()).hexdigest() != plan.get('seed_sha256'):
        raise ValueError('Sampling seed does not match precommitted audit seed')
    original = design_random_audit(population,sources=sources,snapshot_dir=snapshot_dir,
        asof=plan['asof'],budget=plan['budget'],seed=replay_seed,
        min_per_stratum=plan['min_per_stratum'],synthetic=plan['origin']=='synthetic')
    if plan != original:
        raise ValueError('Audit plan altered after sample design; deterministic replay mismatch')
    groups: dict[tuple[str,str],list[ReviewCandidate]]=defaultdict(list)
    by_id={c.claim_id:c for c in population}
    for c in population:groups[_stratum(c)].append(c)
    selected=plan['selected']
    selections={r['claim_id']:r for r in selected}
    if len(selections)!=len(selected) or len(selected)!=plan['budget']:
        raise ValueError('Duplicate or missing selection in audit plan')
    counts=Counter((r['publisher_root'],r['field']) for r in selected)
    if len(plan['strata']) != len(groups):
        raise ValueError('Missing audit stratum')
    for entry in plan['strata']:
        key=(entry['publisher_root'],entry['field'])
        if key not in groups or entry['population_n'] != len(groups[key]) or entry['selected_n'] != counts[key]:
            raise ValueError('Audit stratum size changed')
        if not (0 < counts[key] <= len(groups[key])):
            raise ValueError('Uncovered audit stratum')
    for item in selected:
        c=by_id.get(item['claim_id'])
        if c is None or any((item[k]!=getattr(c,k)) for k in ('entity_id','field','publisher_root','source_id','snapshot_sha256')):
            raise ValueError('Selected claim identity differs from frozen frame')
        correct_pi=counts[_stratum(c)]/len(groups[_stratum(c)])
        if item['method']!='stratified_random' or abs(item['inclusion_probability']-correct_pi)>1e-12:
            raise ValueError('Audit inclusion probability mismatch')
    outcomes={}
    for review in reviews:
        if not isinstance(review,ReviewedClaim):
            raise TypeError('ReviewedClaim required')
        if review.claim_id not in selections:
            raise ValueError('Targeted/non-random reviews cannot enter population estimator')
        if review.claim_id in outcomes:
            raise ValueError('Multiple adjudicated outcomes for sampled claim')
        sample=selections[review.claim_id]
        original_candidate = by_id[review.claim_id]
        if (review.entity_id!=sample['entity_id'] or review.field!=sample['field']
            or review.publisher_root!=sample['publisher_root']
            or review.source_id!=sample['source_id']
            or review.snapshot_sha256!=sample['snapshot_sha256']
            or review.city!=original_candidate.city
            or review.claimed_at!=original_candidate.claimed_at
            or aware(review.observed_at)!=aware(original_candidate.observed_at)
            or aware(review.predicted_at)!=aware(original_candidate.predicted_at)
            or review.rights_scope!=original_candidate.rights_scope
            or review.origin!=plan['origin']):
            raise ValueError('Review is not bound to its audit snapshot and origin')
        if aware(review.checked_at) < cutoff:
            outcomes[review.claim_id]=review.outcome
    missing=[r['claim_id'] for r in selected if outcomes.get(r['claim_id']) not in ('correct','incorrect')]
    counters=Counter(outcomes.get(r['claim_id'],'not_yet_reviewed') for r in selected)
    base={'study':'KEP-SCI-003','research_only':True,'allow_auto_publish':False,
          'population_n':len(population),'sample_n':len(selected),
          'resolved_n':len(selected)-len(missing),'unresolved_n':len(missing),
          'audit_label_counts':dict(counters),
          'origin':plan['origin'],'policy_version':plan['policy_version'],
          'population_sha256':digest,'risk_is_event_prediction':False}
    if missing:
        return {**base,'status':'INCOMPLETE_NONRESPONSE','error_rate_estimate':None,
                'confidence_band':None,
                'reason':'Sampled claims are not all independently adjudicated before cutoff; no population-rate estimate.'}
    n=len(population)
    h=len(groups)
    weighted=0.
    radius=0.
    sum_weights=0.
    sum_sq_weights=0.
    by_stratum=[]
    for key in sorted(groups):
        members=[r for r in selected if (r['publisher_root'],r['field'])==key]
        Nh=len(groups[key]);nh=len(members)
        bad=sum(outcomes[r['claim_id']]=='incorrect' for r in members)
        p=bad/nh
        weight=Nh/n
        weighted+=weight*p
        epsilon=0 if nh==Nh else sqrt(log(2*h/alpha)/(2*nh))
        radius+=weight*epsilon
        pi=nh/Nh
        sum_weights+=nh/pi
        sum_sq_weights+=nh/(pi*pi)
        by_stratum.append({'publisher_root':key[0],'field':key[1],
                          'population_n':Nh,'sample_n':nh,
                          'sample_error_fraction':round(p,6),
                          'inclusion_probability':round(pi,8)})
    ess=sum_weights*sum_weights/sum_sq_weights
    return {**base,'status':'COMPLETE_STRATIFIED_AUDIT',
            'error_rate_estimate':round(weighted,6),
            'confidence_band':{'lower':round(max(0.,weighted-radius),6),
                               'upper':round(min(1.,weighted+radius),6),
                               'method':'finite_population_stratified_Hoeffding_union_bound',
                               'confidence_level':1-alpha},
            'effective_sample_size':round(ess,3),
            'by_stratum':by_stratum,
            'assumptions':['fixed complete sampling frame','SRS without replacement within each stratum',
                           'all sampled labels resolved independently and correctly',
                           'no unlogged audit changes','future source drift not covered']}
