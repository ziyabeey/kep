"""DATA-016: compare two publisher changelog paths without inventing a baseline.

Offline and standard-library-only. Equal footer/ETag does not imply full object
identity, and equal scoped event projections are not independent witnesses.
"""
from __future__ import annotations
import re
from .gers_access_cost import PINNED_ZIP_SHA256
from .gers_region_probe import regional_plan, PINNED_MANIFEST_SHA256

PATCH_RELEASE='2026-09-23.1'
ORIGINAL_RELEASE='2026-09-23.0'
COMPARE_FIELDS=frozenset({
    'regional_observation_sha256','regional_event_type_counts','regional_rows',
    'unique_regional_ids','matched_union_ids','conflicting_regional_ids',
    'duplicate_exact_observations','scanned_rows',
})
COUNT_TYPES=frozenset({'added','removed','data_changed','unchanged'})


def select_patch_counterparts(manifest:dict)->dict:
    """Require genuine pinned footer metadata and strict .0/.1 counterpart groups."""
    plan=regional_plan(manifest)  # SHA-checks original immutable manifest
    objects={o['key']:o for o in manifest['objects']}
    selected=[]
    for original in plan['selected']:
        if original['change_type'] not in {'added','removed'}:
            continue
        if not original['key'].startswith('changelog/'+ORIGINAL_RELEASE+'/'):
            raise ValueError('Unreviewed original release key')
        counterpart_key=original['key'].replace(
            'changelog/'+ORIGINAL_RELEASE+'/','changelog/'+PATCH_RELEASE+'/',1)
        partner=objects.get(counterpart_key)
        base=objects[original['key']]
        if not partner or any(base[k]!=partner[k] for k in
            ('etag','size','footer_length','footer_sha256','rows','row_groups')):
            raise ValueError('Patch counterpart does not match pinned metadata')
        i=original['row_group']
        if i<0 or i>=len(partner['row_groups']) or partner['row_groups'][i]['rows']!=original['rows']:
            raise ValueError('Counterpart row-group coverage changed')
        selected.append({**original,'key':counterpart_key})
    selected.sort(key=lambda x:x['change_type'])
    if (len(selected)!=2 or [x['change_type'] for x in selected]!=['added','removed']
        or sum(x['estimated_compressed_column_bytes'] for x in selected)>16*1024*1024
        or sum(x['rows'] for x in selected)>500_000):
        raise ValueError('Patch membership read exceeds fixed design')
    return {
        'study':'KEP-DATA-016','release':PATCH_RELEASE,
        'compared_release_path':ORIGINAL_RELEASE,'selected':selected,
        'all_counterpart_metadata_equal':True,'selected_row_groups':2,
        'source_metadata_zip_sha256':PINNED_ZIP_SHA256,
        'source_metadata_manifest_sha256':PINNED_MANIFEST_SHA256,
        'scope':'two_bounding_boxes_added_removed_only',
        'complete_for_all_union_ids':False,
        'verified_changelog_comparison_baseline':None,
        'observed_event_rows':0,'consumer_publish':False,
    }


def _validate_aggregate(x):
    if not isinstance(x,dict) or set(x)!=COMPARE_FIELDS:
        raise ValueError('Unexpected regional aggregate fields')
    digest=x['regional_observation_sha256']
    if not isinstance(digest,str) or not re.fullmatch('[0-9a-f]{64}',digest):
        raise ValueError('Invalid regional event fingerprint')
    counts=x['regional_event_type_counts']
    if not isinstance(counts,dict) or set(counts)!=COUNT_TYPES or any(
        type(v) is not int or v<0 for v in counts.values()):
        raise ValueError('Invalid event type counts')
    for k in COMPARE_FIELDS-{'regional_observation_sha256','regional_event_type_counts'}:
        if type(x[k]) is not int or x[k]<0:
            raise ValueError('Invalid aggregate count: '+k)
    if (x['regional_rows']!=sum(counts.values())
        or x['matched_union_ids']>x['unique_regional_ids']
        or x['unique_regional_ids']>x['regional_rows']
        or x['regional_rows']>x['scanned_rows']
        or x['conflicting_regional_ids'] or x['duplicate_exact_observations']):
        raise ValueError('Regional projection not clean')
    if counts['data_changed']!=0 or counts['unchanged']!=0:
        raise ValueError('Only added/removed accepted')


def compare_regional_fingerprints(before:dict,after:dict)->dict:
    """Compare audited regional projections; never claim full ID or GERS baseline."""
    _validate_aggregate(before);_validate_aggregate(after)
    if any(before[k]!=after[k] for k in COMPARE_FIELDS-{'regional_observation_sha256'}):
        raise ValueError('Regional capture populations, counts or scope disagree')
    equal=before['regional_observation_sha256']==after['regional_observation_sha256']
    return {
        'study':'KEP-DATA-016','source_root':'overturemaps',
        'compared_release_paths':[ORIGINAL_RELEASE,PATCH_RELEASE],
        'event_types':['added','removed'],
        'regional_event_rows_each':before['regional_rows'],
        'scanned_row_group_rows_each':before['scanned_rows'],
        'regional_observation_sets_equal':equal,
        'before_region_sha256':before['regional_observation_sha256'],
        'after_region_sha256':after['regional_observation_sha256'],
        'status':('SAME_REGIONAL_PROJECTION_NOT_BASELINE_ATTESTATION' if equal
                 else 'REGIONAL_PROJECTION_DIFFERENCE_REQUIRES_REVIEW'),
        'independent_publisher_roots':1,
        'safe_to_compose_as_independent_adjacent_hops':False,
        'verified_changelog_comparison_baseline':None,
        'official_membership_agreement_fraction':None,
        'complete_for_all_union_ids':False,
        'full_parquet_objects_equal':None,
        'business_event_accuracy_available':False,
        'physical_business_openings':None,'physical_business_closures':None,
        'consumer_publish':False,
    }
