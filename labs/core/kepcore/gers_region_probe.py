"""DATA-015: scope-safe, bounded regional GERS event research. Never business truth.

No network or Arrow dependency. Metadata is loaded from DATA-014's pinned ZIP;
read-only optional source acquisition belongs to scripts/probe_gers_region.py.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from hashlib import sha256
from math import isfinite
from uuid import UUID

from .gers_access_cost import (PINNED_ZIP_SHA256, KINDS, RELEASES, _interval,
                               validate_objects)
from .overture_places import PILOT,canonical

TARGET = '2026-09-23.0'
BUDGET_BYTES = 32 * 1024 * 1024
MAX_RANGE = 12 * 1024 * 1024
MAX_REQUESTS = 256
# Canonical digest of the *entire* SHA-verified DATA-014 original footer manifest.
PINNED_MANIFEST_SHA256 = '4c19d5baf0bac7f06e052c70158895a9b83ab65a3b5f20503c0ad1f909361ae5'


def publisher_patch_scope():
    """Publisher's *stated patch fix*, not an attested changelog build lineage.

    Overture's Sept 23 release notes identify base/building_parts UUIDs only.
    They do not attest a comparison baseline for the two changelog paths.
    """
    return {
        'publisher_url':'https://docs.overturemaps.org/blog/2026/09/23/release-notes/',
        'patch_release':'2026-09-23.1',
        'stated_patch_targets':['base','building_parts'],
        'places_explicitly_named_as_patch_target':False,
        'patch_scope_guarantees_unchanged_places':False,
        'verified_changelog_comparison_baseline':None,
        'may_sum_september_changelogs_as_independent_hops':False,
        'one_publisher_cannot_vote_twice':True,
    }


def _bbox_intersects(bb, box):
    return bb['xmin']<=box[2] and bb['xmax']>=box[0] and bb['ymin']<=box[3] and bb['ymax']>=box[1]


def regional_plan(manifest):
    """Select exactly the known region's row groups in one changelog path.

    ID lookup outside the sampled boxes is NOT performed. This is never an
    all-ID agreement, even if all geographically matched rows were read.
    """
    if (not isinstance(manifest,dict) or manifest.get('format')!='KEP-GERS-FOOTERS-v1'
            or manifest.get('status')!='COMPLETE_METADATA'
            or manifest.get('origin')!='captured_public_footer_metadata'
            or sha256(canonical(manifest)).hexdigest()!=PINNED_MANIFEST_SHA256):
        raise ValueError('Expected exact authenticated local DATA-014 metadata capture')
    objects=manifest['objects'];validate_objects(objects)
    if len(objects)!=128 or len(RELEASES)!=2:
        raise ValueError('Unexpected GERS source partition inventory')
    counts=Counter((o['release'],o['change_type']) for o in objects)
    if any(counts[(release,kind)]!=16 for release in RELEASES for kind in KINDS):
        raise ValueError('Partition inventory incomplete')
    selected=[]
    excluded=0
    for obj in sorted(objects,key=lambda o:o['key']):
        for i,group in enumerate(obj['row_groups']):
            cs={c['path']:c for c in group['columns']}
            bb={k:_interval(cs['bbox.'+k]) for k in ('xmin','xmax','ymin','ymax')}
            spatial_unknown=any(v is None for v in bb.values())
            possible=(spatial_unknown or any(
                bb['xmin'][0]<=box[2] and bb['xmax'][1]>=box[0]
                and bb['ymin'][0]<=box[3] and bb['ymax'][1]>=box[1]
                for box in PILOT.values()))
            if possible and obj['release']==TARGET:
                selected.append({
                    'key':obj['key'],'etag':obj['etag'],'object_bytes':obj['size'],
                    'footer_sha256':obj['footer_sha256'],'row_group':i,
                    'change_type':obj['change_type'],'rows':group['rows'],
                    'estimated_compressed_column_bytes':sum(c['compressed_bytes'] for c in group['columns']),
                    'metadata_statistics_unknown':spatial_unknown,
                })
            if not possible:excluded+=1
    selected.sort(key=lambda x:x['change_type'])
    if len(selected)!=4 or set(x['change_type'] for x in selected)!=set(KINDS):
        raise ValueError('Unexpected pilot group footprint; require manual re-design')
    total= sum(x['estimated_compressed_column_bytes'] for x in selected)
    if total>BUDGET_BYTES or sum(x['rows'] for x in selected)>1_000_000:
        raise ValueError('Prospective research read exceeds reviewed limits')
    return {
        'study':'KEP-DATA-015','target_release':TARGET,'metadata_release_paths':list(RELEASES),
        'source_zip_sha256':PINNED_ZIP_SHA256,'source_manifest_sha256':PINNED_MANIFEST_SHA256,
        'selected':selected,'selected_one_release_groups':len(selected),
        'total_row_groups':sum(len(x['row_groups']) for x in objects),
        'excluded_row_groups_across_both_releases':excluded,
        'estimated_candidate_column_bytes':total,
        'max_application_body_bytes':BUDGET_BYTES,
        'scope':'bbox_intersecting_events_only_not_global_id_union',
        'complete_id_union_scan':False,'data_pages_read':0,
        'official_membership_agreement_fraction':None,
        'patch_provenance':publisher_patch_scope(),
        'consumer_publish':False,'real_business_truth':None,
    }


class RangeBudget:
    """Conservatively charge every requested body extent, including failures."""
    def __init__(self,limit=BUDGET_BYTES,requests=MAX_REQUESTS):
        if (type(limit) is not int or not 0<limit<=BUDGET_BYTES or
                type(requests) is not int or not 0<requests<=MAX_REQUESTS):
            raise ValueError('Invalid immutable read budget')
        self.limit=limit;self.request_limit=requests;self.bytes_reserved=0;self.requests=0

    def reserve(self,size):
        if (type(size) is not int or not 0<size<=MAX_RANGE or
                self.bytes_reserved+size>self.limit or self.requests>=self.request_limit):
            raise ValueError('GERS event read budget exhausted or invalid')
        self.bytes_reserved+=size;self.requests+=1


def validate_response(status,headers,start,end,obj,body):
    h={k.lower():v for k,v in headers.items()}
    if (type(start) is not int or type(end) is not int or
            not 0<=start<=end<obj['size'] or
            end-start+1>MAX_RANGE or status!=206 or
            h.get('content-range')!=f'bytes {start}-{end}/{obj["size"]}' or
            h.get('content-length')!=str(end-start+1) or
            h.get('etag')!=obj['etag'] or
            h.get('content-encoding','identity')!='identity' or
            len(body)!=end-start+1):
        raise ValueError('Pinned S3 range status/ETag/extent/body mismatch')


def validate_event(row,kind):
    """Validate *publisher row format* without inferring business reality."""
    if kind not in KINDS or not isinstance(row,dict) or set(row)!= {'id','bbox','columns_changed'}:
        raise ValueError('Unknown official GERS row projection')
    rid=row['id']
    if not isinstance(rid,str):raise ValueError('Malformed ID')
    try:
        if str(UUID(rid))!=rid:raise ValueError('Noncanonical ID')
    except (TypeError,AttributeError):raise ValueError('Malformed ID') from None
    bb=row['bbox']
    if (not isinstance(bb,dict) or set(bb)!={'xmin','xmax','ymin','ymax'} or
            any(type(x) not in {float,int} or not isfinite(x) for x in bb.values()) or
            not -180<=bb['xmin']<=bb['xmax']<=180 or
            not -90<=bb['ymin']<=bb['ymax']<=90):
        raise ValueError('Invalid GERS geometry bounds')
    cols=row['columns_changed']
    if kind=='data_changed':
        if not isinstance(cols,list) or not cols or len(cols)>100 or any(
                not isinstance(s,str) or not s for s in cols):
            raise ValueError('Changed fields missing or invalid')
    elif cols not in (None,[]):raise ValueError('Unexpected changed columns for this GERS event')
    return rid


def summarize_events(events,union_ids,*,origin):
    """Aggregate a bounded capture. No raw IDs or field-review material exported.

    Even after a successful bbox event acquisition, patch predecessor and
    out-of-bounds ID movement remain unverified, so agreement is null.
    """
    if origin not in {'synthetic_test_fixture','captured_public_GERS_rows'}:
        raise ValueError('Source provenance cannot be invented')
    if not isinstance(union_ids,set) or not all(isinstance(s,str) for s in union_ids):
        raise ValueError('Expected real union-ID set')
    data={};dupes=0;variants=defaultdict(set);scanned=0
    for kind,row in events:
        scanned+=1
        if scanned>1_000_000:raise ValueError('Unbounded regional observation set')
        rid=validate_event(row,kind)
        if not any(_bbox_intersects(row['bbox'],box) for box in PILOT.values()):continue
        signature=sha256(canonical(row)).hexdigest()
        key=(kind,rid)
        if key in data and data[key]==signature:dupes+=1
        elif key in data:
            variants[rid].add(data[key]);variants[rid].add(signature)
        else:data[key]=signature
    kinds=Counter(k for k,_ in data)
    per_id=defaultdict(set)
    for kind,rid in data:per_id[rid].add(kind)
    conflicts={rid for rid,k in per_id.items() if len(k)>1}|set(variants)
    return {
        'study':'KEP-DATA-015','origin':origin,'region':'besiktas_center+karakoy_center',
        'source_root':'overturemaps','scanned_rows':scanned,
        'regional_rows':len(data),'unique_regional_ids':len(per_id),
        'matched_union_ids':len(set(per_id)&union_ids),
        'matched_union_by_type':{kind:sum(rid in union_ids for t,rid in data if t==kind) for kind in KINDS},
        'regional_event_type_counts':{kind:kinds[kind] for kind in KINDS},
        'duplicate_exact_observations':dupes,'conflicting_regional_ids':len(conflicts),
        'regional_observation_sha256':sha256(canonical(sorted((k,r,s) for (k,r),s in data.items()))).hexdigest(),
        'full_id_union_coverage':False,
        'verified_patch_predecessor':None,
        'safe_to_reconcile_membership':False,
        'official_membership_agreement_fraction':None,
        'physical_business_openings':None,'physical_business_closures':None,
        'independent_human_labels':0,'consumer_publish':False,
    }
