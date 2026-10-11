"""DATA-014 offline replay or explicitly authorized, metadata-only public capture."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
import io
import json
from pathlib import Path
import sys
from threading import Lock
from time import perf_counter
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from kepcore import gers_access_cost as cost
from kepcore.gers_reconciliation import assess_changelog_compatibility, load_pinned_pair
from kepcore.overture_places import PILOT, canonical
S3='https://overturemaps-us-west-2.s3.us-west-2.amazonaws.com/'
ARROW_VERSION='21.0.0'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        return None


class Reader:
    def __init__(self):
        self.budget=cost.BodyBudget()
        self.body_bytes=0
        self.lock=Lock()

    def read(self,url,*,maximum,headers=None):
        if not url.startswith(S3):
            raise ValueError('Only reviewed public S3 endpoint allowed')
        self.budget.reserve(maximum)
        request=urllib.request.Request(url,headers={'Accept-Encoding':'identity',**(headers or {})})
        opener=urllib.request.build_opener(NoRedirect())
        with opener.open(request,timeout=15) as r:
            content_length=r.headers.get('Content-Length')
            if content_length is None or not content_length.isdigit() or int(content_length)>maximum:
                raise ValueError('Missing or oversized response length')
            raw=r.read(maximum)
            with self.lock:self.body_bytes+=len(raw)
            if len(raw)!=int(content_length):
                raise ValueError('Truncated metadata response')
            return raw,dict(r.headers),r.status

    def range(self,item,start,end):
        raw,h,status=self.read(S3+item['key'],maximum=end-start+1,
            headers={'Range':f'bytes={start}-{end}','If-Match':item['etag']})
        cost.validate_range(status,h,start,end,item['size'],item['etag'],raw)
        return raw


def listed_objects(reader):
    out=[]
    for release in cost.RELEASES:
        for kind in cost.KINDS:
            prefix=f'changelog/{release}/theme=places/type=place/change_type={kind}/'
            query=urllib.parse.urlencode({'list-type':'2','prefix':prefix,'max-keys':'100'})
            raw,_,status=reader.read(S3+'?'+query,maximum=128*1024)
            if status!=200 or b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
                raise ValueError('Unsafe or unsuccessful source inventory')
            ns={'s':'http://s3.amazonaws.com/doc/2006-03-01/'}
            doc=ET.fromstring(raw)
            if (doc.findtext('s:IsTruncated',namespaces=ns)!='false'
                    or doc.findtext('s:Prefix',namespaces=ns)!=prefix):
                raise ValueError('Incomplete or wrong source listing')
            items=[]
            for e in doc.findall('s:Contents',ns):
                key=e.findtext('s:Key',namespaces=ns)
                etag=e.findtext('s:ETag',namespaces=ns)
                size=int(e.findtext('s:Size',namespaces=ns))
                if (not key or not key.startswith(prefix) or '/' in key[len(prefix):]
                        or not key.endswith('.parquet') or '..' in key or size<=12
                        or not etag or not etag.startswith('"') or not etag.endswith('"')):
                    raise ValueError('Invalid public object metadata')
                items.append({'key':key,'release':release,'change_type':kind,'etag':etag,'size':size,
                    'last_modified':e.findtext('s:LastModified',namespaces=ns),
                    'listing_sha256':sha256(raw).hexdigest()})
            if not items:raise ValueError('Missing change partition; no empty-success assumption')
            out.extend(items)
    if len(out)>256 or len({o['key'] for o in out})!=len(out):
        raise ValueError('Duplicate or oversized object inventory')
    return sorted(out,key=lambda o:o['key'])


def decode_footer(item,footer):
    import pyarrow as pa
    import pyarrow.parquet as pq
    if pa.__version__!=ARROW_VERSION:
        raise ValueError('Manual capture requires pinned pyarrow=='+ARROW_VERSION)
    # Metadata-only wrapper; column offsets refer to the ORIGINAL S3 object.
    # No data page is decoded from this wrapper.
    md=pq.read_metadata(pa.BufferReader(b'PAR1'+footer))
    groups=[]
    for i in range(md.num_row_groups):
        rg=md.row_group(i);cols=[]
        for j in range(rg.num_columns):
            c=rg.column(j);s=c.statistics
            path=c.path_in_schema
            order='UNKNOWN'
            logical=md.schema.column(j).logical_type
            if path=='id' and str(logical)=='String' and c.physical_type=='BYTE_ARRAY':order='UTF8_BYTEWISE'
            elif path.startswith('bbox.') and c.physical_type in {'FLOAT','DOUBLE'}:order='NUMERIC'
            values=None
            if s is not None:
                lo,hi=(s.min,s.max) if s.has_min_max else (None,None)
                if type(lo) not in {str,int,float,type(None)} or type(hi) not in {str,int,float,type(None)}:
                    lo=hi=None
                if path.startswith('columns_changed.'):
                    lo=hi=None;order='UNKNOWN'
                values={'min':lo,'max':hi,'null_count':s.null_count,'order':order}
            offsets=[c.data_page_offset]
            if c.has_dictionary_page:offsets.append(c.dictionary_page_offset)
            cols.append({'path':path,'physical_type':c.physical_type,
                'compressed_bytes':c.total_compressed_size,'offset':min(offsets),'statistics':values})
        groups.append({'rows':rg.num_rows,'columns':cols})
    name='footers/'+sha256(item['key'].encode()).hexdigest()+'.bin'
    result={**item,'footer_length':len(footer)-8,'footer_sha256':sha256(footer).hexdigest(),
        'footer_member':name,'rows':md.num_rows,'row_groups':groups,'created_by':md.created_by}
    cost.validate_objects([result])
    return result


def capture(output):
    if output.exists() or output.is_symlink():
        raise ValueError('Capture output must be a fresh directory')
    import pyarrow as pa
    if pa.__version__!=ARROW_VERSION:raise ValueError('Wrong optional Arrow version')
    compatibility=assess_changelog_compatibility()
    before,after=load_pinned_pair()
    ids=sorted({r['overture_id'] for s in (before,after) for r in s.records})
    output.mkdir(parents=True)
    reader=Reader();began=perf_counter();footers={}
    report={'format':'KEP-GERS-FOOTERS-v1','origin':'captured_public_footer_metadata',
        'status':'INCOMPLETE_METADATA','rights_evidence_url':'https://docs.overturemaps.org/attribution/',
        'changelog_documentation':'https://docs.overturemaps.org/gers/changelog/',
        'release_chain':compatibility['release_chain'],'source_root':'overturemaps',
        'pyarrow_version':pa.__version__,'research_only':True,'consumer_publish':False,
        'data_page_bytes_read':0,'official_event_rows_read':0,'objects':[]}
    try:
        items=listed_objects(reader)
        report['listed_objects']=len(items)
        def work(item):
            if reader.range(item,0,3)!=b'PAR1':raise ValueError('Unsupported Parquet header')
            tail=reader.range(item,item['size']-8,item['size']-1)
            start,end=cost.footer_span(tail,item['size'])
            footer=reader.range(item,start,end)+tail
            return decode_footer(item,footer),footer
        with ThreadPoolExecutor(max_workers=4) as pool:
            for obj,raw in pool.map(work,items):
                report['objects'].append(obj);footers[obj['footer_member']]=raw
        report['objects'].sort(key=lambda o:o['key'])
        report['analysis']=cost.plan_cost(report['objects'],ids,PILOT,inventory_complete=True)
        report['status']='COMPLETE_METADATA'
    except Exception as exc:
        report['failure_type']=type(exc).__name__
        report['failure_detail']=str(exc)[:1000]
    report.update(retrieved_at=datetime.now(timezone.utc).isoformat(),
        capture_seconds=round(perf_counter()-began,6),body_bytes_read=reader.body_bytes,
        accounted_body_allowance=reader.budget.accounted_bytes,
        request_count=reader.budget.requests,budget_bytes=reader.budget.limit,
        byte_scope='application response bodies; headers, TLS and optional package installation excluded')
    (output/'receipt.json').write_bytes(canonical({k:v for k,v in report.items() if k!='objects'}))
    if report['status']=='COMPLETE_METADATA':
        archive=output/'footers.zip'
        with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
            z.writestr('manifest.json',canonical(report))
            for name,raw in sorted(footers.items()):z.writestr(name,raw)
        digest=sha256(archive.read_bytes()).hexdigest()
        cost.load_capture(archive,digest)
        (output/'SHA256.txt').write_text(digest+'  footers.zip\n')
    print(json.dumps({k:v for k,v in report.items() if k!='objects'},ensure_ascii=False,indent=2))
    return report


def replay():
    m=cost.load_capture(cost.DATA_DIR/'footers.zip',cost.PINNED_ZIP_SHA256)
    before,after=load_pinned_pair()
    ids=sorted({r['overture_id'] for s in (before,after) for r in s.records})
    result=cost.plan_cost(m['objects'],ids,PILOT,inventory_complete=True)
    if result!=m['analysis']:raise ValueError('Normalized metadata replay changed')
    return {'stable_results':result,'observed_capture':{k:m[k] for k in (
        'retrieved_at','body_bytes_read','accounted_body_allowance','request_count','budget_bytes',
        'capture_seconds','byte_scope','release_chain','pyarrow_version')}}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--fetch',action='store_true');p.add_argument('--research-confirmation')
    p.add_argument('--output',type=Path);p.add_argument('--replay',action='store_true')
    args=p.parse_args()
    if args.fetch:
        if args.replay or args.research_confirmation!='METADATA_ONLY_16MIB' or args.output is None:
            p.error('Explicit METADATA_ONLY_16MIB confirmation and fresh output required')
        if capture(args.output)['status']!='COMPLETE_METADATA':raise SystemExit(3)
    elif args.replay:
        if args.output is not None:p.error('Replay does not write acquisition files')
        print(json.dumps(replay(),indent=2,sort_keys=True,ensure_ascii=False))
    else:print(json.dumps({'status':'OFFLINE_DEFAULT','network_calls':0,'event_rows':0}))


if __name__=='__main__':main()
