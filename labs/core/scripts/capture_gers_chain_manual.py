"""Explicit manual public-source capture, never run by ordinary CI.

No August Places download. Scan two changelog releases through a byte-limited
loopback proxy. A spatially bounded capture is PARTIAL globally, even if every
partition file was queried. Requires --fetch --research-confirmation RESEARCH_ONLY.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kepcore.overture_archive_artifact import load_original_research_zip
from kepcore.overture_real import load_archive
from kepcore.overture_places import PILOT, canonical

BUDGET = 268_435_456
S3 = 'https://overturemaps-us-west-2.s3.us-west-2.amazonaws.com/'
RELEASES = ('2026-09-23.0', '2026-09-23.1')
KINDS = ('added','removed','data_changed','unchanged')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def capture(output: Path) -> dict:
    import duckdb  # Separately installed pinned dependency; offline lab never needs it.
    if output.exists():
        raise ValueError('Capture output must not already exist')
    output.mkdir(parents=True)
    old,_,_ = load_original_research_zip(ROOT/'data/real/overture_istanbul_2026-08-19.0/original_actions_artifact.zip')
    new,_,_ = load_archive(verify=True)
    ids = sorted({r['overture_id'] for r in old + new['records']})
    report = {'format':'KEP-GERS-CHAIN-CAPTURE-v1','origin':'official_capture',
        'research_only':True,'consumer_publish':False,'source_root':'overturemaps',
        'rights_evidence_url':'https://docs.overturemaps.org/attribution/',
        'queried_ids_sha256':sha256(canonical(ids)).hexdigest(),
        'query_scope':'bbox_and_id_union_not_global','bounds':{k:list(v) for k,v in PILOT.items()},
        'budget_bytes':BUDGET,'transitions':[], 'objects':[], 'status':'IN_PROGRESS'}
    opener = urllib.request.build_opener(NoRedirect())
    transferred = requests = 0
    lock = threading.Lock()
    def read(url, *, method='GET', headers=None, maximum=1_000_000):
        nonlocal transferred, requests
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme!='https' or parsed.hostname not in {'stac.overturemaps.org',
                'overturemaps-us-west-2.s3.us-west-2.amazonaws.com'} or parsed.username or parsed.password:
            raise ValueError('Unapproved capture endpoint')
        with lock:
            if requests >= 1800 or transferred+maximum>BUDGET:
                raise ValueError('Research transfer budget exhausted')
            requests += 1
            transferred += maximum  # Reserve the worst case before concurrent I/O.
        consumed = 0
        try:
            req = urllib.request.Request(url, method=method, headers=headers or {})
            with opener.open(req, timeout=15) as response:
                if headers and 'Range' in headers and response.status!=206:
                    raise ValueError('Server ignored range request')
                body = response.read(maximum) if method!='HEAD' else b''
                consumed = len(body)
                if method!='HEAD' and not (headers and 'Range' in headers) and consumed==maximum:
                    raise ValueError('Per-request byte budget exhausted')
                if headers and 'Range' in headers and response.status!=206:
                    raise ValueError('Server ignored range request')
                return body, dict(response.headers), response.status
        finally:
            with lock:
                transferred -= maximum-consumed
    objects = {}
    ns = {'s':'http://s3.amazonaws.com/doc/2006-03-01/'}
    server = None
    try:
        previous = '2026-08-19.0'
        for release in RELEASES:
            url='https://stac.overturemaps.org/'+release+'/catalog.json'
            raw,_,status=read(url)
            catalog=json.loads(raw)
            prev=[x for x in catalog.get('links',[]) if x.get('rel')=='prev']
            if (catalog.get('id')!=release or len(prev)!=1
                    or prev[0].get('href')!='https://stac.overturemaps.org/'+previous+'/catalog.json'):
                raise ValueError('Unexpected intermediate release; do not invent transition')
            (output/(release+'.catalog.json')).write_bytes(raw)
            report['transitions'].append({'before_release':previous,'after_release':release,
                'catalog_url':url,'catalog_sha256':sha256(raw).hexdigest(),
                'catalog':catalog,'catalog_http_status':status,'rows':[],
                'all_partitions_scanned':False})
            previous=release
            for kind in KINDS:
                prefix='changelog/'+release+'/theme=places/type=place/change_type='+kind+'/'
                url=S3+'?'+urllib.parse.urlencode({'list-type':'2','prefix':prefix,'max-keys':100})
                raw,_,_=read(url)
                if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
                    raise ValueError('Unsafe source XML')
                doc=ET.fromstring(raw)
                if doc.findtext('s:IsTruncated',namespaces=ns)!='false':
                    raise ValueError('Incomplete object listing')
                found=[]
                for obj in doc.findall('s:Contents',ns):
                    key=obj.findtext('s:Key',namespaces=ns)
                    size=int(obj.findtext('s:Size',namespaces=ns))
                    etag=obj.findtext('s:ETag',namespaces=ns)
                    if not key.startswith(prefix) or not key.endswith('.parquet') or '..' in key or size<=8:
                        raise ValueError('Invalid listed changelog object')
                    item={'key':key,'bytes':size,'etag':etag,'release':release,'change_type':kind}
                    objects['/'+key]=item;found.append(item)
                if not found:
                    raise ValueError('Missing changelog partition')
                report['objects'].extend(found)
        class Proxy(BaseHTTPRequestHandler):
            def log_message(self,*args):
                return
            def serve(self,head=False):
                item=objects.get(urllib.parse.unquote(self.path))
                if item is None:
                    self.send_error(404);return
                try:
                    if head:
                        _,headers,_=read(S3+item['key'],method='HEAD',maximum=0)
                        if int(headers.get('Content-Length','-1'))!=item['bytes'] or headers.get('ETag')!=item['etag']:
                            raise ValueError('Object changed since listing')
                        self.send_response(200)
                        self.send_header('Content-Length',str(item['bytes']))
                        self.send_header('Accept-Ranges','bytes')
                        self.send_header('ETag',item['etag']);self.end_headers();return
                    range_value=self.headers.get('Range','')
                    if not range_value.startswith('bytes=') or ',' in range_value:
                        raise ValueError('Only bounded range requests allowed')
                    low,high=range_value[6:].split('-',1)
                    if not low or not high:
                        raise ValueError('Unbounded range request')
                    low,high=int(low),int(high)
                    if not 0<=low<=high<item['bytes'] or high-low+1>32_000_000:
                        raise ValueError('Invalid/oversized range')
                    body,headers,status=read(S3+item['key'],headers={'Range':range_value,
                        'If-Match':item['etag']},maximum=high-low+1)
                    if len(body)!=high-low+1 or headers.get('ETag')!=item['etag']:
                        raise ValueError('Source range identity mismatch')
                    self.send_response(status)
                    self.send_header('Content-Length',str(len(body)))
                    self.send_header('Content-Range',headers['Content-Range'])
                    self.send_header('Accept-Ranges','bytes');self.end_headers();self.wfile.write(body)
                except (ValueError,OSError,urllib.error.URLError):
                    self.send_error(503,'Bounded source read failed')
            def do_HEAD(self):
                self.serve(True)
            def do_GET(self):
                self.serve()
        server=ThreadingHTTPServer(('127.0.0.1',0),Proxy)
        server.daemon_threads=True
        threading.Thread(target=server.serve_forever,daemon=True).start()
        con=duckdb.connect()
        con.execute("SET memory_limit='768MB'; SET threads=2;")
        con.execute('INSTALL httpfs; LOAD httpfs;')
        con.execute("SET http_timeout=15; SET http_retries=0;")
        con.execute('CREATE TABLE wanted(id VARCHAR PRIMARY KEY)')
        con.executemany('INSERT INTO wanted VALUES (?)',[(rid,) for rid in ids])
        where=' OR '.join('(bbox.xmin <= %s AND bbox.xmax >= %s AND bbox.ymin <= %s AND bbox.ymax >= %s)'%
            (bounds[2]+.0001,bounds[0]-.0001,bounds[3]+.0001,bounds[1]-.0001) for bounds in PILOT.values())
        for edge in report['transitions']:
            urls=['http://127.0.0.1:'+str(server.server_port)+path for path,item in objects.items()
                  if item['release']==edge['after_release']]
            query="SELECT id,change_type,columns_changed FROM read_parquet(?,hive_partitioning=true,union_by_name=true) WHERE ("+where+") AND id IN (SELECT id FROM wanted) ORDER BY id,change_type"
            rows=con.execute(query,[urls]).fetchall()
            if len(rows)>20_000:
                raise ValueError('Unexpected result growth')
            edge['rows']=[{'id':r[0],'change_type':r[1],'columns_changed':r[2]} for r in rows]
            edge['rows_sha256']=sha256(canonical(edge['rows'])).hexdigest()
            edge['all_partitions_scanned']=True
        report['status']='CAPTURED_SPATIALLY_BOUNDED_NOT_GLOBAL'
    except Exception as exc:
        report['status']='INCOMPLETE_CAPTURE'
        report['failure_type']=type(exc).__name__
        report['failure_detail']=str(exc)[:1500]
    finally:
        if server is not None:
            server.shutdown()
        report['retrieved_at']=datetime.now(timezone.utc).isoformat()
        report['bytes_transferred']=transferred
        report['http_requests']=requests
        report['network_budget_complied']=transferred<=BUDGET
        (output/'gers_chain_capture.json').write_bytes(canonical(report))
        print(json.dumps({k:v for k,v in report.items() if k not in {'transitions','objects'}},indent=2))
        for edge in report['transitions']:
            print(edge['before_release'],edge['after_release'],len(edge['rows']),edge['all_partitions_scanned'])
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--fetch',action='store_true')
    p.add_argument('--research-confirmation')
    p.add_argument('--output',type=Path)
    args=p.parse_args()
    if not args.fetch:
        print(json.dumps({'status':'OFFLINE_DEFAULT','network_calls':0,'paid_api_calls':0}));return
    if args.research_confirmation!='RESEARCH_ONLY' or args.output is None:
        p.error('Explicit RESEARCH_ONLY confirmation and fresh output path required')
    result=capture(args.output)
    if result['status']!='CAPTURED_SPATIALLY_BOUNDED_NOT_GLOBAL':
        raise SystemExit(3)


if __name__=='__main__':
    main()
