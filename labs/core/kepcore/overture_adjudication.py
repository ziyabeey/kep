"""KEP-DATA-005: blind third-human adjudication + independent holdout design.

This research-only code DOES NOT independently authenticate humans or sources,
prove ground truth, update venue records, publish content, or send notifications.
It preserves every A/B ballot intact and never uses a majority-vote shortcut.
"""
from __future__ import annotations

from collections import defaultdict
from hashlib import sha256
from math import isfinite, log, sqrt
from pathlib import Path
from urllib.parse import urlsplit
import json
import re

from .audit_sampling import _allocated
from .calibration import aware
from .overture_audit import confidence_band
from .overture_field_review import read_review_sheet, conservative_precision_budget
from .overture_real import DATA_DIR, prepare_private_audit

DIMENSION = 'physical_existence'
VERDICTS = frozenset({'exists', 'does_not_exist', 'unknown'})
STRICT_FIELDS = frozenset({
    'overture_id', 'case_sha256', 'dimension', 'outcome', 'reviewer_id',
    'checked_at', 'evidence_url', 'reason',
})
MAX_ADJUDICATION_FILE_BYTES = 250_000


def _canonical(obj: object) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':')).encode('utf-8')


def _case_hash(plan: dict, rid: str, a: dict, b: dict) -> str:
    """Bind the third ballot to the exact two original, still-private ballots."""
    return sha256(_canonical({
        'protocol': 'KEP-DATA-005-v1', 'population_sha256': plan['population_sha256'],
        'seed_commitment_sha256': plan['seed_commitment_sha256'],
        'overture_id': rid, 'a': a, 'b': b,
    })).hexdigest()


def _load_context(*, reviewer_a: str | Path, reviewer_b: str | Path,
                  audit_plan: str | Path, seed_file: str | Path,
                  evaluation_asof: str, directory: Path | str):
    # Reuse the original strict A/B OOXML validator but verify the private
    # sampling plan ONCE per invocation. Do not bypass its immutable-field
    # checks or rely on prior run output.
    cutoff = aware(evaluation_asof)
    plan = json.loads(Path(audit_plan).read_text(encoding='utf-8'))
    seed_path = Path(seed_file)
    if seed_path.is_symlink() or not seed_path.is_file():
        raise ValueError('Unsafe or absent private seed')
    frozen = prepare_private_audit(directory, budget=plan['audit_budget'],
                                  seed=seed_path.read_text(encoding='utf-8').strip(),
                                  sampled_at=plan['sampled_at'])
    if plan != frozen['plan']:
        raise ValueError('Frozen pilot sampling plan changed')
    # The 60 reviewed records are taken straight from the verified immutable
    # frame produced above. No second unverified archive read, and no cached
    # object across calls that could silently ignore on-disk modifications.
    index = {
        row['overture_id']:{**row,'basic_category':row['category']}
        for row in frozen['unlabeled_review_sheet']
    }
    first = read_review_sheet(reviewer_a, role='A', plan=plan, frozen=index,
                              source_run_url=frozen['source_run_url'])
    second = read_review_sheet(reviewer_b, role='B', plan=plan, frozen=index,
                               source_run_url=frozen['source_run_url'])
    a, b = first['votes'],second['votes']
    counts = {state: 0 for state in ('missing','unknown','conflict','concordant')}
    for rid in a:
        counts[_state(a[rid],b[rid],asof=evaluation_asof)] += 1
    base = {
        'study':'KEP-DATA-005','research_only':True,'consumer_publish':False,
        'source_release':plan['source_release'],'population_n':plan['population_n'],
        'selected_n':len(a),'sampled_n_by_stratum':plan['strata'],
        'design_precision_forecast':conservative_precision_budget(plan),
        'reviewer_a_completed':first['completed'],
        'reviewer_b_completed':second['completed'],
        'concordant_resolved':counts['concordant'],
        'missing_or_late':counts['missing'],
        'disagreements':counts['conflict'],
        'unknown_responses':counts['unknown'],
        'requires_third_independent_adjudication':counts['conflict'],
        'survey_label_truth_verified_independently':False,
        'error_fraction_estimate':None,'confidence_band':None,
        'status':'INCOMPLETE_BLIND_AUDIT',
    }
    return base, plan, a, b, index


def _state(a: dict | None, b: dict | None, *, asof: str) -> str:
    if a is None or b is None:
        return 'missing'
    if aware(a['checked_at']) > aware(asof) or aware(b['checked_at']) > aware(asof):
        return 'missing'
    if a['outcome'] == 'unknown' or b['outcome'] == 'unknown':
        return 'unknown'
    if a['outcome'] != b['outcome']:
        return 'conflict'
    return 'concordant'


def blind_case_templates(*, reviewer_a: str | Path, reviewer_b: str | Path,
                         audit_plan: str | Path, seed_file: str | Path,
                         evaluation_asof: str, directory: Path | str = DATA_DIR) -> list[dict]:
    """Issue only conflicted POIs, not either human's decision or reviewer IDs.

    Keep this file off-repo. The case hash binds C to A/B but is not a proof
    of real human independence; it does not include A/B outcomes in plaintext.
    """
    _, plan, a, b, index = _load_context(
        reviewer_a=reviewer_a, reviewer_b=reviewer_b,
        audit_plan=audit_plan, seed_file=seed_file,
        evaluation_asof=evaluation_asof, directory=directory,
    )
    output = []
    for rid in sorted(a):
        if _state(a[rid], b[rid], asof=evaluation_asof) != 'conflict':
            continue
        row = index[rid]
        output.append({
            'overture_id':rid, 'case_sha256':_case_hash(plan,rid,a[rid],b[rid]),
            'dimension':DIMENSION, 'outcome':'not_reviewed', 'reviewer_id':'',
            'checked_at':'', 'evidence_url':'', 'reason':'',
            # No A/B verdicts or reviewer IDs are revealed to the third reader.
            'name': row['name'], 'address':row['address'],
            'lat':row['lat'], 'lon':row['lon'],
        })
    return output


def read_adjudications(path: str | Path) -> dict[str, dict]:
    p = Path(path)
    if (p.is_symlink() or not p.is_file() or not 0 < p.stat().st_size <= MAX_ADJUDICATION_FILE_BYTES):
        raise ValueError('Missing, symlinked or oversized third-review JSONL')
    seen = {}
    # Optionally include read-only name/address/coordinates in a blinded case
    # template. They are checked against the frozen frame before use.
    optional_fields = frozenset({'name','address','lat','lon'})
    for n, line in enumerate(p.read_text(encoding='utf-8').splitlines(),1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            if not isinstance(row,dict) or not (set(row)==STRICT_FIELDS or set(row)==STRICT_FIELDS|optional_fields):
                raise ValueError('Unexpected adjudication fields')
            rid=row['overture_id']
            if not isinstance(rid,str) or rid in seen or not rid:
                raise ValueError('Repeated or missing third-review place ID')
            h=row['case_sha256']
            if not isinstance(h,str) or not re.fullmatch('[0-9a-f]{64}',h):
                raise ValueError('Invalid A/B ballot commitment')
            if row['dimension'] != DIMENSION:
                raise ValueError('Adjudication cannot redefine the measured field')
            if row['outcome'] not in VERDICTS | {'not_reviewed'}:
                raise ValueError('Invalid adjudication outcome')
            if row['outcome']=='not_reviewed':
                if any(row[k] not in ('', None) for k in ('reviewer_id','checked_at','evidence_url','reason')):
                    raise ValueError('Incomplete third ballot must not have partial evidence')
            else:
                name=row['reviewer_id']
                if (not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9][\w.:-]{0,127}',name,re.ASCII)
                    or name.casefold() in {'ai','model','simulator','unknown','reviewer-a','reviewer-b'}):
                    raise ValueError('Independent third human pseudonym required')
                aware(row['checked_at'])
                url=row['evidence_url']
                if not isinstance(url,str) or len(url)>2048 or url.strip()!=url:
                    raise ValueError('Invalid evidence URL')
                u=urlsplit(url)
                if (u.scheme!='https' or not u.hostname or u.username or u.password or u.port not in (None,443)
                    or any(ch.isspace() for ch in url)
                    or (u.hostname.endswith('google.com') and u.path.startswith('/maps/search/'))):
                    raise ValueError('Specific HTTPS third-party evidence required')
                reason=row['reason']
                if not isinstance(reason,str) or not 12 <= len(reason.strip()) <= 1500:
                    raise ValueError('Substantive adjudication explanation required')
            seen[rid]=row
        except (ValueError,TypeError,KeyError) as exc:
            raise ValueError(f'Invalid third-review line {n}: {exc}') from exc
    return seen


def _estimate_from_resolved(plan: dict, outcomes: dict[str,str], *, alpha: float=.05) -> dict:
    """Replicate the frozen design-based estimator, without rewriting A/B votes.

    The third adjudicator supplies a new *final* label only when A/B explicitly
    disagreed. The original votes remain separate immutable source records.
    """
    if not isinstance(alpha,(int,float)) or isinstance(alpha,bool) or not isfinite(alpha) or not 0<alpha<1:
        raise ValueError('Invalid nominal alpha')
    sample=defaultdict(list)
    for row in plan['selected']:
        sample[(row['cell'],row['confidence_band'])].append(row['overture_id'])
    if len(outcomes)!=len(plan['selected']) or set(outcomes)!=set(x['overture_id'] for x in plan['selected']):
        raise ValueError('Incomplete or extra resolved outcomes')
    if not all(x in {'exists','does_not_exist'} for x in outcomes.values()):
        raise ValueError('Unknown outcome must not enter prevalence')
    N=plan['population_n']
    H=len(plan['strata'])
    weighted=radius=0.
    band_counts=defaultdict(lambda:[0.,0])
    details=[]
    for h in sorted(plan['strata'],key=lambda r:(r['cell'],r['confidence_band'])):
        key=(h['cell'],h['confidence_band'])
        n=h['selected_n']; Nh=h['population_n']
        if len(sample[key])!=n or not 1<=n<=Nh:
            raise ValueError('Stratum allocation does not match selection')
        k=sum(outcomes[rid]=='does_not_exist' for rid in sample[key])
        risk=k/n; weight=Nh/N
        weighted+=weight*risk
        radius+=0. if n==Nh else weight*sqrt(log(2*H/alpha)/(2*n))
        band_counts[h['confidence_band']][0]+=Nh*risk
        band_counts[h['confidence_band']][1]+=Nh
        details.append({'cell':h['cell'],'band':h['confidence_band'],'N':Nh,'n':n,
                        'sample_nonexistent_fraction':round(risk,6),
                        'population_weight':round(weight,6)})
    return {'error_fraction_estimate':round(weighted,6),
            'confidence_band':{'lower':round(max(0,weighted-radius),6),
                               'upper':round(min(1,weighted+radius),6),
                               'method':'stratified_Hoeffding_union_bound_fixed_frame',
                               'nominal_coverage':1-alpha},
            'per_confidence_band':[{'band':name,'population_n':int(v[1]),
                                    'weighted_nonexistent_fraction':round(v[0]/v[1],6)}
                                   for name,v in sorted(band_counts.items())],
            'strata':details}


def reconcile(*, reviewer_a:str|Path, reviewer_b:str|Path,
              audit_plan:str|Path, seed_file:str|Path, evaluation_asof:str,
              adjudications:str|Path|None=None,
              directory:Path|str=DATA_DIR) -> dict:
    """Fail closed unless every pilot item has independently resolved final label.

    Deliberate choice: C can settle a binary A/B disagreement, but cannot
    overwrite a missing ballot or either person's `unknown` verdict. Unknown
    requires a separately preregistered re-review procedure, not label forcing.
    """
    base, plan, a, b, index = _load_context(
        reviewer_a=reviewer_a,reviewer_b=reviewer_b,
        audit_plan=audit_plan,seed_file=seed_file,evaluation_asof=evaluation_asof,
        directory=directory,
    )
    c=read_adjudications(adjudications) if adjudications else {}
    conflicts={rid for rid in a if _state(a[rid],b[rid],asof=evaluation_asof)=='conflict'}
    if set(c)-conflicts:
        raise ValueError('Third decision submitted for non-conflicted or unselected place')
    outcomes={}; awaiting=[]; unknown=[]; third_complete=0; third_late=0
    for rid in sorted(a):
        state=_state(a[rid],b[rid],asof=evaluation_asof)
        if state=='concordant':
            outcomes[rid]=a[rid]['outcome']
        elif state=='conflict':
            choice=c.get(rid)
            if choice is None or choice['outcome']=='not_reviewed':
                awaiting.append(rid);continue
            if choice['case_sha256']!=_case_hash(plan,rid,a[rid],b[rid]):
                raise ValueError('Third decision is not bound to unchanged A/B ballots')
            for col,key in [('name','name'),('address','address'),('lat','lat'),('lon','lon')]:
                if col in choice and choice[col]!=index[rid][key]:
                    raise ValueError('Blinded case source fields were altered')
            if choice['reviewer_id'].casefold() in {
                    a[rid]['reviewer_id'].casefold(),b[rid]['reviewer_id'].casefold()}:
                raise ValueError('Third reviewer must differ from both original reviewers')
            if aware(choice['checked_at'])<max(aware(a[rid]['checked_at']),aware(b[rid]['checked_at'])):
                raise ValueError('Adjudication cannot predate both original decisions')
            if aware(choice['checked_at'])>aware(evaluation_asof):
                third_late+=1;awaiting.append(rid);continue
            if choice['outcome']=='unknown':
                unknown.append(rid);continue
            outcomes[rid]=choice['outcome'];third_complete+=1
        elif state=='unknown':unknown.append(rid)
    completed=len(outcomes)
    report={
        **base, 'study':'KEP-DATA-005', 'original_ballots_retained_separately':True,
        'adjudication_policy':'explicit_third_independent_human_only',
        'third_cases_required':len(conflicts), 'third_cases_resolved':third_complete,
        'third_cases_awaiting':len(awaiting), 'third_cases_late':third_late,
        'unresolved_unknown_count':len(unknown),
        'final_resolved_n':completed,
        'dimension':DIMENSION, 'current_operation_verified':False,
        'open_now_verified':False,'coordinate_accuracy_verified':False,
        'error_fraction_estimate':None,'confidence_band':None,
        'survey_label_truth_verified_independently':False,
    }
    if completed!=len(a):
        return {**report,'status':'INCOMPLETE_OR_ADJUDICATION_PENDING'}
    measured=_estimate_from_resolved(plan,outcomes)
    return {**report,**measured,
            'status':('COMPLETE_ADJUDICATED_RESEARCH_DIAGNOSTIC'
                      if conflicts else 'COMPLETE_DESIGN_BASED_DIAGNOSTIC')}


def new_holdout_forecast(plan: dict, *, targets: tuple[float,...]=(.20,.15,.10),
                         alpha:float=.05, reviewer_minutes:float=12.,
                         adjudication_fraction:float=.10,
                         adjudication_minutes:float=15.) -> dict:
    """PRE-REVIEW design/effort forecast; does not draw or label a new sample.

    Excludes the 60 original pilot IDs, changing the estimand to the remaining
    unreviewed 4,743 records. Do NOT describe this as 4,803-frame accuracy.
    """
    strata=plan['strata']
    old_N=plan['population_n']; pilot=plan['audit_budget']
    if (not isinstance(strata,list) or not strata or type(old_N)!=int or type(pilot)!=int
        or sum(h['population_n'] for h in strata)!=old_N
        or sum(h['selected_n'] for h in strata)!=pilot
        or any(type(h['population_n'])!=int or type(h['selected_n'])!=int or h['population_n']<h['selected_n']<1 for h in strata)):
        raise ValueError('Invalid frozen frame')
    if (not isinstance(alpha,(int,float)) or not isfinite(alpha) or not 0<alpha<1
        or any(not isinstance(t,(int,float)) or not isfinite(t) or not 0<t<1 for t in targets)
        or not all(isinstance(v,(float,int)) and isfinite(v) and v>0 for v in (reviewer_minutes,adjudication_minutes))
        or not 0<=adjudication_fraction<=1):
        raise ValueError('Invalid preregistered effort assumptions')
    remain={(h['cell'],h['confidence_band']):h['population_n']-h['selected_n'] for h in strata}
    remain={k:n for k,n in remain.items() if n>0}
    if not remain:
        raise ValueError('No remaining disjoint holdout frame')
    N=sum(remain.values()); H=len(remain)
    from itertools import chain
    groups={k:range(n) for k,n in remain.items()}
    def design(n):
        a=_allocated(groups,n,1)
        radius=sum((Nh/N)*(0 if a[k]==Nh else sqrt(log(2*H/alpha)/(2*a[k])))
                   for k,Nh in remain.items())
        return a,radius
    rows=[]
    for t in targets:
        lo,hi=H,N
        while lo<hi:
            middle=(lo+hi)//2
            _,r=design(middle)
            if r<=t:hi=middle
            else:lo=middle+1
        allocation,radius=design(lo)
        rows.append({
            'target_half_width':t, 'new_holdout_sample_n':lo,
            'achieved_conservative_half_width':round(radius,6),
            'two_reviewers_hours':round(2*lo*reviewer_minutes/60,2),
            'expected_extra_adjudication_hours':round(lo*adjudication_fraction*adjudication_minutes/60,2),
            'assumed_adjudication_fraction':adjudication_fraction,
            'allocation':[{'cell':k[0],'confidence_band':k[1],
                           'eligible_n':remain[k],'proposed_n':allocation[k]}
                          for k in sorted(remain)],
        })
    return {'study':'KEP-DATA-005','mode':'DESIGN_ONLY_NO_NEW_SAMPLE_DRAWN',
            'research_only':True,'consumer_publish':False,
            'original_population_n':old_N,'excluded_existing_pilot_n':pilot,
            'new_disjoint_frame_n':N,'estimand':'remaining_unreviewed_POIs_only',
            'pilot_ids_cannot_be_reused':True,'private_new_seed_required':True,
            'nominal_confidence':1-alpha,'method':'stratified_Hoeffding_union_bound',
            'forecast':rows,
            'limitations':'Assumes correct and complete independent human labels, SRS in each stratum, no selection based on results, fixed 2026-09-23.1 frame; NOT a power calculation based on observed error variance.'}
