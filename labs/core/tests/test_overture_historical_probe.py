"""DATA-008: no-network historical object reachability & artifact receipt tests."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import subprocess
import sys
import unittest

from kepcore.overture_historical_probe import (
    BUCKET, PINNED_PREFIX, S3_BASE, list_url, parse_public_listing,
    confirm_public_parquet_object,
)
from kepcore.overture_places import PILOT, canonical
from scripts import overture_august_legacy as legacy

KEY=PINNED_PREFIX+'part-00000-c7e47654-8483-5b8f-b183-7ba73334f7a5-c000.zstd.parquet'
ETAG='"1a95e694df6b2978fd4f268c9dd9d65c-10"'


def list_body(*, prefix=PINNED_PREFIX, key=KEY, size=634918674, etag=ETAG,
              keycount=1, name=BUCKET, modified='2026-08-19T15:45:33.000Z',
              contents=True):
    elements = (f'<Contents><Key>{key}</Key><LastModified>{modified}</LastModified>'
                f'<ETag>{etag}</ETag><Size>{size}</Size></Contents>') if contents else ''
    return (f'<?xml version="1.0" encoding="UTF-8"?>'
            f'<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
            f'<Name>{name}</Name><Prefix>{prefix}</Prefix><KeyCount>{keycount}</KeyCount>'
            f'<MaxKeys>1</MaxKeys><IsTruncated>true</IsTruncated>{elements}'
            f'</ListBucketResult>').encode()


class PrefixTests(unittest.TestCase):
    def test_public_list_uses_exact_host_prefix_and_single_key(self):
        url = list_url()
        self.assertTrue(url.startswith(S3_BASE+'/?list-type=2&'))
        self.assertIn('2026-08-19.0', url)
        self.assertIn('max-keys=1', url)
        self.assertNotIn('latest', url)
    def test_realistic_s3_xml_metadata(self):
        parsed = parse_public_listing(list_body())
        self.assertEqual(parsed['key'],KEY)
        self.assertEqual(parsed['size_bytes'],634918674)
        self.assertEqual(parsed['etag'],ETAG)
        self.assertEqual(parsed['listing_sha256'],sha256(list_body()).hexdigest())
    def test_bad_origin_or_prefix_fails(self):
        for changes in ({'name':'wrong-bucket'}, {'prefix':'release/2026-09-23.1/theme=places/type=place/'},
                        {'key':'release/2026-09-23.1/theme=places/type=place/a.parquet'},
                        {'key':'release/2026-08-19.0/theme=places/type=building/a.parquet'}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                parse_public_listing(list_body(**changes))
    def test_no_key_not_proof_of_availability(self):
        for body in (list_body(keycount=0,contents=False), list_body(contents=False)):
            with self.assertRaises(ValueError):parse_public_listing(body)
    def test_invalid_size_or_name_fails(self):
        for changes in ({'size':0},{'size':-2},{'size':'NaN'},
                        {'key':PINNED_PREFIX+'places.csv'},
                        {'key':PINNED_PREFIX+'part-000../a.parquet'}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                parse_public_listing(list_body(**changes))
    def test_bad_etag_or_timestamp_fails(self):
        for changes in ({'etag':'abc'}, {'etag':'"abcdef"'},
                        {'modified':'not-a-date'}, {'modified':'2026-05-04T00:00:00Z'}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                parse_public_listing(list_body(**changes))
    def test_reject_xml_entity_expansion(self):
        body = b'<!DOCTYPE a [ <!ENTITY x "xx"> ]><ListBucketResult>&x;</ListBucketResult>'
        with self.assertRaisesRegex(ValueError,'XML entities'):
            parse_public_listing(body)
    def test_bad_xml_and_size_guard(self):
        for body in (b'',b'<not-list/>',b'<junk',b'x'*24001,b'{}'):
            with self.subTest(n=len(body)),self.assertRaises(ValueError):
                parse_public_listing(body)


class RemoteContractTests(unittest.TestCase):
    def setUp(self):
        self.calls=[]
        def ok(url,*,method,max_bytes):
            self.calls.append((url,method,max_bytes))
            if method=='GET':return 200,{},list_body()
            return 200,{'content-length':'634918674','etag':ETAG},b''
        self.ok=ok
    def test_list_plus_head_only_no_download(self):
        proof=confirm_public_parquet_object(request_fn=self.ok,checked_at='2026-10-11T08:30:00+03:00')
        self.assertEqual(len(self.calls),2)
        self.assertEqual(self.calls[0][1:],('GET',24000))
        self.assertEqual(self.calls[1][1:],('HEAD',0))
        self.assertIn('2026-08-19.0',self.calls[1][0])
        self.assertFalse(proof['regional_istanbul_download_completed'])
        self.assertFalse(proof['consumer_publish_approved'])
        self.assertFalse(proof['all_release_parts_verified'])
        self.assertTrue(proof['one_parquet_head_verified'])
    def test_head_wrong_size_fails(self):
        def fn(url,*,method,max_bytes):
            if method=='GET':return 200,{},list_body()
            return 200,{'content-length':'1','etag':ETAG},b''
        with self.assertRaisesRegex(ValueError,'lengths differ'):
            confirm_public_parquet_object(request_fn=fn)
    def test_head_wrong_etag_fails(self):
        def fn(url,*,method,max_bytes):
            if method=='GET':return 200,{},list_body()
            return 200,{'content-length':'634918674','etag':'"00000000000000000000000000000000"'},b''
        with self.assertRaisesRegex(ValueError,'ETags differ'):
            confirm_public_parquet_object(request_fn=fn)
    def test_head_denied_fails(self):
        def fn(url,*,method,max_bytes):
            if method=='GET':return 200,{},list_body()
            return 403,{},b''
        with self.assertRaisesRegex(ValueError,'HEAD'):
            confirm_public_parquet_object(request_fn=fn)
    def test_list_denied_fails(self):
        with self.assertRaisesRegex(ValueError,'listing unavailable'):
            confirm_public_parquet_object(request_fn=lambda *a,**k:(403,{},b''))
    def test_preflight_timestamp_has_offset(self):
        with self.assertRaises(ValueError):
            confirm_public_parquet_object(request_fn=self.ok,checked_at='2026-10-11T08:30:00')
    def test_check_does_not_include_secret_credentials(self):
        proof=confirm_public_parquet_object(request_fn=self.ok)
        self.assertFalse(any('secret' in k or 'token' in k for k in proof))
        self.assertNotIn('auth',json.dumps(proof))


class ManualWorkflowIntegrationTests(unittest.TestCase):
    def test_default_cli_offline(self):
        repo=Path(__file__).resolve().parents[1]
        p=subprocess.run([sys.executable,str(repo/'scripts/overture_august_legacy.py')],
            cwd=repo,capture_output=True,text=True,timeout=10)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(json.loads(p.stdout)['network_calls'],0)
    def test_cli_mutually_exclusive_probe_and_fetch(self):
        repo=Path(__file__).resolve().parents[1]
        p=subprocess.run([sys.executable,str(repo/'scripts/overture_august_legacy.py'),'--probe','--fetch'],
                         cwd=repo,capture_output=True,text=True,timeout=10)
        self.assertNotEqual(p.returncode,0)
    def test_preflight_runs_before_any_expensive_parquet_query(self):
        with TemporaryDirectory() as d:
            with patch.object(legacy,'_catalog',return_value=b'CATALOG'),\
                 patch.object(legacy,'confirm_public_parquet_object',side_effect=ValueError('No S3 object')),\
                 patch.object(legacy,'_bounded_duckdb_extract') as heavy:
                with self.assertRaisesRegex(ValueError,'No S3 object'):
                    legacy.run(Path(d)/'out')
                heavy.assert_not_called()
    def test_receipt_links_to_exact_normalized_artifact(self):
        with TemporaryDirectory() as d:
            original=Path(d)/'aug'; inp={}
            for cell in PILOT:
                f=Path(d)/(cell+'.geojson')
                w,s,e,n=PILOT[cell]
                feat={'type':'Feature','geometry':{'type':'Point','coordinates':[(w+e)/2,(s+n)/2]},
                      'properties':{'id':'00000000-0000-0000-0000-000000000001' if cell=='besiktas_center' else '00000000-0000-0000-0000-000000000002',
                                    'theme':'places','type':'place','names':{'primary':'synthetic'},
                                    'categories':{'primary':'old'},'confidence':.4,
                                    'addresses':[],'sources':[],'taxonomy':None,'basic_category':None}}
                f.write_bytes(canonical({'type':'FeatureCollection','features':[feat]}))
                inp[cell]=f
            from kepcore.overture_august import prepare_august_bundle
            stac=canonical({'type':'Catalog','links':[{'rel':'child','href':'https://stac.overturemaps.org/2026-08-19.0/catalog.json'}]})
            proof={'study':'KEP-DATA-008','one_parquet_head_verified':True,
                   'all_release_parts_verified':False, 'regional_istanbul_download_completed':False}
            with patch.object(legacy,'_catalog',return_value=stac),\
                 patch.object(legacy,'confirm_public_parquet_object',return_value=proof),\
                 patch.object(legacy,'_bounded_duckdb_extract',return_value=inp),\
                 patch.object(legacy,'prepare_august_bundle',side_effect=lambda paths,output,stac_bytes,observed_at,acquisition,stac_after_bytes:prepare_august_bundle(inp,output=output,stac_bytes=stac,observed_at='2026-10-11T08:00:00+03:00',acquisition='operator_supplied_local_files')):
                result=legacy.run(original)
            receipt=json.loads((original/'historical_public_preflight.json').read_bytes())
            self.assertEqual(receipt['normalized_sha256'],result['normalized_sha256'])
            self.assertEqual(receipt['manifest_sha256'],result['manifest_sha256'])
            self.assertFalse(receipt['regional_istanbul_download_completed'])

if __name__=='__main__':unittest.main()
