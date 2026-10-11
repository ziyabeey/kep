"""KEP-DATA-006: version-to-version change in *source records*, not city ground truth.

No requests, no fuzzy entity auto-merges, no consumer publication. Overture
'added' != newly opened business, 'removed' != closed business. Same-ID
coordinate changes are cartographic/data changes, not proof of relocation.

Two genuinely observed releases are REQUIRED before publishing a real-source
change count. A synthetic second snapshot can exercise code but never supports
claims about changes in Istanbul.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
import json

from .calibration import aware
from .overture_audit import _validated_record, confidence_band
from .overture_places import PILOT, MAX_FEATURES, _name_key, canonical, check_release, metres_between
from .overture_real import DATA_DIR, load_archive

MAX_COMPARISON_BYTES = 16_000_000
MAX_MANIFEST_BYTES = 32_000
LIMITED_FIELDS = ('name', 'address', 'basic_category', 'taxonomy_primary',
                  'operating_status', 'locality', 'country', 'source_provenance')
SCHEMA = 'Overture Places schema 2.0 (taxonomy / basic_category)'


@dataclass(frozen=True)
class ResearchSnapshot:
    release: str
    observed_at: str
    normalized_sha256: str
    population_sha256: str
    origin: str
    records: tuple[dict, ...]
    sampling_cells: tuple[str, ...]
    schema: str = SCHEMA

    def __post_init__(self) -> None:
        check_release(self.release)
        when = aware(self.observed_at)
        release_date = datetime.fromisoformat(self.release[:10]).date()
        if when.date() < release_date:
            raise ValueError('Snapshot observed before release date')
        if self.origin not in {'pinned_real_archive', 'operator_supplied_research', 'synthetic_future'}:
            raise ValueError('Unknown origin / fixture provenance')
        if self.schema != SCHEMA:
            raise ValueError('Incompatible Overture schema: explicit reviewed migration required')
        if self.sampling_cells != tuple(sorted(PILOT)):
            raise ValueError('Changed or incomplete geographic sampling scope')
        if not self.records or len(self.records) > MAX_FEATURES:
            raise ValueError('Unbounded or empty release population')
        ids = set()
        for item in self.records:
            rid,cell = _validated_record(item)
            if rid in ids or cell not in self.sampling_cells:
                raise ValueError('Repeated identity or unexpected sampling cell')
            ids.add(rid)
        if [r['overture_id'] for r in self.records] != sorted(ids):
            raise ValueError('Record order must be deterministic by Overture ID')
        hash_now = sha256(canonical(list(self.records))).hexdigest()
        if self.population_sha256 != hash_now:
            raise ValueError('Population hash does not match snapshot rows')
        if (not isinstance(self.normalized_sha256,str) or len(self.normalized_sha256) != 64
            or any(ch not in '0123456789abcdef' for ch in self.normalized_sha256)):
            raise ValueError('Invalid normalized artifact SHA256')


def snapshot_from_frozen_archive(directory: str | Path = DATA_DIR) -> ResearchSnapshot:
    """Use the actual existing SHA-pinned 2026-09-23.1 real research archive."""
    data, manifest, meta = load_archive(directory, verify=True)
    return ResearchSnapshot(
        release=meta['release'], observed_at=manifest['acquisition']['downloaded_at_utc'],
        normalized_sha256=meta['normalized_sha256'],
        population_sha256=manifest['population_sha256'],
        origin='pinned_real_archive',records=tuple(data['records']),
        sampling_cells=tuple(sorted(meta['sampling_cells'])),
    )


def synthetic_overlay(reference: ResearchSnapshot, rows: list[dict], *,
                      hypothetical_release: str, hypothetical_observed_at: str) -> ResearchSnapshot:
    """Make an explicitly marked artificial second release for deterministic stress tests."""
    if reference.origin not in {'pinned_real_archive','synthetic_future'}:
        raise ValueError('Synthetic fixture must derive from a frozen, explicit input')
    sorted_rows = sorted(rows,key=lambda x: x['overture_id'])
    # This is a diagnostic hash, not a proof an Overture release was downloaded.
    data = {'dataset':'KEP-DATA-006-SYNTHETIC','release':hypothetical_release,
            'study_only':True,'records':sorted_rows}
    return ResearchSnapshot(
        release=hypothetical_release,observed_at=hypothetical_observed_at,
        normalized_sha256=sha256(canonical(data)).hexdigest(),
        population_sha256=sha256(canonical(sorted_rows)).hexdigest(),
        origin='synthetic_future',records=tuple(sorted_rows),
        sampling_cells=reference.sampling_cells,
    )


def _safe_read(path:Path,limit:int)->bytes:
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= limit:
        raise ValueError('Missing/unsafe/oversized research artifact')
    return path.read_bytes()


def load_operator_research_bundle(directory: str | Path, *, expected_release: str,
                                  expected_normalized_sha256: str,
                                  expected_observed_at: str) -> ResearchSnapshot:
    """Load a future *separately pinned* normalized artifact, not a verified business list.

    A human supplies the expected SHA out-of-band. File hashes verify local
    consistency, NOT the origin's authenticity. A follow-up source-specific
    capture verification must precede any upstream authenticity claim.
    """
    root = Path(directory)
    raw=_safe_read(root/'places_minimal.json',MAX_COMPARISON_BYTES)
    mb=_safe_read(root/'manifest.json',MAX_MANIFEST_BYTES)
    obj=json.loads(raw);manifest=json.loads(mb)
    if canonical(obj)!=raw or canonical(manifest)!=mb:
        raise ValueError('Noncanonical research artifact')
    check_release(expected_release)
    if expected_release=='2026-09-23.1':
        raise ValueError('Use the separately pinned real archive loader for the original snapshot')
    if (set(obj)!={'dataset','release','study_only','records'}
        or obj.get('dataset')!='KEP-DATA-001' or obj.get('study_only') is not True
        or obj.get('release')!=expected_release
        or manifest.get('pinned_release')!=expected_release
        or manifest.get('research_only') is not True
        or manifest.get('consumer_display_approved') is not False
        or manifest.get('schema')!=SCHEMA
        or manifest.get('sample_cell_bounds_not_district_boundary') != {k:list(v) for k,v in PILOT.items()}
        or manifest.get('human_verified_labels')!=0
        or manifest.get('no_automatic_entity_merge') is not True
        or manifest.get('license_evidence_url')!='https://docs.overturemaps.org/attribution/'
        or not isinstance(manifest.get('source_files'),list)
        or sorted(x.get('cell') for x in manifest['source_files'] if isinstance(x,dict))!=sorted(PILOT)):
        raise ValueError('Release, schema, rights or sampling scope mismatch')
    if (sha256(raw).hexdigest()!=expected_normalized_sha256
        or manifest.get('normalized_sha256')!=expected_normalized_sha256):
        raise ValueError('Unpinned or corrupted normalized future snapshot')
    records=obj.get('records')
    if not isinstance(records,list):raise ValueError('Missing normalized records')
    digest=sha256(canonical(records)).hexdigest()
    if manifest.get('population_sha256')!=digest:
        raise ValueError('Population SHA mismatch')
    acq=manifest.get('acquisition',{})
    if (not isinstance(acq,dict) or acq.get('method')!='manual_overturemaps_cli_stac_pinned'
        or not isinstance(acq.get('stac_catalog_sha256_before'),str) or len(acq['stac_catalog_sha256_before'])!=64
        or not isinstance(acq.get('stac_catalog_sha256_after'),str) or len(acq['stac_catalog_sha256_after'])!=64
        or acq.get('downloaded_at_utc')!=expected_observed_at):
        raise ValueError('Cannot claim a versioned research acquisition')
    return ResearchSnapshot(release=expected_release,observed_at=expected_observed_at,
        normalized_sha256=expected_normalized_sha256,population_sha256=digest,
        origin='operator_supplied_research',records=tuple(records),sampling_cells=tuple(sorted(PILOT)))


def _release_key(release:str) -> tuple:
    check_release(release)
    day,patch = release.rsplit('.',1)
    return datetime.fromisoformat(day).date(),int(patch)


def _field_value(record:dict, field:str):
    # The order of source-provenance entries is nonsemantic. Count content changes
    # separately from JSON array-order fluctuations.
    if field=='source_provenance':
        return sorted(canonical(entry) for entry in record[field])
    return record[field]


def _candidate_id_churn(removed:list[dict],added:list[dict],limit:int) -> tuple[list[dict],bool]:
    # Exact normalized name and same basic category, within 45m. Review hints only.
    lookup=defaultdict(list)
    for row in added:
        key=(_name_key(row['name']),row['basic_category'])
        if key[0] and key[1]:lookup[key].append(row)
    hints=[]
    for old in removed:
        key=(_name_key(old['name']),old['basic_category'])
        if not key[0] or not key[1]:continue
        for new in lookup.get(key,[]):
            if old['cell']!=new['cell']:continue
            d=metres_between(old,new)
            if d<=45:
                hints.append({'old_id':old['overture_id'],'new_id':new['overture_id'],
                              'distance_m':round(d,2),'decision':'HUMAN_REVIEW_IDENTITY_ONLY'})
                if len(hints)>limit:
                    return hints[:limit],True
    return sorted(hints,key=lambda r:(r['old_id'],r['new_id'])),False


def compare_snapshots(before:ResearchSnapshot,after:ResearchSnapshot,*,
                      max_detail:int=80,max_churn_hints:int=250,
                      allow_historical_backfill:bool=False)->dict[str,Any]:
    """Report source churn. Release order need not equal historical download order.

    Acquisition-time reversal is only permitted for the exact August->September
    research backfill. The default policy for other comparisons stays strict.
    """
    if not isinstance(before,ResearchSnapshot) or not isinstance(after,ResearchSnapshot):
        raise TypeError('Expected validated research snapshots')
    # Dataclass is frozen, but nested record dicts can still be altered by a caller.
    # Re-check the bound population before emitting any numerical findings.
    for snapshot in (before,after):
        if sha256(canonical(list(snapshot.records))).hexdigest()!=snapshot.population_sha256:
            raise ValueError('Snapshot records changed after integrity verification')
    if type(allow_historical_backfill) is not bool:
        raise ValueError('Historical backfill flag must be a boolean')
    if _release_key(before.release)>=_release_key(after.release):
        raise ValueError('Cannot compare unordered, identical or backwards releases')
    if aware(before.observed_at)>=aware(after.observed_at):
        exact_backfill = (allow_historical_backfill
            and before.release=='2026-08-19.0'
            and after.release=='2026-09-23.1'
            and before.origin=='operator_supplied_research'
            and after.origin=='pinned_real_archive')
        if not exact_backfill:
            raise ValueError('Cannot compare unordered, identical or backwards releases')
    if before.sampling_cells!=after.sampling_cells or before.schema!=after.schema:
        raise ValueError('Incomparable release schema/sampling coverage')
    if (type(max_detail)!=int or max_detail<0 or max_detail>1000 or
        type(max_churn_hints)!=int or not 0<=max_churn_hints<=5000):
        raise ValueError('Unbounded review output request')
    old={r['overture_id']:r for r in before.records}
    new={r['overture_id']:r for r in after.records}
    left=sorted(set(old)-set(new));right=sorted(set(new)-set(old));same=sorted(set(old)&set(new))
    field_counts=Counter();unknown_transitions=Counter();cell_counts=Counter()
    modified=[];confidence_only=0;provenance_only=0; unchanged=0
    for rid in same:
        a,b=old[rid],new[rid]
        changed=[]
        for field in LIMITED_FIELDS:
            if _field_value(a,field)!=_field_value(b,field):
                changed.append(field)
                field_counts[field]+=1
                if a[field] is None and b[field] is not None:
                    unknown_transitions[field+'_became_known']+=1
                elif a[field] is not None and b[field] is None:
                    unknown_transitions[field+'_became_unknown']+=1
        distance=metres_between(a,b)
        if a['lon']!=b['lon'] or a['lat']!=b['lat']:
            changed.append('geometry');field_counts['geometry']+=1
        if a['cell']!=b['cell']:
            changed.append('sample_cell');field_counts['sample_cell']+=1
        confidence=(a['confidence']!=b['confidence'])
        if confidence:field_counts['confidence']+=1
        if not changed and not confidence:
            unchanged+=1
        elif not changed and confidence:
            confidence_only+=1
        else:
            if changed==['source_provenance'] and not confidence:provenance_only+=1
            cell_counts[a['cell']]+=1
            modified.append({'overture_id':rid,'changed_fields':sorted(changed),
                             'confidence_changed':confidence,
                             'coordinate_difference_m':round(distance,2) if 'geometry' in changed else None,
                             'decision':'SOURCE_RECORD_REVISION_ONLY'})
    hints,truncated=_candidate_id_churn([old[k] for k in left],[new[k] for k in right],max_churn_hints)
    for key in left:cell_counts['removed_'+old[key]['cell']]+=1
    for key in right:cell_counts['added_'+new[key]['cell']]+=1
    is_synthetic=before.origin=='synthetic_future' or after.origin=='synthetic_future'
    can_call_real=False  # Internal hashes alone cannot authenticate upstream changes.
    report={
        'study':'KEP-DATA-006', 'comparison':'SOURCE_RELEASE_CHANGE_NOT_GROUND_TRUTH',
        'research_only':True,'consumer_publish':False,
        'old_release':before.release,'new_release':after.release,
        'old_source_origin':before.origin,'new_source_origin':after.origin,
        'synthetic_second_release':is_synthetic,
        'real_world_business_changes_estimated':False,
        'upstream_change_authenticated_by_comparison':can_call_real,
        'old_population_n':len(before.records),'new_population_n':len(after.records),
        'old_population_sha256':before.population_sha256,
        'new_population_sha256':after.population_sha256,
        'source_record_churn':{
            'retained_ids':len(same),'newly_listed_ids':len(right),'no_longer_listed_ids':len(left),
            'field_or_geometry_revised_ids':len(modified),'unchanged_ids':unchanged,
            'confidence_only_revised_ids':confidence_only,
            'provenance_only_revised_ids':provenance_only,
            'field_change_counts':dict(sorted(field_counts.items())),
            'missingness_transitions':dict(sorted(unknown_transitions.items())),
            'by_cell':dict(sorted(cell_counts.items())),
            'possible_id_reassignment_hints':hints,
            'id_reassignment_review_truncated':truncated,
            'modified_examples':modified[:max_detail],
            'detail_truncated':len(modified)>max_detail,
        },
        'conclusions_forbidden':['closed_business_from_missing_id',
             'new_business_from_added_id', 'physical_move_from_changed_geometry',
             'currently_open_from_operating_status',
             'ground_truth_probability_from_confidence',
             'auto_merge_possible_id_reassignment'],
        'human_verified_closures':0,'human_verified_openings':0,
    }
    return report


def controlled_future_example(directory: str | Path = DATA_DIR)->dict:
    """Run on 4,803 *real* 2026-09 records with explicitly INVENTED future edits.

    This is an algorithmic stress test, not evidence from October 2026.
    """
    import copy
    from uuid import UUID
    before=snapshot_from_frozen_archive(directory)
    rows=copy.deepcopy(list(before.records))
    by_id={r['overture_id']:r for r in rows}
    changed=sorted(by_id)
    remove=changed[0];rekey=changed[5]
    by_id[changed[1]]['name']='SYNTHETIC_CHANGED_NAME_FOR_TEST'
    by_id[changed[2]]['basic_category']='synthetic_review_category'
    by_id[changed[3]]['lon']+=.00007
    by_id[changed[4]]['address']=None
    by_id[changed[6]]['operating_status']='temporarily_closed'
    by_id[changed[7]]['confidence']=.01
    moved=by_id.pop(rekey)
    replacement=copy.deepcopy(moved)
    replacement['overture_id']=str(UUID(int=1))
    if replacement['overture_id'] in by_id:
        raise ValueError('Unexpected fixture collision')
    by_id[replacement['overture_id']]=replacement
    by_id.pop(remove)
    new=copy.deepcopy(by_id[changed[8]])
    new['overture_id']=str(UUID(int=2))
    new['name']='SYNTHETIC_ADDED_LISTING_NOT_A_BUSINESS'
    if new['overture_id'] in by_id:
        raise ValueError('Unexpected synthetic second fixture collision')
    by_id[new['overture_id']]=new
    after=synthetic_overlay(before,list(by_id.values()),
        hypothetical_release='2026-10-21.0',hypothetical_observed_at='2026-10-22T10:00:00+03:00')
    return compare_snapshots(before,after)
