"""Offline DATA-016 SHA-pinned scoped patch comparison. No source fetching."""
from __future__ import annotations
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from kepcore.gers_access_cost import PINNED_ZIP_SHA256
from kepcore.gers_patch_pair import COMPARE_FIELDS,compare_regional_fingerprints
from kepcore.overture_places import canonical
from scripts.probe_gers_patch import PRIOR_SHA,load_prior

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/'reports/KEP_DATA_016_PATCH_REGIONAL.json'
REPORT_SHA256='a1bfed37f2fa0f83bbd3bf395297cbd01f4a47e054c25b767db37ccf3cf2ea64'

def validate_receipt(raw:bytes)->dict:
    if type(raw) is not bytes or sha256(raw).hexdigest()!=REPORT_SHA256:
        raise ValueError('DATA-016 patch receipt checksum mismatch')
    d=json.loads(raw)
    if canonical(d)!=raw:
        raise ValueError('DATA-016 source receipt is noncanonical')
    required={'aggregate','body_budget_bytes','byte_scope','captured_change_types',
        'compared_with_release','complete_for_all_union_ids',
        'conservatively_reserved_body_bytes','consumer_publish','data_page_response_bytes',
        'independent_human_labels','observed_at','official_membership_agreement_fraction',
        'origin','physical_business_closures','physical_business_openings',
        'prior_aggregate_receipt_sha256','projected_compressed_chunk_bytes',
        'publisher_patch_scope','read_seconds','regional_patch_comparison',
        'request_count','scanned_rows','scope','selected_release',
        'source_metadata_zip_sha256','source_root','status','study',
        'verified_changelog_comparison_baseline'}
    if (set(d)!=required or d['study']!='KEP-DATA-016'
            or d['origin']!='captured_public_GERS_rows'
            or d['status']!='PATCH_REGIONAL_PROJECTION_CAPTURED_NOT_BASELINE_VERIFIED'
            or d['selected_release']!='2026-09-23.1'
            or d['compared_with_release']!='2026-09-23.0'
            or d['prior_aggregate_receipt_sha256']!=PRIOR_SHA
            or d['source_metadata_zip_sha256']!=PINNED_ZIP_SHA256
            or d['scope']!='regional_bbox_added_removed_only'
            or d['captured_change_types']!=['added','removed']
            or d['consumer_publish'] is not False
            or d['complete_for_all_union_ids'] is not False
            or d['independent_human_labels']!=0
            or d['official_membership_agreement_fraction'] is not None
            or d['verified_changelog_comparison_baseline'] is not None
            or d['physical_business_openings'] is not None
            or d['physical_business_closures'] is not None):
        raise ValueError('DATA-016 scope or truth boundary changed')
    a=d['aggregate']
    if (a['origin']!='captured_public_GERS_rows' or a['regional_rows']!=285
            or a['scanned_rows']!=207733 or a['matched_union_ids']!=285
            or a['regional_event_type_counts']!={'added':218,'removed':67,
                'data_changed':0,'unchanged':0}
            or a['full_id_union_coverage'] is not False):
        raise ValueError('DATA-016 aggregate differs from captured observation')
    rebuilt=compare_regional_fingerprints(load_prior(),{k:a[k] for k in COMPARE_FIELDS})
    if rebuilt!=d['regional_patch_comparison'] or not rebuilt['regional_observation_sets_equal']:
        raise ValueError('Region event fingerprints no longer match')
    if (d['data_page_response_bytes']!=8022067
            or d['data_page_response_bytes']>d['conservatively_reserved_body_bytes']
            or d['conservatively_reserved_body_bytes']>d['body_budget_bytes']
            or d['body_budget_bytes']!=16*1024*1024 or d['request_count']!=14
            or d['request_count']>128 or d['scanned_rows']!=207733):
        raise ValueError('Observed I/O cost changed')
    return d

def evaluate()->dict:
    if REPORT.is_symlink() or not REPORT.is_file():
        raise ValueError('Missing pinned patch receipt')
    return validate_receipt(REPORT.read_bytes())

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--check',action='store_true')
    args=p.parse_args()
    d=evaluate()
    if args.check:
        print(json.dumps({'study':'KEP-DATA-016','status':'PINNED_PATCH_REGIONAL_EQUIVALENCE',
            'source_receipt_sha256':REPORT_SHA256,
            'regional_event_sets_equal':d['regional_patch_comparison']['regional_observation_sets_equal'],
            'event_counts':d['aggregate']['regional_event_type_counts'],
            'official_membership_agreement_fraction':None,
            'verified_changelog_comparison_baseline':None,'consumer_publish':False},sort_keys=True))
    else:
        print(json.dumps(d,indent=2,sort_keys=True))

if __name__=='__main__':main()
