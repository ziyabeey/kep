"""DATA-016: explicitly authorized .1 patch regional events, not global agreement.

Read only two exact pinned GERS added/removed row groups, 16 MiB max. Equal
regional fingerprints do not certify publisher changelog comparison ancestry.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
from hashlib import sha256
import json
from pathlib import Path
import sys
from time import perf_counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from kepcore.gers_access_cost import DATA_DIR,PINNED_ZIP_SHA256,load_capture
from kepcore.gers_patch_pair import select_patch_counterparts,compare_regional_fingerprints,COMPARE_FIELDS
from kepcore.gers_reconciliation import load_pinned_pair
from kepcore.gers_region_probe import summarize_events,publisher_patch_scope
from kepcore.overture_places import canonical
from scripts.probe_gers_region import RemoteRanges,RemoteFile,source_item,OPTIONAL_ARROW_VERSION,MAX_READ_BODY

ROOT=Path(__file__).resolve().parents[1]
PRIOR_PATH=ROOT/'reports/KEP_DATA_015_REGIONAL_EVENTS.json'
PRIOR_SHA='8796914fb07117ddd5551c7480def866d17e8e7c8b04df8ed42af52d79598a10'
ACK='PATCH_REGIONAL_EQUIVALENCE_16MIB'

def load_prior()->dict:
    if PRIOR_PATH.is_symlink() or not PRIOR_PATH.is_file():
        raise ValueError('DATA-015 prerequisite evidence missing')
    raw=PRIOR_PATH.read_bytes()
    if sha256(raw).hexdigest()!=PRIOR_SHA:
        raise ValueError('DATA-015 prior event receipt changed')
    old=json.loads(raw)
    if (canonical(old)!=raw or old['study']!='KEP-DATA-015'
            or old['status']!='REGIONAL_OBSERVATIONS_CAPTURED_NOT_COMPLETE_ID_UNION'
            or old['selected_release']!='2026-09-23.0'
            or old['captured_change_types']!=['added','removed']
            or old['source_metadata_zip_sha256']!=PINNED_ZIP_SHA256
            or old['complete_for_all_union_ids'] is not False
            or old['official_membership_agreement_fraction'] is not None
            or old['physical_business_openings'] is not None
            or old['physical_business_closures'] is not None):
        raise ValueError('DATA-015 not an allowable regional predecessor')
    return {k:old['aggregate'][k] for k in COMPARE_FIELDS}

def run(output:Path)->dict:
    # No optional dependencies or source traffic in default offline mode.
    import pyarrow as pa
    import pyarrow.parquet as pq
    if pa.__version__!=OPTIONAL_ARROW_VERSION:
        raise ValueError('Pinned Arrow version required')
    if output.is_symlink() or output.exists():
        raise ValueError('Source output directory must be fresh and non-symlink')
    manifest=load_capture(DATA_DIR/'footers.zip',PINNED_ZIP_SHA256)
    plan=select_patch_counterparts(manifest)
    prior=load_prior()
    before,after=load_pinned_pair()
    union={r['overture_id'] for snap in (before,after) for r in snap.records}
    if len(union)!=4872:
        raise ValueError('Pinned ID population changed')
    selected=plan['selected']
    output.mkdir(parents=True)
    src=RemoteRanges(release='2026-09-23.1')
    scanned=0
    t0=perf_counter()
    result={
        'study':'KEP-DATA-016','origin':'captured_public_GERS_rows',
        'status':'INCOMPLETE_PATCH_CAPTURE','source_root':'overturemaps',
        'selected_release':'2026-09-23.1','compared_with_release':'2026-09-23.0',
        'prior_aggregate_receipt_sha256':PRIOR_SHA,
        'source_metadata_zip_sha256':PINNED_ZIP_SHA256,
        'scope':'regional_bbox_added_removed_only','captured_change_types':['added','removed'],
        'projected_compressed_chunk_bytes':sum(x['estimated_compressed_column_bytes'] for x in selected),
        'complete_for_all_union_ids':False,
        'verified_changelog_comparison_baseline':None,
        'official_membership_agreement_fraction':None,
        'physical_business_openings':None,'physical_business_closures':None,
        'consumer_publish':False,'independent_human_labels':0,
        'publisher_patch_scope':publisher_patch_scope(),
    }
    try:
        def iter_rows():
            nonlocal scanned
            for item in selected:
                remote=RemoteFile(src,source_item(item))
                parquet=pq.ParquetFile(remote,pre_buffer=False)
                if parquet.metadata.row_group(item['row_group']).num_rows!=item['rows']:
                    raise ValueError('Pinned patch row group changed')
                table=parquet.read_row_group(item['row_group'],
                          columns=['id','bbox','columns_changed'],use_threads=False)
                if table.num_rows!=item['rows']:
                    raise ValueError('Incomplete patch group read')
                for batch in table.to_batches(max_chunksize=8192):
                    for row in batch.to_pylist():
                        scanned+=1
                        yield item['change_type'],row
                remote.close()
        aggregate=summarize_events(iter_rows(),union,origin='captured_public_GERS_rows')
        if scanned!=sum(x['rows'] for x in selected):
            raise ValueError('Not all selected records scanned')
        compact={k:aggregate[k] for k in COMPARE_FIELDS}
        result['aggregate']=aggregate
        result['regional_patch_comparison']=compare_regional_fingerprints(prior,compact)
        result['status']='PATCH_REGIONAL_PROJECTION_CAPTURED_NOT_BASELINE_VERIFIED'
    except Exception as exc:
        result['failure_type']=type(exc).__name__
        result['failure_detail']=str(exc)[:600]
    result.update({
        'observed_at':datetime.now(timezone.utc).isoformat(),
        'read_seconds':round(perf_counter()-t0,6),
        'data_page_response_bytes':src.bytes_read,
        'conservatively_reserved_body_bytes':src.budget.bytes_reserved,
        'request_count':src.budget.requests,'scanned_rows':scanned,
        'body_budget_bytes':MAX_READ_BODY,
        'byte_scope':'S3 HTTP application body bytes, excludes headers and Arrow install',
    })
    (output/'research_receipt.json').write_bytes(canonical(result))
    print(json.dumps(result,ensure_ascii=False,sort_keys=True))
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--fetch',action='store_true')
    p.add_argument('--research-confirmation')
    p.add_argument('--output',type=Path)
    args=p.parse_args()
    if not args.fetch:
        print(json.dumps({'status':'OFFLINE_DEFAULT','network_calls':0,'source_event_rows':0}))
        return
    if args.research_confirmation!=ACK or args.output is None:
        p.error('Explicit research confirmation and fresh output path required')
    if run(args.output)['status']!='PATCH_REGIONAL_PROJECTION_CAPTURED_NOT_BASELINE_VERIFIED':
        raise SystemExit(3)

if __name__=='__main__':main()
