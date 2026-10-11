"""DATA-017: read original pinned Parquet footers, never pretend indexes exist.

Strict, stdlib-only subset of Thrift Compact Protocol. The byte source is the
unchanged DATA-014 original metadata archive, not any live event rows.
"""
from __future__ import annotations
from collections import defaultdict
from hashlib import sha256
from pathlib import Path
import zipfile

from .gers_access_cost import DATA_DIR, PINNED_ZIP_SHA256, load_capture
from .gers_region_probe import PINNED_MANIFEST_SHA256
from .overture_places import canonical

STOP, TRUE, FALSE, BYTE, I16, I32, I64, DOUBLE, BINARY, LIST, SET, MAP, STRUCT = range(13)
CAP = 2 * 1024 * 1024
ID_SHA = '38b248b344cb66a87228c713e74e55ec5f24124f383a3e2c077fc11ddfc73804'

class CompactFooter:
    """Bounded generic Compact Thrift reader. Fail closed on malformed metadata."""
    def __init__(self, data):
        if type(data) is not bytes or not 0 < len(data) <= CAP:
            raise ValueError('Invalid Parquet footer length')
        self.buf=data;self.pos=0

    def take(self, n):
        if type(n) is not int or n<0 or n>len(self.buf)-self.pos:
            raise ValueError('Truncated or oversized Thrift field')
        old=self.pos;self.pos+=n
        return self.buf[old:self.pos]

    def byte(self):return self.take(1)[0]

    def varint(self):
        result=0
        for shift in range(0,70,7):
            b=self.byte()
            if shift==63 and b>1:raise ValueError('64-bit Thrift varint overflow')
            result|=(b&127)<<shift
            if not b&128:return result
        raise ValueError('Unbounded Thrift varint')

    def integer(self):
        n=self.varint()
        return (n>>1)^-(n&1)

    def field(self, previous):
        h=self.byte()
        if h==STOP:return STOP,0
        typ=h&15;delta=h>>4
        fid=previous+delta if delta else self.integer()
        if typ==STOP or fid<=previous:
            raise ValueError('Invalid or reordered Thrift field')
        return typ,fid

    def list_head(self):
        h=self.byte();size=h>>4;typ=h&15
        if size==15:size=self.varint()
        if size>100000 or not 1<=typ<=12:
            raise ValueError('Bad Thrift list')
        return typ,size

    def skip(self,typ,depth=0,in_container=False):
        if depth>24:raise ValueError('Nested Thrift depth exceeded')
        if typ in (TRUE,FALSE):
            if in_container and self.byte() not in (TRUE,FALSE):
                raise ValueError('Invalid bool value')
        elif typ==BYTE:self.take(1)
        elif typ in (I16,I32,I64):self.varint()
        elif typ==DOUBLE:self.take(8)
        elif typ==BINARY:self.take(self.varint())
        elif typ in (LIST,SET):
            t,n=self.list_head()
            for _ in range(n):self.skip(t,depth+1,True)
        elif typ==MAP:
            n=self.varint()
            if n>100000:raise ValueError('Too many Thrift map items')
            if n:
                types=self.byte();kt=types>>4;vt=types&15
                for _ in range(n):
                    self.skip(kt,depth+1,True);self.skip(vt,depth+1,True)
        elif typ==STRUCT:
            prev=0
            while True:
                t,fid=self.field(prev)
                if t==STOP:break
                self.skip(t,depth+1);prev=fid
        else:raise ValueError('Unsupported compact Thrift type')

    def column_metadata(self):
        prev=0;data={'path':None,'bloom_offset':None,'bloom_length':None}
        while True:
            t,fid=self.field(prev)
            if t==STOP:break
            if fid==3:
                if t!=LIST or data['path'] is not None:
                    raise ValueError('Invalid Parquet column path')
                typ,n=self.list_head()
                if typ!=BINARY or not 0<n<=8:raise ValueError('Invalid path size')
                parts=[]
                for _ in range(n):
                    s=self.take(self.varint()).decode('utf-8')
                    if not 0<len(s)<=100:raise ValueError('Bad Parquet path token')
                    parts.append(s)
                data['path']='.'.join(parts)
            elif fid in (14,15):
                if t!=(I64 if fid==14 else I32):raise ValueError('Invalid Bloom pointer type')
                data['bloom_offset' if fid==14 else 'bloom_length']=self.integer()
            else:self.skip(t)
            prev=fid
        return data

    def column(self):
        prev=0
        d={'offset_index_offset':None,'offset_index_length':None,
           'column_index_offset':None,'column_index_length':None,
           'bloom_offset':None,'bloom_length':None}
        lookup={4:'offset_index_offset',5:'offset_index_length',
                6:'column_index_offset',7:'column_index_length'}
        found=False
        while True:
            typ,fid=self.field(prev)
            if typ==STOP:break
            if fid==3:
                if found or typ!=STRUCT:raise ValueError('Invalid Parquet ColumnMetaData')
                d.update(self.column_metadata());found=True
            elif fid in lookup:
                if typ!=(I64 if fid in (4,6) else I32):raise ValueError('Invalid page-index type')
                d[lookup[fid]]=self.integer()
            else:self.skip(typ)
            prev=fid
        if not found or d.get('path') is None:raise ValueError('Column metadata/path absent')
        for a,b in (('column_index_offset','column_index_length'),
                    ('offset_index_offset','offset_index_length')):
            if (d[a] is None)!=(d[b] is None):raise ValueError('Incomplete page-index extent')
            if d[a] is not None and (d[a]<4 or d[b]<=0):raise ValueError('Unsafe page-index extent')
        if (d['bloom_offset'] is not None and d['bloom_offset']<4 or
            d['bloom_length'] is not None and d['bloom_length']<=0):
            raise ValueError('Unsafe bloom extent')
        return d

    def row_group(self):
        prev=0;columns=None;sorted_declared=False
        while True:
            t,fid=self.field(prev)
            if t==STOP:break
            if fid==1:
                if columns is not None or t!=LIST:raise ValueError('Missing column list')
                item,n=self.list_head()
                if item!=STRUCT or not 1<=n<=100:raise ValueError('Invalid number of columns')
                columns=[self.column() for _ in range(n)]
            elif fid==4:
                if t!=LIST:raise ValueError('Invalid sorting-columns field')
                item,n=self.list_head()
                if item!=STRUCT:raise ValueError('Invalid sorting-column type')
                sorted_declared = sorted_declared or n>0
                for _ in range(n):self.skip(STRUCT)
            else:self.skip(t)
            prev=fid
        if columns is None:raise ValueError('Row group has no columns')
        return {'columns':columns,'declares_sorting_columns':sorted_declared}

    def file_metadata(self):
        prev=0;groups=None
        while True:
            t,fid=self.field(prev)
            if t==STOP:break
            if fid==4:
                if t!=LIST or groups is not None:raise ValueError('Bad FileMetaData row groups')
                item,n=self.list_head()
                if item!=STRUCT or not 0<n<=20000:raise ValueError('Bad row-group list')
                groups=[self.row_group() for _ in range(n)]
            else:self.skip(t)
            prev=fid
        if groups is None or self.pos!=len(self.buf):
            raise ValueError('Missing row groups or trailing bytes')
        return groups

def audit_index_capabilities(manifest,archive):
    if (not isinstance(manifest,dict) or
            sha256(canonical(manifest)).hexdigest()!=PINNED_MANIFEST_SHA256):
        raise ValueError('Noncanonical or foreign DATA-014 capture')
    totals={k:0 for k in ('object_count','row_groups','column_chunks','id_column_chunks',
        'page_column_indexes','page_offset_indexes','bloom_filters',
        'id_page_column_indexes','id_page_offset_indexes','id_bloom_filters',
        'id_full_index_pairs','declared_sorted_row_groups')}
    names=tuple(totals)[4:-1]
    partitions=defaultdict(lambda:{k:0 for k in tuple(totals)[1:]} | {
        'id_chunks_compressed_bytes':0,'six_columns_compressed_bytes':0})
    with zipfile.ZipFile(archive) as z:
        for obj in manifest['objects']:
            raw=z.read(obj['footer_member'])
            if (len(raw)!=obj['footer_length']+8 or raw[-4:]!=b'PAR1' or
                sha256(raw).hexdigest()!=obj['footer_sha256']):
                raise ValueError('Original footer member integrity mismatch')
            groups=CompactFooter(raw[:-8]).file_metadata()
            if len(groups)!=len(obj['row_groups']):raise ValueError('Raw/normalized group mismatch')
            name=obj['release']+'/'+obj['change_type'];p=partitions[name]
            totals['object_count']+=1
            for group,normalized in zip(groups,obj['row_groups']):
                if len(group['columns'])!=len(normalized['columns']):
                    raise ValueError('Raw/normalized column count mismatch')
                totals['row_groups']+=1;p['row_groups']+=1
                sort=int(group['declares_sorting_columns'])
                totals['declared_sorted_row_groups']+=sort;p['declared_sorted_row_groups']+=sort
                for col,norm in zip(group['columns'],normalized['columns']):
                    if col['path']!=norm['path']:
                        raise ValueError('Raw/normalized Parquet column path mismatch')
                    totals['column_chunks']+=1;p['column_chunks']+=1
                    flags={'page_column_indexes':col['column_index_offset'] is not None,
                        'page_offset_indexes':col['offset_index_offset'] is not None,
                        'bloom_filters':col['bloom_offset'] is not None}
                    for k,v in flags.items():totals[k]+=int(v);p[k]+=int(v)
                    p['six_columns_compressed_bytes']+=norm['compressed_bytes']
                    if norm['path']=='id':
                        totals['id_column_chunks']+=1;p['id_column_chunks']+=1
                        p['id_chunks_compressed_bytes']+=norm['compressed_bytes']
                        for k,v in (('id_page_column_indexes',flags['page_column_indexes']),
                            ('id_page_offset_indexes',flags['page_offset_indexes']),
                            ('id_bloom_filters',flags['bloom_filters']),
                            ('id_full_index_pairs',flags['page_column_indexes'] and flags['page_offset_indexes'])):
                            totals[k]+=int(v);p[k]+=int(v)
    if (len(partitions)!=8 or totals['object_count']!=128 or totals['row_groups']!=1244 or
        totals['column_chunks']!=7464 or
        any(p['id_column_chunks']!=p['row_groups'] for p in partitions.values())):
        raise ValueError('Incomplete original GERS inventory')
    membership=sum(p['id_chunks_compressed_bytes'] for k,p in partitions.items()
                   if k in ('2026-09-23.0/added','2026-09-23.0/removed'))
    single=sum(p['id_chunks_compressed_bytes'] for k,p in partitions.items()
               if k.startswith('2026-09-23.0/'))
    allpaths=sum(p['id_chunks_compressed_bytes'] for p in partitions.values())
    prior=16*1024*1024
    return {'study':'KEP-DATA-017','origin':'pinned_real_GERS_Parquet_footers',
        'source_footer_zip_sha256':PINNED_ZIP_SHA256,
        'covered_release_paths':['2026-09-23.0','2026-09-23.1'],
        'totals':totals,'by_partition':dict(sorted(partitions.items())),
        'non_indexed_id_scan_bytes_all_release_paths':allpaths,
        'non_indexed_id_scan_bytes_one_release':single,
        'non_indexed_id_scan_bytes_membership_one_release':membership,
        'id_page_index_usable':False if totals['id_full_index_pairs']==0 else None,
        'id_bloom_filter_usable':False if totals['id_bloom_filters']==0 else None,
        'id_union_query_sha256':ID_SHA,
        'existing_approved_source_body_budget_bytes':prior,
        'membership_one_release_fits_prior_budget':membership<=prior,
        'full_id_one_release_fits_prior_budget':single<=prior,
        'all_id_events_observed':False,'event_rows_read':0,
        'data_page_response_bytes':0,'http_requests':0,
        'index_presence_is_not_row_membership':True,
        'publisher_changelog_comparison_baseline':None,
        'official_membership_agreement_fraction':None,
        'physical_business_openings':None,'physical_business_closures':None,
        'cost_is_sum_of_column_chunk_metadata_not_observed_transfer':True,
        'consumer_publish':False}

def evaluate():
    archive=DATA_DIR/'footers.zip'
    m=load_capture(archive,PINNED_ZIP_SHA256)
    return audit_index_capabilities(m,archive)
