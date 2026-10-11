"""DATA-017: mock Compact Thrift and real pinned original footer evidence."""
import json, unittest, tempfile
from pathlib import Path
from hashlib import sha256
from unittest.mock import patch
from kepcore.gers_access_cost import DATA_DIR, PINNED_ZIP_SHA256, load_capture
from kepcore.gers_index_audit import CompactFooter, evaluate, audit_index_capabilities
from scripts.audit_gers_index import stable_projection

def u(n):
    out=bytearray()
    while n>=128:
        out.append((n&127)|128);n>>=7
    out.append(n)
    return bytes(out)
def i(n):return u(n*2 if n>=0 else -2*n-1)
def binary(x):
    raw=x.encode();return u(len(raw))+raw
def arr(typ,values):
    n=len(values)
    return bytes([((n if n<15 else 15)<<4)|typ])+(u(n) if n>=15 else b'')+b''.join(values)
def struct(items):
    buf=bytearray();previous=0
    for fid,typ,v in items:
        delta=fid-previous
        buf.extend(bytes([(delta<<4)|typ]) if 0<delta<=15 else bytes([typ])+i(fid))
        buf.extend(v);previous=fid
    return bytes(buf)+b'\x00'
def fixture(colidx=False, offidx=False, bloom=False,sort=False,orphan=False,path='id'):
    meta=[(3,9,arr(8,[binary(x) for x in path.split('.')])),(9,6,i(80))]
    if bloom:meta.extend([(14,6,i(400)),(15,5,i(64))])
    col=[(3,12,struct(meta))]
    if offidx:col.extend([(4,6,i(100)),(5,5,i(20))])
    if colidx:
        col.append((6,6,i(120)))
        if not orphan:col.append((7,5,i(20)))
    group=[(1,9,arr(12,[struct(col)]))]
    if sort:group.append((4,9,arr(12,[struct([(1,5,i(0))])])))
    return struct([(1,5,i(2)),(4,9,arr(12,[struct(group)]))])

class SyntheticIndexContracts(unittest.TestCase):
    def test_unindexed_not_interpreted_as_indexed(self):
        d=CompactFooter(fixture()).file_metadata()[0]['columns'][0]
        self.assertIsNone(d['column_index_offset']);self.assertIsNone(d['offset_index_offset'])
        self.assertIsNone(d['bloom_offset']);self.assertEqual(d['path'],'id')
    def test_detect_true_page_index_pair(self):
        d=CompactFooter(fixture(colidx=True,offidx=True)).file_metadata()[0]['columns'][0]
        self.assertEqual((d['column_index_offset'],d['column_index_length']),(120,20))
        self.assertEqual((d['offset_index_offset'],d['offset_index_length']),(100,20))
    def test_detect_bloom_pointer_but_not_membership(self):
        d=CompactFooter(fixture(bloom=True)).file_metadata()[0]['columns'][0]
        self.assertEqual(d['bloom_offset'],400)
    def test_reject_orphan_index(self):
        with self.assertRaises(ValueError):CompactFooter(fixture(colidx=True,orphan=True)).file_metadata()
    def test_nested_column_path(self):
        self.assertEqual(CompactFooter(fixture(path='bbox.xmin')).file_metadata()[0]['columns'][0]['path'],'bbox.xmin')
    def test_sort_declaration_not_page_index(self):
        d=CompactFooter(fixture(sort=True)).file_metadata()[0]
        self.assertTrue(d['declares_sorting_columns']);self.assertIsNone(d['columns'][0]['column_index_offset'])
    def test_trailing_bytes_rejected(self):
        with self.assertRaises(ValueError):CompactFooter(fixture()+b'X').file_metadata()
    def test_truncation_rejected(self):
        with self.assertRaises(ValueError):CompactFooter(fixture()[:-2]).file_metadata()
    def test_oversize_rejected(self):
        with self.assertRaises(ValueError):CompactFooter(b'0'*(2*1024*1024+1))
    def test_oversized_varint_rejected(self):
        with self.assertRaises(ValueError):CompactFooter(b'\x15'+b'\xff'*12).file_metadata()

class PinnedOriginalFooterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=evaluate()
    def test_real_counts(self):
        t=self.r['totals']
        self.assertEqual((t['object_count'],t['row_groups'],t['column_chunks'],t['id_column_chunks']),(128,1244,7464,1244))
    def test_real_index_absence(self):
        for k in ('page_column_indexes','page_offset_indexes','bloom_filters',
                  'id_page_column_indexes','id_page_offset_indexes','id_bloom_filters',
                  'id_full_index_pairs','declared_sorted_row_groups'):
            with self.subTest(k=k):self.assertEqual(self.r['totals'][k],0)
    def test_costs_and_prior_16mib_cap(self):
        self.assertEqual(self.r['non_indexed_id_scan_bytes_all_release_paths'],3323200846)
        self.assertEqual(self.r['non_indexed_id_scan_bytes_one_release'],1661600423)
        self.assertEqual(self.r['non_indexed_id_scan_bytes_membership_one_release'],203288875)
        self.assertFalse(self.r['membership_one_release_fits_prior_budget'])
    def test_existing_archives_untouched_and_no_network(self):
        self.assertEqual(sha256((DATA_DIR/'footers.zip').read_bytes()).hexdigest(),PINNED_ZIP_SHA256)
        with patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('NETWORK')):
            self.assertEqual(evaluate(),self.r)
    def test_reject_tampered_manifest(self):
        m=load_capture(DATA_DIR/'footers.zip',PINNED_ZIP_SHA256)
        m['objects'][0]['etag']='bad'
        with self.assertRaises(ValueError):audit_index_capabilities(m,DATA_DIR/'footers.zip')
    def test_never_claims_event_or_business_truth(self):
        for k in ('publisher_changelog_comparison_baseline','official_membership_agreement_fraction','physical_business_openings','physical_business_closures'):
            self.assertIsNone(self.r[k])
        self.assertFalse(self.r['consumer_publish']);self.assertFalse(self.r['all_id_events_observed'])
        self.assertEqual(self.r['data_page_response_bytes'],0)
    def test_golden_report(self):
        p=Path(__file__).resolve().parents[1]/'reports/KEP_DATA_017_INDEX_AUDIT.json'
        self.assertEqual(stable_projection(self.r),json.loads(p.read_text()))
if __name__=='__main__':unittest.main()
