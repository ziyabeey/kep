"""KEP-DATA-001 synthetic contract tests. No Overture feature is fabricated as real."""
from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import copy
import json
import math
import subprocess
import sys
import unittest

from kepcore.overture_places import (
    PILOT, canonical, normalize_feature, ingest_geojson, potential_duplicates,
    pilot_audit_plan, check_release, valid_stac_catalog, metres_between
)
from benchmarks.overture_places_eval import example, run

ROOT=Path(__file__).resolve().parents[1]
CELLS=sorted(PILOT)
RELEASE='2026-09-23.1'


def as_geojson(records):
    return {'type':'FeatureCollection','features':records}


def fixture_file(path, features):
    path.write_text(json.dumps(as_geojson(features),ensure_ascii=False),encoding='utf-8')


class SchemaTests(unittest.TestCase):
    def setUp(self):
        self.cell=CELLS[0]
        self.feature=example(1,self.cell,'Örnek Kafe','cafe')

    def test_accept_minimal_v2(self):
        p=normalize_feature(self.feature,cell=self.cell)
        self.assertEqual(p['name'],'Örnek Kafe');self.assertEqual(p['taxonomy_primary'],'cafe')
        self.assertFalse(p['consumer_verified'])
        self.assertIsNone(p['open_now']);self.assertIsNone(p['active_event'])
        self.assertIsNone(p['administrative_district'])
    def test_opt_in_rich_pii_not_copied(self):
        feat=copy.deepcopy(self.feature)
        feat['properties'].update({'phones':['+901234'],'emails':['hello@example.org'],
            'socials':['https://social.example/1'],'websites':['https://example.org'],
            'opening_hours':{'Mon':'9-5'},'reviews':['review']})
        text=json.dumps(normalize_feature(feat,cell=self.cell))
        for secret in ['+901234','hello@example.org','social.example','review','9-5']:
            self.assertNotIn(secret,text)
    def test_invalid_shape(self):
        for geom in (None,{}, {'type':'Polygon','coordinates':[]}, {'type':'Point','coordinates':['a',3]},
                     {'type':'Point','coordinates':[True,41]}, {'type':'Point','coordinates':[200,41]},
                     {'type':'Point','coordinates':[float('nan'),41]}):
            x=copy.deepcopy(self.feature);x['geometry']=geom
            with self.subTest(geom=str(geom)),self.assertRaisesRegex(ValueError,'invalid_geometry'):
                normalize_feature(x,cell=self.cell)
    def test_out_of_bbox_rejected(self):
        x=copy.deepcopy(self.feature)
        x['geometry']['coordinates']=[41.04,29.004]
        with self.assertRaisesRegex(ValueError,'outside_sampling_cell'):normalize_feature(x,cell=self.cell)
    def test_legacy_categories_fails(self):
        x=copy.deepcopy(self.feature);x['properties']['categories']={'primary':'cafe'}
        with self.assertRaisesRegex(ValueError,'obsolete_categories_schema'):normalize_feature(x,cell=self.cell)
    def test_missing_name_and_categories_unknown(self):
        x=copy.deepcopy(self.feature);x['properties'].pop('names');x['properties'].pop('taxonomy');x['properties'].pop('basic_category')
        r=normalize_feature(x,cell=self.cell)
        self.assertIsNone(r['name']);self.assertIsNone(r['taxonomy_primary'])
    def test_operating_status_open_not_open_now(self):
        x=copy.deepcopy(self.feature);x['properties']['operating_status']='open'
        r=normalize_feature(x,cell=self.cell)
        self.assertEqual(r['operating_status'],'open');self.assertIsNone(r['open_now'])
    def test_invalid_operating_status(self):
        x=copy.deepcopy(self.feature);x['properties']['operating_status']='open_now'
        with self.assertRaisesRegex(ValueError,'invalid_operating_status'):normalize_feature(x,cell=self.cell)
    def test_null_confidence_is_not_one(self):
        x=copy.deepcopy(self.feature);x['properties']['confidence']=None
        self.assertIsNone(normalize_feature(x,cell=self.cell)['confidence'])
    def test_invalid_confidence(self):
        for v in [True,-.2,1.1,float('inf'),float('nan'),'1']:
            x=copy.deepcopy(self.feature);x['properties']['confidence']=v
            with self.subTest(v=str(v)),self.assertRaisesRegex(ValueError,'invalid_confidence'):
                normalize_feature(x,cell=self.cell)
    def test_reject_wrong_thing(self):
        x=copy.deepcopy(self.feature);x['properties']['theme']='buildings'
        with self.assertRaisesRegex(ValueError,'not_a_place'):normalize_feature(x,cell=self.cell)
    def test_requires_id(self):
        x=copy.deepcopy(self.feature);x['properties']['id']='not-a-uuid'
        with self.assertRaisesRegex(ValueError,'invalid_id'):normalize_feature(x,cell=self.cell)
    def test_sources_strip_record_ids(self):
        x=copy.deepcopy(self.feature)
        x['properties']['sources']=[{'dataset':'meta','provider':'meta','license':'CDLA','record_id':'no-copy-recordid'}]
        r=normalize_feature(x,cell=self.cell)
        self.assertEqual(r['source_provenance'][0]['provider'],'meta')
        self.assertNotIn('no-copy-recordid',json.dumps(r))
    def test_point_distance_symmetry(self):
        a=normalize_feature(example(10,self.cell,'A','cafe'),cell=self.cell)
        b=normalize_feature(example(11,self.cell,'B','cafe',dx=.00010),cell=self.cell)
        self.assertAlmostEqual(metres_between(a,b),metres_between(b,a),places=8)
        self.assertGreater(metres_between(a,b),3)


class AcquisitionContractTests(unittest.TestCase):
    def test_release_version_validation(self):
        self.assertEqual(check_release(RELEASE),RELEASE)
        for bad in ['latest','2026-09-23.1/../../../','2026-13-23.1','2026-09-23','2026-09-23.1 && rm']:
            with self.subTest(bad=bad),self.assertRaises(ValueError):check_release(bad)
    def test_stac_pin_passes_exact(self):
        raw=json.dumps({'type':'Catalog','stac_version':'1.1.0','latest':RELEASE,
             'links':[{'rel':'child','href':'./2026-09-23.1/catalog.json','latest':True}]}).encode()
        self.assertEqual(valid_stac_catalog(raw,pinned=RELEASE)['stac_sha256'],sha256(raw).hexdigest())
    def test_stac_pin_mismatch_halts(self):
        raw=json.dumps({'type':'Catalog','stac_version':'1.1.0','latest':'2026-10-20.0',
             'links':[{'rel':'child','href':'./2026-10-20.0/catalog.json','latest':True}]}).encode()
        with self.assertRaisesRegex(ValueError,'pins'):valid_stac_catalog(raw,pinned=RELEASE)
    def test_stac_mismatch_latest_link(self):
        raw=json.dumps({'type':'Catalog','stac_version':'1.1.0','latest':RELEASE,'links':[]}).encode()
        with self.assertRaisesRegex(ValueError,'not linked'):valid_stac_catalog(raw,pinned=RELEASE)
    def test_stac_oversized_halts(self):
        with self.assertRaisesRegex(ValueError,'bounded'):valid_stac_catalog(b'x'*200001,pinned=RELEASE)
    def test_cli_default_no_network(self):
        p=subprocess.run([sys.executable,str(ROOT/'scripts/overture_istanbul.py')],cwd=ROOT,
                         capture_output=True,text=True,timeout=10)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertIn('offline_default',p.stdout)
    def test_cli_help_no_network(self):
        p=subprocess.run([sys.executable,str(ROOT/'scripts/overture_istanbul.py'),'--help'],cwd=ROOT,
                         capture_output=True,text=True,timeout=10)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertIn('--fetch',p.stdout)


class DatasetTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.paths={c:Path(self.tmp.name)/f'{c}.json' for c in CELLS}
        fixture_file(self.paths[CELLS[0]],[example(1,CELLS[0],'Kafe A','cafe'),example(2,CELLS[0],'Kafe A','cafe',dx=.00006)])
        fixture_file(self.paths[CELLS[1]],[example(3,CELLS[1],'Müze B','museum')])

    def ingest(self):return ingest_geojson(self.paths,pinned_release=RELEASE)
    def test_report_and_replay(self):
        a=self.ingest();b=self.ingest()
        self.assertEqual(a,b);self.assertEqual(a['audit']['accepted'],3)
        self.assertEqual(a['audit']['rows_read'],3)
        self.assertEqual(len(a['audit']['potential_duplicate_pairs']),1)
        self.assertEqual(a['audit']['claim_verified_place_count'],0)
    def test_duplicate_proposals_never_merge(self):
        d=self.ingest();self.assertEqual(len(d['normalized_places']),3)
        self.assertEqual(d['audit']['potential_duplicate_pairs'][0]['action'],'human_review_only')
    def test_different_name_does_not_match(self):
        fixture_file(self.paths[CELLS[0]],[example(1,CELLS[0],'Kafe A','cafe'),example(2,CELLS[0],'Kafe B','cafe')])
        self.assertEqual(len(self.ingest()['audit']['potential_duplicate_pairs']),0)
    def test_same_name_far_does_not_match(self):
        fixture_file(self.paths[CELLS[0]],[example(1,CELLS[0],'Kafe A','cafe',dx=-.002),example(2,CELLS[0],'Kafe A','cafe',dx=.002)])
        self.assertEqual(len(self.ingest()['audit']['potential_duplicate_pairs']),0)
    def test_missing_values_counted(self):
        first=example(1,CELLS[0],'A','cafe');first['properties'].pop('names');first['properties']['confidence']=None
        fixture_file(self.paths[CELLS[0]],[first])
        d=self.ingest()
        self.assertEqual(d['audit']['unknown_name'],1)
        self.assertEqual(d['audit']['missing_confidence'],1)
    def test_rejected_geometry_counted(self):
        bad=example(4,CELLS[0],'Wrong','restaurant')
        bad['geometry']['coordinates']=[0,0]
        fixture_file(self.paths[CELLS[0]],[bad])
        d=self.ingest()
        self.assertEqual(d['audit']['rejected']['outside_sampling_cell'],1)
    def test_identical_uuid_duplicates_not_double_counted(self):
        good=example(1,CELLS[0],'Kafe A','cafe')
        fixture_file(self.paths[CELLS[0]],[good,copy.deepcopy(good)])
        d=self.ingest()
        self.assertEqual(d['audit']['duplicate_identical_ids'],1)
        self.assertEqual(d['audit']['accepted'],2)
    def test_conflicting_same_id_aborts(self):
        a=example(1,CELLS[0],'Kafe A','cafe');b=example(1,CELLS[0],'Kafe B','cafe')
        fixture_file(self.paths[CELLS[0]],[a,b])
        with self.assertRaisesRegex(ValueError,'Conflicting rows'):self.ingest()
    def test_too_many_records_aborts_no_implicit_sample(self):
        with self.assertRaisesRegex(ValueError,'Feature count exceeded'):
            ingest_geojson(self.paths,pinned_release=RELEASE,max_features=1)
    def test_bad_fc_aborts(self):
        self.paths[CELLS[0]].write_text('{}')
        with self.assertRaisesRegex(ValueError,'FeatureCollection'):self.ingest()
    def test_reject_unknown_cell(self):
        with self.assertRaises(ValueError):ingest_geojson({'extra':self.paths[CELLS[0]]},pinned_release=RELEASE)
    def test_random_audit_no_truth_claim(self):
        d=self.ingest()
        a=pilot_audit_plan(d,budget=2,seed='long-private-mock-seed-00001')
        self.assertEqual(a,pilot_audit_plan(d,budget=2,seed='long-private-mock-seed-00001'))
        self.assertEqual(len(a['selected']),2)
        self.assertEqual(a['verified_labels'],0)
        self.assertTrue(all(x['review_outcome'] is None for x in a['selected']))
    def test_random_audit_different_seed(self):
        d=self.ingest()
        a=pilot_audit_plan(d,budget=2,seed='long-private-mock-seed-00001')
        b=pilot_audit_plan(d,budget=2,seed='long-private-mock-seed-00002')
        self.assertNotEqual(a['seed_commitment_sha256'],b['seed_commitment_sha256'])
    def test_audit_cannot_use_modified_population(self):
        d=self.ingest()
        d['normalized_places'][0]['name']='Injected name'
        with self.assertRaisesRegex(ValueError,'frozen hash'):
            pilot_audit_plan(d,budget=2,seed='long-private-mock-seed-00001')
    def test_budget_too_small_for_strata(self):
        with self.assertRaisesRegex(ValueError,'minimum'):
            pilot_audit_plan(self.ingest(),budget=1,seed='long-private-mock-seed-00001')
    def test_only_two_sampling_boxes(self):
        self.assertEqual(set(PILOT),{'besiktas_center','karakoy_center'})
    def test_synthetic_benchmark_identified(self):
        b=run()
        self.assertEqual(b['origin'],'synthetic_contract_fixture')
        self.assertEqual(b['real_istanbul_pois'],0)
    def test_offline_local_cli_export(self):
        out=Path(self.tmp.name)/'output'
        cmd=[sys.executable,str(ROOT/'scripts/overture_istanbul.py'),
             '--besiktas-geojson',str(self.paths['besiktas_center']),
             '--karakoy-geojson',str(self.paths['karakoy_center']),
             '--output',str(out)]
        p=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,timeout=10)
        self.assertEqual(p.returncode,0,p.stderr)
        manifest=json.loads((out/'manifest.json').read_text())
        places=json.loads((out/'places_minimal.json').read_text())
        self.assertEqual(manifest['audit']['accepted'],3)
        self.assertEqual(manifest['acquisition']['network_fetch_performed'],False)
        self.assertEqual(len(places['records']),3)
        self.assertEqual(manifest['normalized_sha256'],sha256((out/'places_minimal.json').read_bytes()).hexdigest())
        self.assertFalse(manifest['consumer_display_approved'])
        self.assertTrue(all(r['open_now'] is None for r in places['records']))
        # Output dir must not overwrite an existing run, protecting provenance.
        repeated=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,timeout=10)
        self.assertNotEqual(repeated.returncode,0)


if __name__=='__main__':unittest.main()
