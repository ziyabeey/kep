"""KEP-DATA-002: integrity checks and survey-valid POI existence audit.

No network, no direct publishing and NO claim of independent upstream provenance.
The original raw Overture bytes are NOT included in the manual GitHub artifact.
Any externally supplied manifest can be forged; the checks below detect local
inconsistencies or post-acquisition corruption, not who created the files.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from hashlib import sha256
from math import isfinite, log, sqrt
from pathlib import Path
from random import Random
from urllib.parse import urlsplit
from typing import Any
import json
import re
import uuid

from .audit_sampling import _allocated
from .calibration import aware
from .overture_places import (
    PILOT, MAX_INPUT_BYTES, MAX_FEATURES, canonical, check_release,
    potential_duplicates,
)

POLICY = 'KEP-DATA-002-SRS-CONFIDENCE-v1'
BANDS = ('missing', 'low', 'medium', 'high')
MAX_ARTIFACT_BYTES = 16_000_000
SOURCE_FILES = ('besiktas_center', 'karakoy_center')
MINIMAL_FIELDS = frozenset({
    'overture_id', 'name', 'taxonomy_primary', 'basic_category', 'lon', 'lat',
    'cell', 'confidence', 'operating_status', 'address', 'locality', 'country',
    'source_provenance', 'open_now', 'opening_hours', 'live_price',
    'active_event', 'consumer_verified', 'administrative_district',
})
SHA_RE = re.compile(r'^[0-9a-f]{64}$')
VALID_OUTCOMES = frozenset({'exists', 'does_not_exist', 'unknown'})


def confidence_band(confidence: float | None) -> str:
    """Preregistered diagnostic bins; NOT calibrated risk thresholds."""
    if confidence is None:
        return 'missing'
    if (isinstance(confidence, bool) or not isinstance(confidence, (float, int))
            or not isfinite(confidence) or not 0 <= confidence <= 1):
        raise ValueError('Invalid existence confidence')
    return 'low' if confidence <= .50 else 'medium' if confidence <= .80 else 'high'


def _bounded_json(path: Path) -> tuple[dict, bytes]:
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= MAX_ARTIFACT_BYTES:
        raise ValueError('Missing, unsafe or oversized artifact')
    data = path.read_bytes()
    obj = json.loads(data)
    if not isinstance(obj, dict) or canonical(obj) != data:
        raise ValueError('Artifact must have canonical JSON object bytes')
    return obj, data


def _validated_record(row: Any) -> tuple[str, str]:
    if not isinstance(row, dict) or frozenset(row) != MINIMAL_FIELDS:
        raise ValueError('Wrong minimal POI schema; possible extraneous personal data')
    rid = row['overture_id']
    if not isinstance(rid, str):
        raise ValueError('Invalid Overture UUID')
    try:
        if str(uuid.UUID(rid)) != rid:
            raise ValueError('Invalid canonical Overture UUID')
    except (ValueError, AttributeError) as exc:
        raise ValueError('Invalid Overture UUID') from exc
    cell = row['cell']
    if cell not in PILOT:
        raise ValueError('Unregistered pilot cell')
    xy = (row['lon'], row['lat'])
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v) for v in xy):
        raise ValueError('Invalid POI coordinates')
    west,south,east,north = PILOT[cell]
    if not (west <= xy[0] <= east and south <= xy[1] <= north):
        raise ValueError('POI outside its sampling cell')
    for key in ('name','taxonomy_primary','basic_category','address','locality','country'):
        if row[key] is not None and (not isinstance(row[key],str) or len(row[key])>300):
            raise ValueError('Invalid POI string field')
    if row['consumer_verified'] is not False:
        raise ValueError('Research record must not assert consumer verification')
    for key in ('open_now','opening_hours','live_price','active_event','administrative_district'):
        if row[key] is not None:
            raise ValueError('Unsupported real-time/admin POI claim')
    if row['operating_status'] not in (None,'open','temporarily_closed','permanently_closed'):
        raise ValueError('Unexpected Overture operating_status')
    confidence_band(row['confidence'])
    if not isinstance(row['source_provenance'], list) or len(row['source_provenance'])>8:
        raise ValueError('Invalid source provenance')
    for src in row['source_provenance']:
        if (not isinstance(src,dict) or set(src)!={'dataset','provider','license'}
                or any(v is not None and (not isinstance(v,str) or len(v)>120) for v in src.values())):
            raise ValueError('Invalid provider attribution')
    return rid, cell


def verify_artifact(directory: str | Path, *, require_live: bool=False) -> dict:
    """Verify local JSON consistency, not the upstream author's identity.

    The runner must retain original raw files/provenance off-repo for true
    acquisition chain-of-custody; mere hash strings do not authenticate S3.
    """
    base=Path(directory).expanduser().resolve()
    if not base.is_dir():
        raise ValueError('Artifact directory missing')
    data, data_bytes=_bounded_json(base/'places_minimal.json')
    manifest, manifest_bytes=_bounded_json(base/'manifest.json')
    if set(data)!={'dataset','release','study_only','records'}:
        raise ValueError('Unexpected output envelope fields')
    accepted_manifest_keys={'study','pinned_release','schema','research_only',
                            'consumer_display_approved','license_evidence_url',
                            'sample_cell_bounds_not_district_boundary','acquisition',
                            'source_files','normalized_sha256','population_sha256',
                            'audit','human_verified_labels','no_automatic_entity_merge',
                            'release_quality_claim'}
    if set(manifest)!=accepted_manifest_keys:
        raise ValueError('Unexpected manifest envelope fields')
    if manifest.get('study')!='KEP-DATA-001' or data.get('dataset')!='KEP-DATA-001':
        raise ValueError('Wrong study identifiers')
    if data.get('study_only') is not True or manifest.get('research_only') is not True or manifest.get('consumer_display_approved') is not False:
        raise ValueError('Research-only scope violated')
    release=manifest.get('pinned_release')
    check_release(release)
    if data.get('release')!=release:
        raise ValueError('Source release inconsistent')
    root=Path(__file__).resolve().parents[1]
    cfg=json.loads((root/'sources/overture_places_pilot.json').read_text(encoding='utf-8'))
    if release!=cfg['release'] or manifest.get('schema')!=cfg['schema']:
        raise ValueError('Unapproved release or schema')
    if manifest.get('sample_cell_bounds_not_district_boundary')!=cfg['cells']:
        raise ValueError('Sampling frame changed')
    if manifest.get('license_evidence_url')!=cfg['rights']['attribution_url']:
        raise ValueError('Source attribution missing/modified')
    if manifest.get('normalized_sha256')!=sha256(data_bytes).hexdigest():
        raise ValueError('Normalized file hash mismatch')
    records=data.get('records')
    if not isinstance(records,list) or len(records)>MAX_FEATURES:
        raise ValueError('Invalid POI population count')
    ids=[]
    for row in records:
        rid,_=_validated_record(row)
        ids.append(rid)
    if ids!=sorted(set(ids)):
        raise ValueError('POI IDs must be unique and in deterministic order')
    population_hash=sha256(canonical(records)).hexdigest()
    if population_hash!=manifest.get('population_sha256'):
        raise ValueError('Frozen POI frame hash mismatch')
    sources=manifest.get('source_files')
    if not isinstance(sources,list) or len(sources)!=len(SOURCE_FILES):
        raise ValueError('Expected both pilot source cells')
    if sorted(s.get('cell') for s in sources if isinstance(s,dict))!=sorted(SOURCE_FILES):
        raise ValueError('Missing/duplicated source cell')
    for entry in sources:
        if set(entry)!={'cell','sha256','bytes'}:
            raise ValueError('Unexpected raw source metadata')
        if (not isinstance(entry.get('sha256'),str) or not SHA_RE.fullmatch(entry['sha256'])
                or type(entry.get('bytes')) is not int or not 0 < entry['bytes'] <= MAX_INPUT_BYTES):
            raise ValueError('Invalid raw-source hash declaration')
    audit=manifest.get('audit')
    audit_keys={'rows_read','accepted','rejected','duplicate_identical_ids',
                'potential_duplicate_pairs','unknown_name','unknown_taxonomy',
                'unknown_address','missing_confidence','unknown_source_provenance',
                'mean_overture_confidence_not_truth','claim_verified_place_count',
                'claim_verified_open_now_count','human_audited_count'}
    if not isinstance(audit,dict) or set(audit)!=audit_keys:
        raise ValueError('Unexpected audit report fields')
    if audit.get('accepted') != len(records):
        raise ValueError('Declared accepted count disagrees with file')
    if type(audit.get('rows_read')) is not int or audit['rows_read'] < len(records):
        raise ValueError('Invalid processed row count')
    rejected=audit.get('rejected')
    duplicates=audit.get('duplicate_identical_ids')
    if (not isinstance(rejected,dict) or any(type(v) is not int or v<0 for v in rejected.values())
            or type(duplicates) is not int or duplicates<0
            or audit['rows_read']!=len(records)+duplicates+sum(rejected.values())):
        raise ValueError('Raw row accounting mismatch')
    for key, f in {
        'unknown_name':lambda r:r['name'] is None,
        'unknown_taxonomy':lambda r:r['taxonomy_primary'] is None,
        'unknown_address':lambda r:r['address'] is None,
        'missing_confidence':lambda r:r['confidence'] is None,
        'unknown_source_provenance':lambda r:not r['source_provenance'],
    }.items():
        if audit.get(key)!=sum(f(r) for r in records):
            raise ValueError(f'Audit {key} count mismatch')
    known=[r['confidence'] for r in records if r['confidence'] is not None]
    expected_mean=round(sum(known)/len(known),5) if known else None
    if audit.get('mean_overture_confidence_not_truth')!=expected_mean:
        raise ValueError('Mean Overture confidence summary mismatch')
    if audit.get('potential_duplicate_pairs')!=potential_duplicates(records):
        raise ValueError('Duplicate candidate report mismatch')
    for key in ('claim_verified_place_count','claim_verified_open_now_count','human_audited_count'):
        if audit.get(key)!=0:
            raise ValueError('Unjustified place verification claim')
    if manifest.get('human_verified_labels')!=0 or manifest.get('no_automatic_entity_merge') is not True:
        raise ValueError('Research release contract violated')
    acq=manifest.get('acquisition')
    if not isinstance(acq,dict):
        raise ValueError('Missing acquisition provenance declaration')
    method=acq.get('method')
    if method not in ('operator_supplied_local_files','manual_overturemaps_cli_stac_pinned'):
        raise ValueError('Unknown acquisition method')
    live=(method=='manual_overturemaps_cli_stac_pinned')
    if require_live and not live:
        raise ValueError('Manually fetched release required; supplied files insufficient')
    if live:
        if set(acq)!={'method','downloaded_at_utc','client_version',
                       'stac_catalog_sha256_before','stac_catalog_sha256_after'}:
            raise ValueError('Unexpected live acquisition fields')
        if any(not isinstance(acq.get(x),str) or not SHA_RE.fullmatch(acq[x])
               for x in ('stac_catalog_sha256_before','stac_catalog_sha256_after')):
            raise ValueError('Missing pinned source catalog hashes')
        if not isinstance(acq.get('client_version'),str) or not acq['client_version']:
            raise ValueError('Missing downloading client version')
        aware(acq.get('downloaded_at_utc'))
    else:
        if set(acq)!={'method','network_fetch_performed','warning'}:
            raise ValueError('Unexpected local acquisition fields')
        if acq.get('network_fetch_performed') is not False:
            raise ValueError('Local data cannot assert network fetch')
    return {
        'study':'KEP-DATA-002','artifact_integrity_verified':True,
        'raw_source_sha256_independently_verified':False,
        'upstream_acquisition_authenticated':False,
        'real_world_place_existence_verified':False,
        'source_acquisition_claim':method,
        'research_only':True,'consumer_publish':False,
        'release':release,'population_n':len(records),
        'population_sha256':population_hash,
        'manifest_sha256':sha256(manifest_bytes).hexdigest(),
        'missing_name':audit['unknown_name'],
        'missing_taxonomy':audit['unknown_taxonomy'],
        'possible_duplicate_pairs':len(audit['potential_duplicate_pairs']),
    }


def _frame(dirpath: str | Path) -> tuple[list[dict],dict]:
    info=verify_artifact(dirpath)
    records=json.loads((Path(dirpath)/'places_minimal.json').read_bytes())['records']
    return records,info


def design_existence_audit(directory: str | Path, *, budget: int, seed: str, sampled_at: str) -> dict:
    """Freeze stratified sample by bbox and confidence; seed remains private."""
    if not isinstance(seed,str) or len(seed)<16:
        raise ValueError('Off-repo 16+ char private seed required')
    freeze_at=aware(sampled_at)
    records,frame=_frame(directory)
    acquisition=json.loads((Path(directory)/'manifest.json').read_bytes()).get('acquisition',{})
    if acquisition.get('method')=='manual_overturemaps_cli_stac_pinned' and aware(acquisition['downloaded_at_utc'])>freeze_at:
        raise ValueError('Cannot freeze audit draw before acquisition')
    if not records:
        raise ValueError('Cannot sample an empty population')
    strata=defaultdict(list)
    for row in records:
        strata[(row['cell'],confidence_band(row['confidence']))].append(row)
    allocation=_allocated(strata,budget,1)
    selected=[];details=[]
    for key in sorted(strata):
        candidates=sorted(strata[key],key=lambda x:x['overture_id'])
        n=allocation[key]
        salt=sha256((seed+'|'+frame['population_sha256']+'|'+':'.join(key)).encode()).digest()
        chosen=Random(int.from_bytes(salt,'big')).sample(candidates,n)
        pi=n/len(candidates)
        details.append({'cell':key[0],'confidence_band':key[1],
                        'population_n':len(candidates),'selected_n':n,
                        'inclusion_probability':pi})
        for row in chosen:
            selected.append({'overture_id':row['overture_id'],'cell':key[0],
                             'confidence_band':key[1], 'inclusion_probability':pi})
    return {
        'study':'KEP-DATA-002','policy_version':POLICY,
        'research_only':True,'consumer_publish':False,
        'source_acquisition_claim':frame['source_acquisition_claim'],
        'source_release':frame['release'],'population_n':len(records),
        'population_sha256':frame['population_sha256'],'manifest_sha256':frame['manifest_sha256'],
        'seed_commitment_sha256':sha256(seed.encode()).hexdigest(),
        'audit_budget':budget,'sampled_at':sampled_at,'strata':details,
        'selected':sorted(selected,key=lambda x:x['overture_id']),
        'field_to_review':'physical_existence',
        'pre_registered_bands':{'low':'score <= 0.50','medium':'0.50 < score <= 0.80',
                                 'high':'score > 0.80','missing':'score not present'},
        'review_labels_in_plan':False,'verified_labels':0,
    }


def _vote(v:dict, *, sample_id: str, asof:datetime) -> str | None:
    if not isinstance(v,dict) or set(v)!={'reviewer_id','outcome','checked_at','evidence_url'}:
        raise ValueError('Strict human vote schema required')
    user=v['reviewer_id']
    if (not isinstance(user,str) or not re.fullmatch(r'[A-Za-z0-9][\w.:-]{0,127}',user,re.ASCII)
        or user.casefold() in {'ai','model','unknown','simulator'}):
        raise ValueError('Independent human reviewer identifier required')
    if v['outcome'] not in VALID_OUTCOMES:
        raise ValueError('Unknown existence label')
    t=aware(v['checked_at'])
    if t > asof:
        return None
    url=v['evidence_url']
    if (not isinstance(url,str) or len(url)>2048 or urlsplit(url).scheme!='https'
        or not urlsplit(url).hostname or urlsplit(url).username or urlsplit(url).password):
        raise ValueError('HTTPS review citation required')
    return v['outcome']


def estimate_existence_error(directory: str|Path, *, plan:dict, seed:str,
                             labels:list[dict], evaluation_asof:str, alpha:float=.05) -> dict:
    """Only COMPLETE, double-reviewed, design-based existence prevalence.

    A recorded reviewer ID is not proof of independent people or ground truth.
    Estimates describe a frozen frame; they do not establish business hours.
    """
    if not isinstance(alpha,(int,float)) or isinstance(alpha,bool) or not isfinite(alpha) or not 0<alpha<1:
        raise ValueError('Invalid alpha')
    if not isinstance(plan,dict) or not isinstance(plan.get('seed_commitment_sha256'),str):
        raise ValueError('Missing audit plan')
    if sha256(seed.encode()).hexdigest()!=plan['seed_commitment_sha256']:
        raise ValueError('Audit seed commitment mismatch')
    rebuilt=design_existence_audit(directory,budget=plan['audit_budget'],seed=seed,
                                   sampled_at=plan['sampled_at'])
    if plan!=rebuilt:
        raise ValueError('Tampered audit plan / population / inclusion probability')
    cutoff=aware(evaluation_asof)
    if cutoff <= aware(plan['sampled_at']):
        raise ValueError('Review evaluation must occur after frozen draw')
    frame,_=_frame(directory)
    rows_by_id={r['overture_id']:r for r in frame}
    ids={s['overture_id'] for s in plan['selected']}
    outcome={}
    for label in labels:
        if not isinstance(label,dict) or set(label)!={'overture_id','votes'}:
            raise ValueError('Unexpected existence review label fields')
        rid=label['overture_id']
        if rid not in ids or rid in outcome:
            raise ValueError('Non-random/duplicate audit outcome')
        votes=label['votes']
        if not isinstance(votes,list) or len(votes)!=2:
            raise ValueError('Two human ballots are required for sampled existence')
        if votes[0].get('reviewer_id','').casefold()==votes[1].get('reviewer_id','').casefold():
            raise ValueError('Independent human reviewer IDs required')
        for vote in votes:
            if aware(vote['checked_at']) < aware(plan['sampled_at']):
                raise ValueError('Reviewer decision predates frozen audit draw')
        checked=[_vote(v,sample_id=rid,asof=cutoff) for v in votes]
        outcome[rid]=checked[0] if len(set(checked))==1 and checked[0] in {'exists','does_not_exist'} else None
    missing=sorted(ids-set(outcome))
    unresolved=sorted(rid for rid,x in outcome.items() if x is None)
    base={
        'study':'KEP-DATA-002','research_only':True,'consumer_publish':False,
        'sample_n':len(ids),'reviewed_resolved_n':len(ids)-len(missing)-len(unresolved),
        'missing_n':len(missing),'unresolved_or_conflicting_n':len(unresolved),
        'population_n':len(frame),'source_release':plan['source_release'],
        'population_sha256':plan['population_sha256'],
        'independent_reviewers_verified_in_person':False,
        'real_world_verification_guaranteed':False,
    }
    if missing or unresolved:
        return {**base,'status':'INCOMPLETE_OR_CONFLICTING_REVIEWS',
                'error_fraction_estimate':None,'confidence_band':None,
                'caution':'No population rate with incomplete/uncertain audit labels.'}
    group=defaultdict(list)
    for row in frame:
        group[(row['cell'],confidence_band(row['confidence']))].append(row)
    sample=defaultdict(list)
    for chosen in plan['selected']:
        sample[(chosen['cell'],chosen['confidence_band'])].append(chosen)
    weighted=0.;radius=0.;by_band=defaultdict(lambda:[0.,0]);details=[]
    H=len(group)
    for key in sorted(group):
        n=len(sample[key]);N=len(group[key]);k=sum(outcome[s['overture_id']]=='does_not_exist' for s in sample[key]);
        risk=k/n;weight=N/len(frame)
        weighted+=weight*risk
        radius+=0. if n==N else weight*sqrt(log(2*H/alpha)/(2*n))
        by_band[key[1]][0]+=N*risk
        by_band[key[1]][1]+=N
        details.append({'cell':key[0],'band':key[1],'N':N,'n':n,
                        'sample_nonexistent_fraction':round(risk,6),
                        'population_weight':round(weight,6)})
    return {**base,'status':'COMPLETE_DESIGN_BASED_DIAGNOSTIC',
            'error_fraction_estimate':round(weighted,6),
            'confidence_band':{'lower':round(max(0,weighted-radius),6),
                               'upper':round(min(1,weighted+radius),6),
                               'method':'stratified_Hoeffding_union_bound_fixed_frame',
                               'nominal_coverage':1-alpha},
            'per_confidence_band':[{'band':k,'population_n':int(v[1]),
                                   'weighted_nonexistent_fraction':round(v[0]/v[1],6)}
                                    for k,v in sorted(by_band.items())],
            'strata':details,
            'assumptions':['complete frozen sampling frame','uniform random sampling within strata',
                           'accurate independent human labels','no unlogged review edits',
                           'no claim about unsampled future releases'],
    }
