"""DATA-013: reconcile source observations, never infer physical business events.

Offline and standard-library-only. An official capture is caller-pinned evidence
of a publisher's records, not independent evidence of a shop's existence. The
August/September raw classification schemas are NOT treated as equivalent.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from datetime import date
from hashlib import sha256
from pathlib import Path
import json
import gzip
import io
import re
from urllib.parse import urlsplit
from uuid import UUID

from .calibration import aware
from .overture_archive_artifact import (
    FROZEN_SHA, compare_source_records, load_original_research_zip,
)
from .overture_change_triage import inspect_releases, _changed
from .overture_delta import ResearchSnapshot, compare_snapshots, snapshot_from_frozen_archive
from .overture_places import PILOT, canonical, metres_between, _name_key

OLD = '2026-08-19.0'
NEW = '2026-09-23.1'
RIGHTS = 'https://docs.overturemaps.org/attribution/'
CAPTURE_PREFIX = ('https://overturemaps-us-west-2.s3.us-west-2.amazonaws.com/'
                  'changelog/' + NEW + '/theme=places/type=place/')
MAX_CAPTURE_BYTES = 16_000_000
MAX_EVENTS = 100_000
SCHEMA_FIELDS = frozenset({'basic_category', 'taxonomy_primary'})
TECHNICAL_FIELDS = frozenset({'source_provenance', 'cell'})
TOP_LEVEL = {'name':'names', 'address':'addresses', 'locality':'addresses',
             'country':'addresses', 'operating_status':'operating_status',
             'geometry':'geometry'}
SCHEMA_REPORT = {
    'raw_before_schema':'Places v1.18', 'raw_after_schema':'Places v2.0',
    'not_semantically_comparable':['basic_category','categories','taxonomy'],
    'excluded_from_official_comparison':['confidence','sources'],
    'partially_observed_top_level_columns':['addresses','names'],
    'normalization_note':'Primary name and first address only; raw categories not retained.',
    'absence_of_local_change_proves_full_feature_unchanged':False,
}


def digest(value: object) -> str:
    return sha256(canonical(value)).hexdigest()


def _sha(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


def load_capture(path: str | Path, expected_sha256: str) -> dict:
    """Require exact immutable bytes, bounded size and no symlink. No fetching."""
    p = Path(path)
    if (not _sha(expected_sha256) or p.is_symlink() or not p.is_file()
            or not 0 < p.stat().st_size <= MAX_CAPTURE_BYTES):
        raise ValueError('Missing, unsafe or unpinned changelog capture')
    raw = p.read_bytes()
    if sha256(raw).hexdigest() != expected_sha256:
        raise ValueError('Changelog capture SHA-256 mismatch')
    obj = json.loads(raw)
    if canonical(obj) != raw:
        raise ValueError('Capture must use canonical JSON, without duplicate keys')
    return obj


def load_pinned_pair() -> tuple[ResearchSnapshot, ResearchSnapshot]:
    """Read the existing Git-pinned ZIP. Never re-download the August release."""
    root = Path(__file__).resolve().parents[1]
    rows, manifest, _ = load_original_research_zip(
        root / 'data/real/overture_istanbul_2026-08-19.0/original_actions_artifact.zip')
    before = ResearchSnapshot(release=OLD,
        observed_at=manifest['acquisition']['observed_at'],
        normalized_sha256=FROZEN_SHA['places_minimal.json'],
        population_sha256=manifest['population_sha256'],
        origin='operator_supplied_research', records=tuple(rows),
        sampling_cells=tuple(sorted(PILOT)))
    return before, snapshot_from_frozen_archive()


def _validate_capture(c: dict, expected: str | None, union: set[str], synthetic: bool) -> None:
    keys = {'format','origin','before_release','after_release','source_root',
            'source_url','retrieved_at','rights_evidence_url','transition_evidence','query','rows'}
    if not isinstance(c, dict) or set(c) != keys:
        raise ValueError('Unrecognized capture envelope')
    if not _sha(expected) or digest(c) != expected:
        raise ValueError('Missing or mismatched changelog checksum')
    if len(canonical(c)) > MAX_CAPTURE_BYTES:
        raise ValueError('Unbounded changelog capture')
    if (c['format'] != 'KEP-GERS-CAPTURE-v1' or c['source_root'] != 'overturemaps'
            or c['before_release'] != OLD or c['after_release'] != NEW
            or c['rights_evidence_url'] != RIGHTS):
        raise ValueError('Release predecessor, source root or rights mismatch')
    if aware(c['retrieved_at']).date() < date.fromisoformat(NEW[:10]):
        raise ValueError('Capture predates its release')
    te = c['transition_evidence']
    if (not isinstance(te, dict) or set(te) != {'status','url','sha256'}
            or not _sha(te['sha256'])):
        raise ValueError('Missing release-transition evidence')
    if synthetic:
        if (c['origin'] != 'synthetic_fixture' or c['source_url'] != 'synthetic://gers'
                or te['status'] not in {'synthetic_fixture','unverified'}
                or te['url'] != 'synthetic://transition'):
            raise ValueError('Synthetic observations cannot impersonate an official capture')
    else:
        if c['origin'] != 'official_capture' or c['source_url'] != CAPTURE_PREFIX:
            raise ValueError('Real snapshots require an explicitly pinned official-source capture')
        url = urlsplit(te['url']) if isinstance(te['url'],str) else None
        if (te['status'] not in {'operator_reviewed','unverified'} or url is None
                or url.scheme != 'https' or url.hostname not in {'docs.overturemaps.org','stac.overturemaps.org'}
                or url.username or url.password or url.port not in {None,443}):
            raise ValueError('Unapproved predecessor evidence URL')
    query = c['query']
    if (not isinstance(query,dict) or set(query) != {'mode','ids_sha256','all_partitions_scanned'}
            or query['mode'] not in {'id_union','bbox_partial'}
            or type(query['all_partitions_scanned']) is not bool
            or query['ids_sha256'] != digest(sorted(union))):
        raise ValueError('Changelog query is not bound to the exact union of source IDs')
    rows = c['rows']
    if not isinstance(rows,list) or len(rows) > MAX_EVENTS:
        raise ValueError('Missing or unbounded changelog rows')
    for ev in rows:
        if not isinstance(ev,dict) or set(ev) != {'id','change_type','columns_changed'}:
            raise ValueError('Unrecognized or private event fields')
        rid,kind,cols = ev['id'],ev['change_type'],ev['columns_changed']
        try:
            valid_id = isinstance(rid,str) and str(UUID(rid)) == rid
        except (ValueError,AttributeError):
            valid_id = False
        if not valid_id or (query['mode'] == 'id_union' and rid not in union):
            raise ValueError('Invalid or out-of-query GERS ID')
        if not isinstance(kind,str) or kind not in {'added','removed','data_changed','unchanged'}:
            raise ValueError('Unknown GERS event; physical-business event types are forbidden')
        if kind == 'data_changed':
            if (not isinstance(cols,list) or not 0 < len(cols) <= 100
                    or any(not isinstance(v,str) or not re.fullmatch('[a-z][a-z0-9_]{0,63}',v) for v in cols)
                    or len(set(cols)) != len(cols) or set(cols) & {'confidence','sources'}):
                raise ValueError('Invalid or officially excluded columns_changed')
        elif cols is not None and cols != []:
            raise ValueError('Only data_changed may list changed columns')


def _identity_candidates(old: dict, new: dict, limit: int = 250) -> dict:
    """Exact-name nearby hypotheses; do not require cross-schema category equality."""
    lookup = defaultdict(list)
    for rid in sorted(new.keys()-old.keys()):
        name = _name_key(new[rid]['name']) if new[rid]['name'] else ''
        if name:
            lookup[name].append(new[rid])
    hints = []
    truncated = False
    for rid in sorted(old.keys()-new.keys()):
        row = old[rid]
        name = _name_key(row['name']) if row['name'] else ''
        for target in lookup.get(name,[]):
            distance = metres_between(row,target)
            if row['cell'] == target['cell'] and distance <= 45:
                if len(hints) == limit:
                    truncated = True
                    break
                hints.append({'old_id':rid,'new_id':target['overture_id'],
                    'distance_m':round(distance,2), 'decision':'HUMAN_IDENTITY_REVIEW_ONLY'})
        if truncated:
            break
    return {'candidates':hints, 'truncated':truncated, 'automatic_merge':False,
            'category_used_as_identity_evidence':False, 'candidate_recall_measured':False,
            'publisher_supersession_link_available':False}


def reconcile(before: ResearchSnapshot, after: ResearchSnapshot, *,
              changelog: dict | None = None, expected_changelog_sha256: str | None = None,
              allow_historical_backfill: bool = False) -> dict:
    """Return source accounting and explicit reconciliation/abstention outcomes.

    No events are inferred from documentation. No agreement rate is published for
    missing, partial, conflicting or predecessor-unverified observations. Even a
    complete official capture is another view of the SAME publisher, not truth.
    """
    if not isinstance(before,ResearchSnapshot) or not isinstance(after,ResearchSnapshot):
        raise TypeError('Validated ResearchSnapshot inputs required')
    if (before.release,after.release) != (OLD,NEW):
        raise ValueError('DATA-013 is pinned to the reviewed August/September release pair')
    synthetic = before.origin == 'synthetic_future'
    if synthetic != (after.origin == 'synthetic_future'):
        raise ValueError('Do not mix synthetic and real source records in this experiment')
    base = compare_snapshots(before,after,allow_historical_backfill=allow_historical_backfill)
    old = {r['overture_id']:r for r in before.records}
    new = {r['overture_id']:r for r in after.records}
    common,union = old.keys() & new.keys(), old.keys() | new.keys()
    delta = compare_source_records(list(before.records),list(after.records))
    if any(base['source_record_churn'].get(k) != v for k,v in delta.items()):
        raise ValueError('Existing source comparators disagree')
    drift = inspect_releases(list(before.records),list(after.records))['summary']
    changes = {rid:set(_changed(old[rid],new[rid])) for rid in common}
    queue = []
    routing = Counter({'membership_review_ids':len(union)-len(common),
                       'property_review_ids':0,'schema_only_ids':0,'metadata_only_ids':0,
                       'unchanged_local_ids':0})
    for rid in sorted(union):
        if rid not in common:
            lane = 'SOURCE_MEMBERSHIP_REVIEW_NOT_OPENING_OR_CLOSURE'
        else:
            fields = changes[rid]
            reliable = fields - SCHEMA_FIELDS - TECHNICAL_FIELDS
            if reliable:
                lane = 'SOURCE_PROPERTY_REVIEW_NOT_PHYSICAL_CHANGE'
                routing['property_review_ids'] += 1
            elif fields & SCHEMA_FIELDS:
                lane = 'TECHNICAL_SCHEMA_REVIEW'
                routing['schema_only_ids'] += 1
            elif fields or old[rid]['confidence'] != new[rid]['confidence']:
                routing['metadata_only_ids'] += 1
                continue
            else:
                routing['unchanged_local_ids'] += 1
                continue
        queue.append({'overture_id':rid,'lane':lane,'targeted_not_random':True})
    if sum(routing.values()) != len(union):
        raise AssertionError('Exclusive union accounting failed')
    official = {'status':'NOT_AVAILABLE', 'observed_unique_ids':0,
        'duplicate_rows_collapsed':0,'missing_union_ids':len(union),
        'outcome_counts':{},'unobserved_columns':[],
        'membership_comparable_ids':0,'membership_agreement_fraction':None,
        'source_capture_sha256':None,'publisher_root':'overturemaps',
        'independent_publisher_authentication':False}
    conflicts = []
    outcomes = []
    compatibility = None if synthetic else assess_changelog_compatibility()
    if changelog is None:
        if expected_changelog_sha256 is not None:
            raise ValueError('Checksum supplied without capture')
    else:
        _validate_capture(changelog,expected_changelog_sha256,set(union),synthetic)
        if not synthetic and not compatibility['direct_pair_comparison_allowed']:
            raise ValueError('Nonconsecutive real releases require verified intermediate changelogs; no override')
        grouped = defaultdict(dict)
        duplicates = 0
        for ev in changelog['rows']:
            normal = {'id':ev['id'],'change_type':ev['change_type'],
                      'columns_changed':sorted(ev['columns_changed']) if ev['columns_changed'] else None}
            key = digest(normal)
            duplicates += int(key in grouped[ev['id']])
            grouped[ev['id']][key] = normal
        observed = set(grouped) & union
        missing = len(union-observed)
        official.update(observed_unique_ids=len(observed),duplicate_rows_collapsed=duplicates,
            missing_union_ids=missing,source_capture_sha256=expected_changelog_sha256)
        pair_verified = changelog['transition_evidence']['status'] != 'unverified'
        full_scope = (changelog['query']['mode'] == 'id_union'
                      and changelog['query']['all_partitions_scanned'])
        counts = Counter()
        unknown_columns = set()
        consistent_membership = 0
        for rid in sorted(observed):
            variants = sorted(grouped[rid].values(),key=canonical)
            local_kind = 'retained' if rid in common else ('added' if rid in new else 'removed')
            if len(variants) != 1:
                outcome = 'CONFLICTING_OFFICIAL_EVENTS'
            elif not pair_verified:
                outcome = 'PAIR_NOT_VERIFIED'
            else:
                ev = variants[0]
                kind,cols = ev['change_type'],set(ev['columns_changed'] or [])
                unknown_columns.update(cols-set(TOP_LEVEL.values())-{'basic_category','taxonomy','categories'})
                if local_kind != 'retained':
                    if kind == local_kind:
                        outcome = 'CONSISTENT_SOURCE_MEMBERSHIP'
                        consistent_membership += 1
                    elif kind in {'unchanged','data_changed'}:
                        outcome = ('REGIONAL_ENTRY_OR_CAPTURE_GAP' if local_kind == 'added'
                                   else 'REGIONAL_EXIT_OR_CAPTURE_GAP')
                    else:
                        outcome = 'CONTRADICTION'
                elif kind in {'added','removed'}:
                    outcome = 'CONTRADICTION'
                else:
                    local_columns = {TOP_LEVEL[f] for f in changes[rid] if f in TOP_LEVEL}
                    if kind == 'unchanged':
                        outcome = 'CONTRADICTION' if local_columns else 'COMPATIBLE_ON_OBSERVED_FIELDS'
                    elif local_columns - cols:
                        outcome = 'CONTRADICTION'
                    elif local_columns:
                        outcome = 'CONSISTENT_ON_OBSERVED_FIELDS'
                    else:
                        outcome = 'NOT_OBSERVABLE_OR_SCHEMA_AMBIGUOUS'
            counts[outcome] += 1
            outcomes.append({'overture_id':rid,'local_membership':local_kind,'outcome':outcome})
            if outcome in {'CONTRADICTION','CONFLICTING_OFFICIAL_EVENTS'}:
                conflicts.append({'overture_id':rid,'local_membership':local_kind,
                    'local_changed_fields':sorted(changes.get(rid,set())),
                    'official_events':deepcopy(variants),'resolution':'UNRESOLVED_NO_SOURCE_WINS'})
        status = 'SYNTHETIC_ONLY' if synthetic else 'RECONCILED_SOURCE_CAPTURE'
        if not pair_verified:
            status = 'PAIR_NOT_VERIFIED'
        elif conflicts:
            status = 'CONFLICTED'
        elif not full_scope:
            status = 'PARTIAL_SCOPE'
        elif missing:
            status = 'INCOMPLETE'
        official.update(status=status,outcome_counts=dict(sorted(counts.items())),
                        unobserved_columns=sorted(unknown_columns))
        eligible = pair_verified and full_scope and not missing and not conflicts
        denominator = len(old.keys() ^ new.keys())
        if eligible:
            official['membership_comparable_ids'] = denominator
            official['membership_agreement_fraction'] = (consistent_membership/denominator
                                                         if denominator else None)
    return {'study':'KEP-DATA-013','research_only':True,'consumer_publish':False,
        'source_origin':'SYNTHETIC_FIXTURE' if synthetic else 'PINNED_REAL_SOURCE_ARCHIVES',
        'before_release':OLD,'after_release':NEW,
        'before_population_sha256':before.population_sha256,
        'after_population_sha256':after.population_sha256,
        'before_normalized_sha256':before.normalized_sha256,
        'after_normalized_sha256':after.normalized_sha256,
        'source_record_delta':delta,'drift_summary':drift,
        'schema':deepcopy(SCHEMA_REPORT),'routing':dict(routing),
        'changelog_compatibility':compatibility,
        'sampling_coverage':{'bounds_are_cells_not_districts':True,
            'same_frozen_rectangles':True,'global_membership_inferred_from_local_absence':False,
            'by_cell':{cell:{'old':sum(r['cell']==cell for r in old.values()),
                           'new':sum(r['cell']==cell for r in new.values()),
                           'added':sum(new[rid]['cell']==cell for rid in new.keys()-old.keys()),
                           'removed':sum(old[rid]['cell']==cell for rid in old.keys()-new.keys())}
                       for cell in sorted(PILOT)}},
        'identity_review':_identity_candidates(old,new),
        'legacy_identity_hint_count':len(base['source_record_churn']['possible_id_reassignment_hints']),
        'official':official,'official_outcomes':outcomes,'conflicts':conflicts,
        'review_queue':queue,'review_queue_is_unbiased_audit':False,
        'unsupported_naive_business_assertions':len(old.keys() ^ new.keys()),
        'naive_definition':'EXPANDED_ID_TO_OPENING_OR_CLOSURE_HYPOTHESIS',
        'unsupported_removal_as_closure_assertions':len(old.keys()-new.keys()),
        'independent_business_evidence_count':0,'physical_closures':None,
        'physical_openings':None,'business_event_accuracy':None,
        'confidence_is_truth_probability':False}


def public_summary(report: dict) -> dict:
    """Do not publish target identities, POI fields, or any reviewer materials."""
    allowed = {'study','research_only','consumer_publish','source_origin','before_release',
        'after_release','before_population_sha256','after_population_sha256',
        'before_normalized_sha256','after_normalized_sha256','source_record_delta',
        'drift_summary','schema','routing','changelog_compatibility','sampling_coverage',
        'legacy_identity_hint_count','official','review_queue_is_unbiased_audit',
        'unsupported_naive_business_assertions','naive_definition',
        'unsupported_removal_as_closure_assertions','independent_business_evidence_count',
        'physical_closures','physical_openings','business_event_accuracy','confidence_is_truth_probability'}
    out = deepcopy({k:v for k,v in report.items() if k in allowed})
    identity = report['identity_review']
    out['identity_review'] = {k:v for k,v in identity.items() if k != 'candidates'}
    out['identity_review']['candidate_pairs'] = len(identity['candidates'])
    out['identity_review']['candidate_sha256'] = digest(identity['candidates'])
    out['conflict_count'] = len(report['conflicts'])
    out['review_queue_count'] = len(report['review_queue'])
    out['review_queue_sha256'] = digest(report['review_queue'])
    return out


ACCESS_DIRECTORY = Path(__file__).resolve().parents[1]/'data/real/gers_access_2026-10-11'
ACCESS_GZIP_SHA256 = '29b5665475f7194f2f876bc5766f1209233513a1a409a1e80ec83afebb44c0cc'
ACCESS_RAW_SHA256 = 'a8408c46954de59e33f4ec8e92dc99078d67c8beff66417fe3dc399249089cc6'
CATALOG_SHA256 = {'2026-09-23.0': 'a9798b7f08d1679eee34b8b428c8f127acc9aa13c248bc75a269a1740ab8d46e', '2026-09-23.1': '2cb87fbd6ab8fdf8272d8a3c5cbaf6b1f3b7aedebffe9ba122670138308d6946'}


def _pinned_bytes(path: Path, expected: str, limit: int) -> bytes:
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= limit:
        raise ValueError('Missing or unsafe pinned GERS access evidence')
    raw=path.read_bytes()
    if sha256(raw).hexdigest()!=expected:
        raise ValueError('GERS access evidence SHA-256 mismatch')
    return raw


def assess_changelog_compatibility(directory: str | Path = ACCESS_DIRECTORY) -> dict:
    """Replay actual metadata/capture evidence; do not derive unobserved events.

    The actual target catalog links to September .0, which links to August. The
    failed spatial query did read public Parquet bytes but yielded zero complete
    event batches. A successful Actions workbench does NOT mean data success.
    """
    directory=Path(directory)
    packed=_pinned_bytes(directory/'capture_attempt.json.gz',ACCESS_GZIP_SHA256,100_000)
    with gzip.GzipFile(fileobj=io.BytesIO(packed)) as stream:
        raw=stream.read(200_001)
    if len(raw)>200_000 or sha256(raw).hexdigest()!=ACCESS_RAW_SHA256:
        raise ValueError('GERS capture evidence expanded bytes mismatch')
    capture=json.loads(raw)
    chain=[OLD]
    for edge in capture['transitions']:
        release=edge['after_release']
        if release not in CATALOG_SHA256:
            raise ValueError('Unreviewed transition catalog')
        cat_raw=_pinned_bytes(directory/(release+'.catalog.json'),CATALOG_SHA256[release],16_000)
        catalog=json.loads(cat_raw)
        prev=[x for x in catalog.get('links',[]) if x.get('rel')=='prev']
        if (catalog!=edge['catalog'] or edge['catalog_sha256']!=sha256(cat_raw).hexdigest()
                or catalog.get('id')!=release or len(prev)!=1
                or prev[0].get('href')!='https://stac.overturemaps.org/'+chain[-1]+'/catalog.json'
                or edge['before_release']!=chain[-1]):
            raise ValueError('Catalog predecessor chain inconsistent')
        chain.append(release)
    if chain[-1]!=NEW:
        raise ValueError('Incomplete release chain')
    rows=sum(len(e['rows']) for e in capture['transitions'])
    return {'status':'REQUIRES_INTERMEDIATE_RELEASE' if len(chain)>2 else 'CONSECUTIVE_PAIR',
        'release_chain':chain,'direct_pair_comparison_allowed':len(chain)==2,
        'catalog_raw_sha256':dict(CATALOG_SHA256),
        'complete_event_capture_available':capture['status']=='CAPTURED_SPATIALLY_BOUNDED_NOT_GLOBAL'
            and all(e['all_partitions_scanned'] for e in capture['transitions']),
        'global_capture_available':False,'same_publisher_not_independent_evidence':True,
        'capture_attempt':{'status':capture['status'],'official_event_rows':rows,
            'bytes_transferred':capture['bytes_transferred'],'budget_bytes':capture['budget_bytes'],
            'http_requests':capture['http_requests'],'failure_type':capture.get('failure_type'),
            'failure_observation':'HTTP 503 from bounded proxy near body budget; exact rejection detail not retained',
            'query_scope':capture['query_scope'],'retrieved_at':capture['retrieved_at'],
            'workflow_run_id':38142687481,'artifact_id':11703950496,
            'artifact_zip_sha256':'0151e6d502c7a5d9c566fcfa498b72e55463ec44c31310a9197be2739124fb5a',
            'original_receipt_sha256':ACCESS_RAW_SHA256,
            'object_counts_by_release':{release:sum(x['release']==release for x in capture['objects'])
                for release in CATALOG_SHA256}}}
