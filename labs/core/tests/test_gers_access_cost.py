"""DATA-014 test-first contracts. All metadata here is synthetic, not GERS events."""
import copy
import struct
import unittest
from kepcore.gers_access_cost import (
    BodyBudget, footer_span, validate_range, plan_cost, validate_objects,
)

IDS=['00000000-0000-0000-0000-000000000005']
BOXES={'synthetic_cell':[28.,40.,30.,42.]}


def group(x=29., y=41., lo='00000000-0000-0000-0000-000000000001', hi='00000000-0000-0000-0000-000000000009'):
    cols=[]
    values={'id':(lo,hi),'bbox.xmin':(x,x),'bbox.xmax':(x,x),
            'bbox.ymin':(y,y),'bbox.ymax':(y,y),'columns_changed.list.element':(None,None)}
    for i,(path,(low,high)) in enumerate(values.items()):
        cols.append({'path':path,'physical_type':'BYTE_ARRAY' if not path.startswith('bbox.') else 'FLOAT',
            'compressed_bytes':100,'offset':4+i*100,'statistics':
            {'min':low,'max':high,'null_count':0,'order':'UTF8_BYTEWISE' if path=='id' else 'NUMERIC'}})
    return {'rows':10,'columns':cols}


def obj(g=None):
    return {'key':'changelog/2026-09-23.0/theme=places/type=place/change_type=added/part-000.parquet',
        'release':'2026-09-23.0','change_type':'added','size':10000,'etag':'"abc"',
        'footer_length':1000,'rows':10,'row_groups':[group() if g is None else g]}


class FooterContracts(unittest.TestCase):
    def test_footer_range_excludes_data_and_trailer(self):
        self.assertEqual(footer_span(struct.pack('<I',100)+b'PAR1',1000),(892,991))
    def test_bad_magic(self):
        with self.assertRaises(ValueError):footer_span(struct.pack('<I',100)+b'PARE',1000)
    def test_truncated_trailer(self):
        with self.assertRaises(ValueError):footer_span(b'PAR1',1000)
    def test_zero_footer(self):
        with self.assertRaises(ValueError):footer_span(b'\0'*4+b'PAR1',1000)
    def test_footer_overlaps_header(self):
        with self.assertRaises(ValueError):footer_span(struct.pack('<I',999)+b'PAR1',1000)
    def test_footer_cap_before_network(self):
        with self.assertRaises(ValueError):footer_span(struct.pack('<I',3_000_000)+b'PAR1',4_000_000)
    def test_budget_zero_is_not_unlimited(self):
        with self.assertRaises(ValueError):BodyBudget(0)
    def test_budget_reservation_blocks_overspend(self):
        b=BodyBudget(10);b.reserve(7)
        with self.assertRaises(ValueError):b.reserve(4)
        self.assertEqual(b.accounted_bytes,7)
    def test_failed_read_stays_conservatively_charged(self):
        b=BodyBudget(10);b.reserve(10)
        with self.assertRaises(ValueError):b.reserve(1)
    def test_budget_bool_rejected(self):
        with self.assertRaises(ValueError):BodyBudget(True)
    def test_exact_range(self):
        validate_range(206,{'Content-Range':'bytes 4-7/100','Content-Length':'4','ETag':'"a"'},4,7,100,'"a"',b'abcd')
    def test_range_protocol_fail_closed(self):
        for status,cr,etag,body in [(200,'bytes 4-7/100','"a"',b'abcd'),(206,'bytes 5-8/100','"a"',b'abcd'),
                (206,'bytes 4-7/101','"a"',b'abcd'),(206,'bytes 4-7/100','"b"',b'abcd'),(206,'bytes 4-7/100','"a"',b'abc')]:
            with self.subTest(status=status,cr=cr,etag=etag,body=body),self.assertRaises(ValueError):
                validate_range(status,{'Content-Range':cr,'Content-Length':'4','ETag':etag},4,7,100,'"a"',body)


class CostContracts(unittest.TestCase):
    def plan(self,objects=None,complete=True):
        return plan_cost([obj()] if objects is None else objects,IDS,BOXES,inventory_complete=complete)
    def test_overlap_kept_and_no_event_claim(self):
        r=self.plan();self.assertEqual(r['policies']['bbox']['candidate_groups'],1)
        self.assertEqual(r['policies']['id_union']['projected_chunk_bytes'],600)
        self.assertEqual(r['official_event_rows_read'],0);self.assertIsNone(r['membership_agreement_fraction'])
    def test_outside_bbox_is_still_needed_by_id(self):
        r=self.plan([obj(group(x=-70.))])
        self.assertEqual(r['policies']['bbox']['candidate_groups'],0)
        self.assertEqual(r['policies']['id_union']['candidate_groups'],1)
        self.assertEqual(r['bbox_excluded_but_id_candidate_groups'],1)
        self.assertFalse(r['policies']['bbox']['complete_for_id_union'])
    def test_id_interval_proves_exclusion_not_presence(self):
        r=self.plan([obj(group(lo='f',hi='ff'))]);self.assertEqual(r['policies']['id_union']['candidate_groups'],0)
        self.assertIsNone(r['matched_ids'])
    def test_boundary_is_inclusive(self):
        self.assertEqual(self.plan([obj(group(x=30.))])['policies']['bbox']['candidate_groups'],1)
    def test_missing_stats_kept(self):
        g=group(x=-70.);g['columns'][1]['statistics']=None
        self.assertEqual(self.plan([obj(g)])['policies']['bbox']['candidate_groups'],1)
    def test_null_stats_not_assumed_zero(self):
        g=group(x=-70.);g['columns'][1]['statistics']['null_count']=None
        self.assertEqual(self.plan([obj(g)])['policies']['bbox']['candidate_groups'],1)
    def test_nan_bounds_never_prune(self):
        g=group(x=-70.);g['columns'][1]['statistics']['min']=float('nan')
        self.assertEqual(self.plan([obj(g)])['policies']['bbox']['candidate_groups'],1)
    def test_unknown_id_order_never_prunes(self):
        g=group(lo='f',hi='ff');g['columns'][0]['statistics']['order']='UNKNOWN'
        self.assertEqual(self.plan([obj(g)])['policies']['id_union']['candidate_groups'],1)
    def test_partial_inventory_not_whole_dataset(self):
        r=self.plan(complete=False);self.assertEqual(r['status'],'PARTIAL_INVENTORY')
        self.assertFalse(r['policies']['id_union']['complete_for_id_union'])
    def test_duplicate_object_rejected(self):
        with self.assertRaises(ValueError):self.plan([obj(),obj()])
    def test_duplicate_column_rejected(self):
        g=group();g['columns'].append(copy.deepcopy(g['columns'][0]))
        with self.assertRaises(ValueError):self.plan([obj(g)])
    def test_invalid_compressed_size_rejected(self):
        for v in [-1,True,float('nan')]:
            g=group();g['columns'][0]['compressed_bytes']=v
            with self.subTest(v=v),self.assertRaises(ValueError):self.plan([obj(g)])
    def test_chunk_overlapping_footer_rejected(self):
        g=group();g['columns'][0]['offset']=9000
        with self.assertRaises(ValueError):self.plan([obj(g)])
    def test_overlapping_chunks_rejected(self):
        g=group();g['columns'][1]['offset']=4
        with self.assertRaises(ValueError):self.plan([obj(g)])
    def test_wrong_release_or_partition_rejected(self):
        o=obj();o['release']='2026-10-21.0'
        with self.assertRaises(ValueError):self.plan([o])
    def test_missing_id_column_rejected(self):
        g=group();g['columns']=g['columns'][1:]
        with self.assertRaises(ValueError):self.plan([obj(g)])
    def test_no_fake_row_counts(self):
        o=obj();o['rows']=11
        with self.assertRaises(ValueError):self.plan([o])
    def test_invalid_ids_and_bounds_rejected(self):
        for ids,boxes in [([],BOXES),(['not-id'],BOXES),(IDS,{}),(IDS,{'bad':[30.,42.,28.,40.]})]:
            with self.subTest(ids=ids,boxes=boxes),self.assertRaises(ValueError):plan_cost([obj()],ids,boxes)
    def test_deterministic_and_immutable(self):
        o=obj();old=copy.deepcopy(o);a=self.plan([o]);b=self.plan([o])
        self.assertEqual(a,b);self.assertEqual(o,old)
    def test_counts_are_costs_not_accuracy(self):
        r=self.plan();self.assertFalse(r['consumer_publish']);self.assertIsNone(r['business_event_accuracy'])
        self.assertEqual(r['data_page_bytes_read'],0)
        self.assertIn('not measured HTTP transfer',r['cost_definition'])

if __name__=='__main__':unittest.main()
