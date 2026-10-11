"""DATA-014: metadata-only GERS access planning, never changelog event evidence.

The acquisition CLI uses a pinned optional Arrow reader. Ordinary replay needs
only this module and the hashed, normalized public footer-metadata capture.
"""
from __future__ import annotations
from bisect import bisect_left
from collections import Counter
from hashlib import sha256
from math import isfinite
from pathlib import Path
from threading import Lock
from uuid import UUID
import json
import re
import struct
import zipfile

from .overture_places import canonical

RELEASES = ('2026-09-23.0', '2026-09-23.1')
KINDS = ('added', 'removed', 'data_changed', 'unchanged')
MAX_BODY = 16 * 1024 * 1024
MAX_FOOTER = 2 * 1024 * 1024
COLUMNS = {'id', 'bbox.xmin', 'bbox.xmax', 'bbox.ymin', 'bbox.ymax',
           'columns_changed.list.element'}
DATA_DIR = Path(__file__).resolve().parents[1]/'data/real/gers_footer_2026-10-11'
PINNED_ZIP_SHA256 = None  # Set only after an actual capture and independent byte check.


def positive_int(v, label, *, zero=False):
    if type(v) is not int or v < (0 if zero else 1):
        raise ValueError('Invalid '+label)
    return v


class BodyBudget:
    """Reserve before I/O. Failed reads remain charged at their worst-case size.

    Counts application body allowances, not wire traffic or response headers.
    A bounded sequence of reads cannot silently grow the experiment's budget.
    """
    def __init__(self, limit=MAX_BODY):
        positive_int(limit, 'budget')
        if limit > MAX_BODY:
            raise ValueError('Reviewed metadata budget cannot be increased')
        self.limit, self.accounted_bytes, self.requests = limit, 0, 0
        self._lock = Lock()

    def reserve(self, count):
        positive_int(count, 'read allowance')
        with self._lock:
            if self.requests >= 512 or self.accounted_bytes + count > self.limit:
                raise ValueError('Metadata body/request budget exhausted')
            self.requests += 1
            self.accounted_bytes += count


def footer_span(trailer: bytes, object_size: int) -> tuple[int, int]:
    positive_int(object_size, 'object size')
    if not isinstance(trailer, bytes) or len(trailer) != 8 or trailer[4:] != b'PAR1':
        raise ValueError('Unsupported, encrypted, or truncated Parquet trailer')
    length = struct.unpack('<I', trailer[:4])[0]
    if not 0 < length <= MAX_FOOTER or object_size - 8 - length < 4:
        raise ValueError('Unsafe Parquet footer extent')
    return object_size - 8 - length, object_size - 9


def validate_range(status, headers, start, end, size, etag, body):
    h = {k.lower():v for k,v in headers.items()}
    if (status != 206 or h.get('content-range') != f'bytes {start}-{end}/{size}'
            or h.get('content-length') != str(end-start+1) or h.get('etag') != etag
            or len(body) != end-start+1 or h.get('content-encoding', 'identity') != 'identity'):
        raise ValueError('Range status, extent, length, encoding or ETag mismatch')


def validate_objects(objects):
    """Reject incomplete schemas, repeated observations and invalid chunk extents."""
    if not isinstance(objects,list) or not objects or len(objects)>256:
        raise ValueError('Missing or unbounded object inventory')
    seen=set()
    for o in objects:
        if not isinstance(o,dict) or o.get('release') not in RELEASES or o.get('change_type') not in KINDS:
            raise ValueError('Unreviewed release or partition')
        key=o.get('key','')
        prefix=f"changelog/{o['release']}/theme=places/type=place/change_type={o['change_type']}/"
        if (not isinstance(key,str) or not key.startswith(prefix) or key in seen
                or not re.fullmatch(r'[A-Za-z0-9_./=\-]+\.parquet',key)
                or '..' in key or '/' in key[len(prefix):]):
            raise ValueError('Repeated or invalid source object')
        seen.add(key)
        size=positive_int(o['size'],'object size')
        fl=positive_int(o['footer_length'],'footer length')
        if fl>MAX_FOOTER or size-fl-8<4:
            raise ValueError('Invalid footer length')
        groups=o['row_groups']
        if not isinstance(groups,list) or len(groups)>20_000:
            raise ValueError('Unbounded row groups')
        positive_int(o['rows'],'row count',zero=True)
        spans=[]
        for g in groups:
            positive_int(g['rows'],'row group count')
            if not isinstance(g['columns'],list) or len(g['columns']) != len(COLUMNS):
                raise ValueError('Incomplete changelog projection')
            if {c['path'] for c in g['columns']} != COLUMNS:
                raise ValueError('Duplicate or unknown projected column')
            for c in g['columns']:
                n=positive_int(c['compressed_bytes'],'compressed size')
                start=positive_int(c['offset'],'column offset')
                if start<4 or start+n>size-fl-8:
                    raise ValueError('Column intersects header/footer or escapes object')
                spans.append((start,start+n))
        spans.sort()
        if any(b[0]<a[1] for a,b in zip(spans,spans[1:])):
            raise ValueError('Overlapping column chunks')
        if sum(g['rows'] for g in groups)!=o['rows']:
            raise ValueError('Metadata row counts disagree')


def _interval(col, *, string=False):
    s=col.get('statistics')
    if not isinstance(s,dict) or type(s.get('null_count')) is not int or s['null_count'] != 0:
        return None
    lo,hi=s.get('min'),s.get('max')
    if string:
        if (s.get('order')!='UTF8_BYTEWISE' or col.get('physical_type')!='BYTE_ARRAY'
                or not isinstance(lo,str) or not isinstance(hi,str)):
            return None
        lo,hi=lo.encode('utf-8'),hi.encode('utf-8')
    elif (s.get('order')!='NUMERIC' or col.get('physical_type') not in {'FLOAT','DOUBLE'}
            or type(lo) not in {int,float} or type(hi) not in {int,float}
            or not isfinite(lo) or not isfinite(hi)):
        return None
    return (lo,hi) if lo<=hi else None


def plan_cost(objects, ids, bounds, *, inventory_complete=False):
    """Estimate whole-column-chunk I/O, with strict separation of query scopes.

    Finite-coordinate bbox predicates only. Unknown/null/NaN statistics retain
    a row group. Metadata overlap is a candidate, not evidence that an ID exists.
    """
    validate_objects(objects)
    if type(inventory_complete) is not bool:
        raise ValueError('Inventory completeness must be explicit')
    if not isinstance(ids,list) or not ids or len(ids)>100_000 or len(ids)!=len(set(ids)):
        raise ValueError('Exact unique query IDs required')
    try:
        if any(not isinstance(r,str) or str(UUID(r))!=r for r in ids):
            raise ValueError('Noncanonical query ID')
    except (AttributeError,TypeError):
        raise ValueError('Noncanonical query ID') from None
    wanted=sorted(r.encode('ascii') for r in ids)
    if not isinstance(bounds,dict) or not bounds:
        raise ValueError('Explicit finite geographic boxes required')
    for box in bounds.values():
        if (not isinstance(box,(list,tuple)) or len(box)!=4
                or any(type(x) not in {int,float} or not isfinite(x) for x in box)
                or not -180<=box[0]<box[2]<=180 or not -90<=box[1]<box[3]<=90):
            raise ValueError('Invalid geographic box')
    policies={name:Counter(candidate_groups=0,projected_chunk_bytes=0,candidate_rows=0,
                           id_chunk_bytes=0,unknown_statistics_groups=0)
              for name in ('no_pruning','bbox','id_union','bbox_and_id')}
    by_partition={}
    lost=0
    for o in sorted(objects,key=lambda o:o['key']):
        part=o['release']+'/'+o['change_type']
        partition=by_partition.setdefault(part,Counter(objects=0,groups=0,bbox_groups=0,id_groups=0))
        partition['objects']+=1
        for g in o['row_groups']:
            cs={c['path']:c for c in g['columns']}
            spatial={k:_interval(cs['bbox.'+k]) for k in ('xmin','xmax','ymin','ymax')}
            spatial_unknown=any(v is None for v in spatial.values())
            bbox_keep=spatial_unknown or any(
                spatial['xmin'][0]<=box[2] and spatial['xmax'][1]>=box[0]
                and spatial['ymin'][0]<=box[3] and spatial['ymax'][1]>=box[1]
                for box in bounds.values())
            ii=_interval(cs['id'],string=True)
            pos=bisect_left(wanted,ii[0]) if ii else 0
            id_keep=ii is None or (pos<len(wanted) and wanted[pos]<=ii[1])
            lost+=int(not bbox_keep and id_keep)
            partition.update(groups=1,bbox_groups=int(bbox_keep),id_groups=int(id_keep))
            for name,keep,unknown in (
                ('no_pruning',True,False),('bbox',bbox_keep,spatial_unknown),
                ('id_union',id_keep,ii is None),('bbox_and_id',bbox_keep and id_keep,spatial_unknown or ii is None)):
                if keep:
                    policies[name].update(candidate_groups=1,candidate_rows=g['rows'],
                        projected_chunk_bytes=sum(c['compressed_bytes'] for c in cs.values()),
                        id_chunk_bytes=cs['id']['compressed_bytes'])
                policies[name]['unknown_statistics_groups']+=int(unknown)
    for name,p in policies.items():
        p['complete_for_id_union']=inventory_complete and name in {'no_pruning','id_union'}
    return {'study':'KEP-DATA-014','status':'METADATA_COMPLETE' if inventory_complete else 'PARTIAL_INVENTORY',
        'consumer_publish':False,'metadata_objects':len(objects),
        'metadata_row_groups':sum(len(o['row_groups']) for o in objects),
        'metadata_source_rows':sum(o['rows'] for o in objects),
        'source_object_bytes':sum(o['size'] for o in objects),
        'query_id_count':len(ids),'query_ids_sha256':sha256(canonical(sorted(ids))).hexdigest(),
        'bounds':{k:list(v) for k,v in sorted(bounds.items())},
        'policies':{k:dict(v) for k,v in policies.items()},
        'by_partition':{k:dict(v) for k,v in sorted(by_partition.items())},
        'bbox_excluded_but_id_candidate_groups':lost,
        'cost_definition':'sum of projected compressed column chunks, not measured HTTP transfer; headers, indexes, readahead and retries excluded',
        'metadata_matches_are_not_observed_ids':True,'same_publisher_not_independent_evidence':True,
        'official_event_rows_read':0,'data_page_bytes_read':0,'matched_ids':None,
        'membership_agreement_fraction':None,'business_event_accuracy':None,
        'can_claim_business_openings_or_closures':False}


def load_capture(path, expected_sha256):
    """Validate immutable archive, normalized metadata and exact footer member hashes."""
    p=Path(path)
    if (not isinstance(expected_sha256,str) or not re.fullmatch('[a-f0-9]{64}',expected_sha256)
            or p.is_symlink() or not p.is_file() or not 0<p.stat().st_size<=MAX_BODY):
        raise ValueError('Missing or unsafe metadata capture')
    raw=p.read_bytes()
    if sha256(raw).hexdigest()!=expected_sha256:
        raise ValueError('Metadata archive SHA-256 mismatch')
    with zipfile.ZipFile(p) as z:
        entries=z.infolist();names=[i.filename for i in entries]
        if (len(names)!=len(set(names)) or len(names)>300 or sum(i.file_size for i in entries)>32*1024*1024
                or 'manifest.json' not in names or any(i.flag_bits&1 for i in entries)):
            raise ValueError('Unsafe metadata ZIP members')
        manifest_raw=z.read('manifest.json');m=json.loads(manifest_raw)
        if (canonical(m)!=manifest_raw or m['format']!='KEP-GERS-FOOTERS-v1'
                or m['origin']!='captured_public_footer_metadata' or m['status']!='COMPLETE_METADATA'
                or m['data_page_bytes_read']!=0 or m['official_event_rows_read']!=0):
            raise ValueError('Incomplete or incorrectly identified metadata study')
        expected={'manifest.json'}
        for o in m['objects']:
            fn=o['footer_member'];expected.add(fn)
            if not re.fullmatch(r'footers/[a-f0-9]{64}\.bin',fn):
                raise ValueError('Unsafe footer member')
            data=z.read(fn)
            if sha256(data).hexdigest()!=o['footer_sha256'] or len(data)!=o['footer_length']+8:
                raise ValueError('Footer integrity mismatch')
            footer_span(data[-8:],o['size'])
        if set(names)!=expected:
            raise ValueError('Unexpected or missing metadata members')
    validate_objects(m['objects'])
    return m
