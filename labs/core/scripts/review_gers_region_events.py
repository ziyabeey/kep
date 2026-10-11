"""Offline DATA-015 replay of immutable public GERS regional aggregate receipt.

This checks stored bytes and abstention boundaries. It does not independently
read original event Parquet and cannot authenticate the changelog predecessor.
"""
from __future__ import annotations

from hashlib import sha256
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from kepcore.overture_places import canonical
from kepcore.gers_access_cost import PINNED_ZIP_SHA256

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/'reports/KEP_DATA_015_REGIONAL_EVENTS.json'
PINNED_SHA256='8796914fb07117ddd5551c7480def866d17e8e7c8b04df8ed42af52d79598a10'

def validate_receipt(raw:bytes)->dict:
    if type(raw) is not bytes or sha256(raw).hexdigest()!=PINNED_SHA256:
        raise ValueError('Original regional event receipt SHA-256 changed')
    data=json.loads(raw)
    if canonical(data)!=raw:
        raise ValueError('Noncanonical source receipt')
    required={'study','origin','status','selected_release','source_root','scope',
              'complete_for_all_union_ids','official_membership_agreement_fraction',
              'consumer_publish','physical_business_openings','physical_business_closures',
              'independent_human_labels','source_metadata_zip_sha256',
              'publisher_patch_scope','aggregate','data_page_response_bytes',
              'conservatively_reserved_body_bytes','request_count',
              'body_budget_bytes','read_seconds','observed_at','scanned_rows',
              'projected_compressed_chunk_bytes','byte_scope','captured_change_types'}
    if (set(data)!=required or data['study']!='KEP-DATA-015'
            or data['origin']!='captured_public_GERS_rows'
            or data['status']!='REGIONAL_OBSERVATIONS_CAPTURED_NOT_COMPLETE_ID_UNION'
            or data['selected_release']!='2026-09-23.0'
            or data['captured_change_types']!=['added','removed']
            or data['source_metadata_zip_sha256']!=PINNED_ZIP_SHA256
            or data['scope']!='regional_bbox_rows_only'
            or data['source_root']!='overturemaps'
            or data['complete_for_all_union_ids'] is not False
            or data['official_membership_agreement_fraction'] is not None
            or data['physical_business_openings'] is not None
            or data['physical_business_closures'] is not None
            or data['independent_human_labels']!=0
            or data['consumer_publish'] is not False):
        raise ValueError('Regional source evidence misrepresented as global or business truth')
    a=data['aggregate']
    if (not isinstance(a,dict) or a['study']!='KEP-DATA-015'
            or a['origin']!='captured_public_GERS_rows'
            or a['regional_event_type_counts']!={'added':218,'removed':67,
                                                 'data_changed':0,'unchanged':0}
            or a['regional_rows']!=285 or a['unique_regional_ids']!=285
            or a['matched_union_ids']!=285 or a['conflicting_regional_ids']!=0
            or a['duplicate_exact_observations']!=0 or a['scanned_rows']!=207733
            or a['safe_to_reconcile_membership'] is not False
            or a['full_id_union_coverage'] is not False
            or a['verified_patch_predecessor'] is not None):
        raise ValueError('Original regional observation counts or scope changed')
    patch=data['publisher_patch_scope']
    if (patch['verified_changelog_comparison_baseline'] is not None
            or patch['may_sum_september_changelogs_as_independent_hops'] is not False
            or patch['one_publisher_cannot_vote_twice'] is not True):
        raise ValueError('Unverified patch baseline was elevated')
    if (data['body_budget_bytes']!=16*1024*1024
            or data['data_page_response_bytes']!=8022067
            or data['data_page_response_bytes']>data['conservatively_reserved_body_bytes']
            or data['conservatively_reserved_body_bytes']>data['body_budget_bytes']
            or data['request_count']!=14
            or data['request_count']>128):
        raise ValueError('Read budget or measured HTTP cost changed')
    return data

def evaluate()->dict:
    if REPORT.is_symlink() or not REPORT.is_file():
        raise ValueError('Pinned regional receipt missing or unsafe')
    return validate_receipt(REPORT.read_bytes())

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    result=evaluate()
    if args.check:
        print(json.dumps({'study':'KEP-DATA-015','status':'PINNED_AGGREGATE_CHECKED',
            'source_receipt_sha256':PINNED_SHA256,
            'region_event_counts':result['aggregate']['regional_event_type_counts'],
            'complete_for_all_union_ids':False,'official_membership_agreement_fraction':None,
            'consumer_publish':False},sort_keys=True))
    else:
        print(json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False))

if __name__=='__main__':
    main()
