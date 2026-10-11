"""DATA-015 optional 16 MiB bounded public GERS added/removed regional observation.

No traffic without --fetch --research-confirmation REGIONAL_MEMBERSHIP_16MIB
and a fresh --output directory. Official all-ID agreement stays unmeasured.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import io
import json
from pathlib import Path
import sys
from time import perf_counter
import urllib.request
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from kepcore.gers_access_cost import (DATA_DIR,PINNED_ZIP_SHA256,load_capture)
from kepcore.gers_reconciliation import load_pinned_pair
from kepcore.gers_region_probe import (RangeBudget, regional_plan, summarize_events,
    validate_response, publisher_patch_scope)
from kepcore.overture_places import canonical

ROOT=Path(__file__).resolve().parents[1]
S3='https://overturemaps-us-west-2.s3.us-west-2.amazonaws.com/'
OPTIONAL_ARROW_VERSION='21.0.0'
PROBE_KINDS=frozenset({'added','removed'})
MAX_READ_BODY=16*1024*1024


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


class RemoteRanges:
    def __init__(self, *, release='2026-09-23.0'):
        if release not in {'2026-09-23.0','2026-09-23.1'}:
            raise ValueError('Unreviewed regional GERS release')
        self.release=release
        self.budget=RangeBudget(limit=MAX_READ_BODY,requests=128)
        self.bytes_read=0
        self.opener=urllib.request.build_opener(NoRedirect())
        self.failed=False

    def read(self,item,start,end):
        if self.failed:raise ValueError('Source access stopped after failure')
        key=item['key'];prefix=f'changelog/{self.release}/theme=places/type=place/change_type='
        if (not key.startswith(prefix) or '/part-' not in key or '..' in key):
            raise ValueError('Unreviewed public source path')
        if (type(start) is not int or type(end) is not int or
                not 0<=start<=end<item['size']):
            raise ValueError('Out-of-object range forbidden')
        length=end-start+1
        self.budget.reserve(length)
        req=urllib.request.Request(S3+key,headers={
            'Range':f'bytes={start}-{end}', 'If-Match':item['etag'],
            'Accept-Encoding':'identity'})
        try:
            with self.opener.open(req,timeout=20) as response:
                h=dict(response.headers)
                if (response.status!=206 or h.get('Content-Length')!=str(length)
                        or h.get('Content-Encoding','identity')!='identity'):
                    raise ValueError('Unsafe server response before body read')
                body=response.read(length)
                self.bytes_read+=len(body)
                validate_response(response.status,h,start,end,item,body)
                return body
        except Exception:
            self.failed=True
            raise


def source_item(selected):
    """Convert a pinned planning record into a range-ready object."""
    if (not isinstance(selected,dict) or
            type(selected.get('object_bytes')) is not int or selected['object_bytes']<=12 or
            'size' in selected):
        raise ValueError('Malformed immutable row-group object identity')
    return {**selected,'size':selected['object_bytes']}


class RemoteFile(io.RawIOBase):
    """Strictly bounded, synchronous seek/read interface for Arrow ParquetFile."""
    def __init__(self,source,item):
        self.source=source;self.item=item;self.pos=0
        super().__init__()

    def readable(self):return True
    def seekable(self):return True
    def tell(self):return self.pos

    def seek(self,where,whence=0):
        if type(where) is not int or type(whence) is not int:
            raise ValueError('Invalid read offset')
        new=where if whence==0 else (self.pos+where if whence==1 else (self.item['size']+where if whence==2 else -1))
        if not 0<=new<=self.item['size']:raise ValueError('Invalid remote seek')
        self.pos=new
        return self.pos

    def read(self,size=-1):
        if type(size) is not int or size<0:raise ValueError('Unbounded source read forbidden')
        if size==0 or self.pos==self.item['size']:return b''
        last=min(self.item['size'],self.pos+size)-1
        data=self.source.read(self.item,self.pos,last)
        self.pos+=len(data)
        return data

    def readinto(self,buffer):
        data=self.read(len(buffer));buffer[:len(data)]=data
        return len(data)


def run(output):
    import pyarrow as pa
    import pyarrow.parquet as pq
    if pa.__version__!=OPTIONAL_ARROW_VERSION:
        raise ValueError('Pinned optional Arrow version required')
    if output.is_symlink() or output.exists():raise ValueError('Fresh research output only')
    manifest=load_capture(DATA_DIR/'footers.zip',PINNED_ZIP_SHA256)
    plan=regional_plan(manifest)
    selected=[x for x in plan['selected'] if x['change_type'] in PROBE_KINDS]
    if len(selected)!=2 or sum(x['estimated_compressed_column_bytes'] for x in selected)>MAX_READ_BODY:
        raise ValueError('Selected membership read is not within preregistered limits')
    snapshots=load_pinned_pair()
    union_ids={r['overture_id'] for snap in snapshots for r in snap.records}
    if len(union_ids)!=4872:raise ValueError('Frozen ID-union population changed')
    output.mkdir(parents=True)
    reader=RemoteRanges();t0=perf_counter();rows_read=0
    result={'study':'KEP-DATA-015','origin':'captured_public_GERS_rows',
            'status':'INCOMPLETE_EVENT_CAPTURE','selected_release':'2026-09-23.0',
            'captured_change_types':['added','removed'],'source_root':'overturemaps',
            'scope':'regional_bbox_rows_only','complete_for_all_union_ids':False,
            'publisher_patch_scope':publisher_patch_scope(),
            'source_metadata_zip_sha256':PINNED_ZIP_SHA256,
            'projected_compressed_chunk_bytes':sum(x['estimated_compressed_column_bytes'] for x in selected),
            'consumer_publish':False,'official_membership_agreement_fraction':None,
            'physical_business_openings':None,'physical_business_closures':None,
            'independent_human_labels':0}
    try:
        def scan():
            nonlocal rows_read
            for item in selected:
                remote=RemoteFile(reader,source_item(item))
                parquet=pq.ParquetFile(remote,pre_buffer=False)
                if parquet.metadata.row_group(item['row_group']).num_rows!=item['rows']:
                    raise ValueError('Parquet metadata row group changed from pinned original')
                table=parquet.read_row_group(item['row_group'],columns=['id','bbox','columns_changed'],use_threads=False)
                if table.num_rows!=item['rows']:
                    raise ValueError('Partial column row-group read')
                for batch in table.to_batches(max_chunksize=8192):
                    for row in batch.to_pylist():
                        rows_read+=1
                        yield item['change_type'],row
                remote.close()
        summary=summarize_events(scan(),union_ids,origin='captured_public_GERS_rows')
        if rows_read!=sum(x['rows'] for x in selected):
            raise ValueError('Not all selected regional row groups examined')
        result['aggregate']=summary
        result['status']='REGIONAL_OBSERVATIONS_CAPTURED_NOT_COMPLETE_ID_UNION'
    except Exception as exc:
        result['failure_type']=type(exc).__name__
        result['failure_detail']=str(exc)[:1200]
    result.update(observed_at=datetime.now(timezone.utc).isoformat(),
        read_seconds=round(perf_counter()-t0,6),
        data_page_response_bytes=reader.bytes_read,
        conservatively_reserved_body_bytes=reader.budget.bytes_reserved,
        request_count=reader.budget.requests,scanned_rows=rows_read,
        body_budget_bytes=MAX_READ_BODY,
        byte_scope='source HTTP application-body bytes only; package installation and headers excluded')
    (output/'research_receipt.json').write_bytes(canonical(result))
    print(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fetch',action='store_true')
    parser.add_argument('--research-confirmation')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if not args.fetch:
        print(json.dumps({'status':'OFFLINE_DEFAULT','network_calls':0,'event_rows':0}))
        return
    if args.research_confirmation!='REGIONAL_MEMBERSHIP_16MIB' or args.output is None:
        parser.error('Explicit research confirmation and fresh output path required')
    if run(args.output)['status']!='REGIONAL_OBSERVATIONS_CAPTURED_NOT_COMPLETE_ID_UNION':
        raise SystemExit(3)

if __name__=='__main__':main()
