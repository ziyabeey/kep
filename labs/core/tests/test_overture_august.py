"""KEP-DATA-007: August historical schema and source-version safety gates.

These fixtures are synthetic. No historical August Istanbul release is embedded
or claimed observed by this unittest suite.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import subprocess
import sys
import unittest

from kepcore.overture_places import PILOT,canonical
from kepcore.overture_august import (
    AUGUST, SCHEMA_AUGUST, SCHEMA, STAC_CHILD, S3_PREFIX,
    validate_august_stac, normalize_august_feature, ingest_august_files,
    prepare_august_bundle, load_august_snapshot, compare_august_september,
)
from scripts.overture_august_legacy import source_query, _minimal_feature

OBSERVED='2026-08-26T12:00:00+00:00'
IDS=['00000000-0000-0000-0000-000000000001',
     '00000000-0000-0000-0000-000000000002']


def stac(with_august=True,latest='2026-09-23.1'):
    links=[{'rel':'child','href':'https://stac.overturemaps.org/2026-09-23.1/catalog.json','latest':True}]
    if with_august:links.append({'rel':'child','href':STAC_CHILD})
    return canonical({'type':'Catalog','stac_version':'1.1.0','latest':latest,'links':links})


def feat(cell,*,legacy='old_tea_house',basic=None,taxonomy=None,rid=None,**props):
    west,south,east,north=PILOT[cell]
    d={'type':'Feature','geometry':{'type':'Point', 'coordinates':[(west+east)/2,(south+north)/2]},
       'properties':{'id':rid or IDS[0 if cell=='besiktas_center' else 1],
          'theme':'places','type':'place','categories':{'primary':legacy} if legacy else None,
          'basic_category':basic,'taxonomy':{'primary':taxonomy} if taxonomy else None,
          'names':{'primary':'KEP SYNTHETIC EXAMPLE'},
          'operating_status':'open','confidence':.7,
          'addresses':[{'freeform':'Synthetic Place Address','country':'TR','locality':'İstanbul'}],
          'sources':[{'dataset':'fixture','license':'CC0-1.0','provider':'test'}]}}
    d['properties'].update(props)
    return d


def temp_sources(tmp, variants=None):
    inputs={}
    for cell in sorted(PILOT):
        features=(variants or {}).get(cell,[feat(cell)])
        p=Path(tmp)/(cell+'.geojson')
        p.write_bytes(canonical({'type':'FeatureCollection','features':features}))
        inputs[cell]=p
    return inputs


class HistoricalSchemaTests(unittest.TestCase):
    def test_august_child_exact_even_when_latest_is_september(self):
        result=validate_august_stac(stac())
        self.assertTrue(result['listed_in_stac'])
        self.assertFalse(result['s3_objects_verified'])
        self.assertEqual(result['release'],AUGUST)
    def test_missing_august_child_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'August release'):
            validate_august_stac(stac(False))
    def test_stac_bad_format_rejected(self):
        for raw in [b'[]',b'{}',b'broken-json', b'', b' ' * 200001]:
            with self.subTest(raw=raw[:8]),self.assertRaises((ValueError,TypeError)):
                validate_august_stac(raw)
    def test_do_not_infer_new_taxonomy_from_legacy_categories(self):
        row,flags=normalize_august_feature(feat('besiktas_center'),cell='besiktas_center')
        self.assertIsNone(row['taxonomy_primary'])
        self.assertIsNone(row['basic_category'])
        self.assertTrue(flags['legacy_primary_present'])
        self.assertFalse(flags['native_taxonomy_primary_present'])
    def test_native_categories_survive_without_guesswork(self):
        row,flags=normalize_august_feature(feat('besiktas_center',basic='cafe',taxonomy='tea_house'),cell='besiktas_center')
        self.assertEqual((row['taxonomy_primary'],row['basic_category']),('tea_house','cafe'))
        self.assertTrue(flags['native_taxonomy_primary_present'])
    def test_absent_legacy_category_permitted(self):
        row,flags=normalize_august_feature(feat('besiktas_center',legacy=None),cell='besiktas_center')
        self.assertIsNone(row['taxonomy_primary'])
        self.assertFalse(flags['legacy_primary_present'])
    def test_legacy_categories_have_strict_shape(self):
        for value in (3,{'primary':12},'foo'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_august_feature(feat('besiktas_center',categories=value),cell='besiktas_center')
    def test_native_fields_strict_shape(self):
        for name,value in [('taxonomy',3),('basic_category',12)]:
            with self.subTest(name=name),self.assertRaises(ValueError):
                feature=feat('besiktas_center')
                feature['properties'][name]=value
                normalize_august_feature(feature,cell='besiktas_center')
    def test_private_or_live_fields_not_projected(self):
        f=feat('besiktas_center',phones=['+901234'], emails=['private@example.test'],
               socials=['https://social.example/p'], websites=['https://test.example'])
        row,_=normalize_august_feature(f,cell='besiktas_center')
        self.assertNotIn('phones',row)
        self.assertNotIn('emails',row)
        self.assertNotIn('socials',row)
        self.assertIsNone(row['open_now'])
        self.assertFalse(row['consumer_verified'])
    def test_outside_cell_rejected(self):
        f=feat('besiktas_center');f['geometry']['coordinates']=[25,38]
        with self.assertRaisesRegex(ValueError,'outside_sampling_cell'):
            normalize_august_feature(f,cell='besiktas_center')


class HistoricalIngestTests(unittest.TestCase):
    def test_two_cells_and_legacy_only_stats(self):
        with TemporaryDirectory() as t:
            v=ingest_august_files(temp_sources(t))
            self.assertEqual(len(v['records']),2)
            self.assertEqual(v['migration']['legacy_category_only_unmapped'],2)
            self.assertFalse(v['migration']['legacy_category_mapping_performed'])
            self.assertEqual(v['audit']['rows_read'],2)
    def test_missing_second_cell_rejected(self):
        with TemporaryDirectory() as t:
            paths=temp_sources(t);paths.pop('karakoy_center')
            with self.assertRaisesRegex(ValueError,'Both original'):
                ingest_august_files(paths)
    def test_contradictory_id_rejected(self):
        with TemporaryDirectory() as t:
            f=feat('besiktas_center'); g=deepcopy(f);g['properties']['names']['primary']='another name'
            paths=temp_sources(t,{'besiktas_center':[f,g]})
            with self.assertRaisesRegex(ValueError,'Contradictory'):
                ingest_august_files(paths)
    def test_identical_id_reposted_only_one_record(self):
        with TemporaryDirectory() as t:
            f=feat('besiktas_center')
            v=ingest_august_files(temp_sources(t,{'besiktas_center':[f,deepcopy(f)]}))
            self.assertEqual(v['audit']['duplicate_identical_ids'],1)
            self.assertEqual(v['audit']['accepted'],2)
    def test_unsafe_symlink_rejected(self):
        with TemporaryDirectory() as t:
            paths=temp_sources(t)
            link=Path(t)/'symlink.json'
            link.symlink_to(paths['karakoy_center'])
            paths['karakoy_center']=link
            with self.assertRaises(ValueError):ingest_august_files(paths)
    def test_all_invalid_records_are_not_a_dataset(self):
        with TemporaryDirectory() as t:
            paths=temp_sources(t,{c:[] for c in PILOT})
            with self.assertRaisesRegex(ValueError,'No valid August'):
                ingest_august_files(paths)
    def test_rejected_legacy_invalid_category_counts(self):
        with TemporaryDirectory() as t:
            paths=temp_sources(t,{'besiktas_center':[feat('besiktas_center',categories={'primary':99})]})
            v=ingest_august_files(paths)
            self.assertEqual(v['audit']['rejected']['invalid_legacy_categories'],1)
            self.assertEqual(v['audit']['accepted'],1)


class HistoricalBundleTests(unittest.TestCase):
    def make_bundle(self,tmp,acquisition='operator_supplied_local_files'):
        base=Path(tmp);inputs=temp_sources(base)
        directory=base/'august'
        result=prepare_august_bundle(inputs,output=directory,stac_bytes=stac(),
            observed_at=OBSERVED,acquisition=acquisition)
        return directory,result
    def test_bundle_roundtrip_records_and_rights(self):
        with TemporaryDirectory() as t:
            d,r=self.make_bundle(t)
            snap,m=load_august_snapshot(d,expected_sha256=r['normalized_sha256'],expected_manifest_sha256=r['manifest_sha256'],
                expected_stac_sha256=sha256(stac()).hexdigest(),expected_observed_at=OBSERVED)
            self.assertEqual(len(snap.records),2)
            self.assertEqual(snap.release,AUGUST)
            self.assertEqual(snap.schema,SCHEMA)
            self.assertFalse(m['consumer_publish'])
            self.assertFalse(m['acquisition']['upstream_authenticated_independently'])
    def test_cannot_claim_august_observed_before_release(self):
        with TemporaryDirectory() as t:
            with self.assertRaises(ValueError):prepare_august_bundle(temp_sources(t),output=Path(t)/'august',
                stac_bytes=stac(),observed_at='2026-08-18T00:00:00Z',acquisition='operator_supplied_local_files')
    def test_output_never_overwritten(self):
        with TemporaryDirectory() as t:
            self.make_bundle(t)
            with self.assertRaises(FileExistsError):self.make_bundle(t)
    def test_broken_normalized_hash_rejected(self):
        with TemporaryDirectory() as t:
            d,r=self.make_bundle(t)
            p=d/'places_minimal.json';p.write_bytes(p.read_bytes()+b' ')
            with self.assertRaises(ValueError):load_august_snapshot(d,expected_sha256=r['normalized_sha256'],expected_manifest_sha256=r['manifest_sha256'],
                expected_stac_sha256=sha256(stac()).hexdigest(),expected_observed_at=OBSERVED)
    def test_unapproved_stac_hash_rejected(self):
        with TemporaryDirectory() as t:
            d,r=self.make_bundle(t)
            with self.assertRaises(ValueError):load_august_snapshot(d,expected_sha256=r['normalized_sha256'],expected_manifest_sha256=r['manifest_sha256'],
                expected_stac_sha256='0'*64,expected_observed_at=OBSERVED)
    def test_wrong_reviewed_observation_timestamp_rejected(self):
        with TemporaryDirectory() as t:
            d,r=self.make_bundle(t)
            with self.assertRaises(ValueError):load_august_snapshot(d,expected_sha256=r['normalized_sha256'],expected_manifest_sha256=r['manifest_sha256'],
                expected_stac_sha256=sha256(stac()).hexdigest(),expected_observed_at='2026-08-28T00:00:00Z')
    def test_consumer_permission_tamper_rejected(self):
        with TemporaryDirectory() as t:
            d,r=self.make_bundle(t)
            manifest=d/'manifest.json';m=json.loads(manifest.read_bytes());m['consumer_publish']=True
            manifest.write_bytes(canonical(m))
            with self.assertRaises(ValueError):load_august_snapshot(d,expected_sha256=r['normalized_sha256'],expected_manifest_sha256=r['manifest_sha256'],
                expected_stac_sha256=sha256(stac()).hexdigest(),expected_observed_at=OBSERVED)
    def test_changed_release_rejected(self):
        with TemporaryDirectory() as t:
            d,r=self.make_bundle(t)
            manifest=d/'manifest.json';m=json.loads(manifest.read_bytes());m['source_release']='2026-09-23.1'
            manifest.write_bytes(canonical(m))
            with self.assertRaises(ValueError):load_august_snapshot(d,expected_sha256=r['normalized_sha256'],expected_manifest_sha256=r['manifest_sha256'],
                expected_stac_sha256=sha256(stac()).hexdigest(),expected_observed_at=OBSERVED)
    def test_direct_august_to_frozen_september_compares_without_business_claims(self):
        with TemporaryDirectory() as t:
            d,r=self.make_bundle(t)
            try:
                v=compare_august_september(d,expected_sha256=r['normalized_sha256'],expected_manifest_sha256=r['manifest_sha256'],
                    expected_stac_sha256=sha256(stac()).hexdigest(),expected_observed_at=OBSERVED)
            except FileNotFoundError:
                self.skipTest('Frozen 4803-record September archive is not available in this checkout')
            self.assertEqual(v['old_release'],AUGUST)
            self.assertEqual(v['new_release'],'2026-09-23.1')
            self.assertFalse(v['may_infer_business_openings_closures'])
            self.assertFalse(v['cross_schema_migration']['category_differences_are_semantically_comparable'])
            self.assertFalse(v['source_publisher_authenticated_by_hash_alone'])


class HistoricalFetchContractTests(unittest.TestCase):
    def test_query_is_pinned_to_august_not_latest(self):
        for cell in PILOT:
            q=source_query(cell)
            self.assertIn('2026-08-19.0',q)
            self.assertNotIn('2026-09-23.1',q)
            self.assertNotIn('latest',q)
            self.assertIn('bbox.xmin',q)
    def test_unlisted_cell_never_runs_sql(self):
        with self.assertRaises(ValueError):source_query('istanbul_all')
    def test_row_projection_drops_personal_fields(self):
        value=(IDS[0],29.005,41.042,{'primary':'Synthetic Shop'},
            {'primary':'old_shop'},'cafe',{'primary':'cafe'},.3,'open',
            [{'freeform':'Street','country':'TR'}],[{'dataset':'x','provider':'y','license':'CC0','record_id':'private'}])
        f=_minimal_feature(value)
        self.assertEqual(f['properties']['categories']['primary'],'old_shop')
        self.assertNotIn('record_id',f['properties']['sources'][0])
        self.assertNotIn('emails',f['properties'])
    def test_default_runner_does_no_network_calls(self):
        root=Path(__file__).resolve().parents[1]
        p=subprocess.run([sys.executable,str(root/'scripts/overture_august_legacy.py')],
                         capture_output=True,text=True,cwd=root,timeout=15)
        self.assertEqual(p.returncode,0,p.stderr)
        out=json.loads(p.stdout)
        self.assertEqual(out['network_calls'],0)
        self.assertEqual(out['release'],AUGUST)
    def test_release_comparison_cli_requires_explicit_hashes(self):
        root=Path(__file__).resolve().parents[1]
        p=subprocess.run([sys.executable,str(root/'scripts/compare_overture_august.py'),'--help'],
                         capture_output=True,text=True,cwd=root,timeout=15)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertIn('--august-sha256',p.stdout)

if __name__=='__main__':unittest.main()
