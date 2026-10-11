"""Synthetic/mock transport only. Never a live Overture access test in CI."""
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
from kepcore.gers_access_cost import BodyBudget, MAX_BODY
from scripts import gers_footer_study as cli


class Response:
    def __init__(self,body=b'<xml/>',headers=None,status=200):
        self.headers={} if headers is None else headers
        self.status=status;self.body=io.BytesIO(body);self.reads=0
    def read(self,n):self.reads+=1;return self.body.read(n)
    def __enter__(self):return self
    def __exit__(self,*a):pass


class TransportContracts(unittest.TestCase):
    def read(self,response,maximum=100,headers=None):
        with patch.object(cli.urllib.request,'build_opener') as p:
            p.return_value.open.return_value=response
            return cli.Reader().read(cli.S3+'?list-type=2',maximum=maximum,headers=headers)
    def test_bounded_chunked_listing_without_length(self):
        r=Response(headers={'Transfer-Encoding':'chunked'})
        self.assertEqual(self.read(r)[0],b'<xml/>')
    def test_chunked_response_at_cap_is_not_complete(self):
        with self.assertRaises(ValueError):self.read(Response(body=b'x'*100))
    def test_range_still_requires_exact_length(self):
        r=Response(status=206)
        with self.assertRaises(ValueError):self.read(r,headers={'Range':'bytes=0-3'})
        self.assertEqual(r.reads,0)
    def test_oversized_length_stops_before_read(self):
        r=Response(headers={'Content-Length':'101'})
        with self.assertRaises(ValueError):self.read(r)
        self.assertEqual(r.reads,0)
    def test_truncated_body_is_rejected(self):
        with self.assertRaises(ValueError):self.read(Response(headers={'Content-Length':'99'}))
    def test_nonidentity_encoding_stops_before_read(self):
        r=Response(headers={'Content-Length':'6','Content-Encoding':'gzip'})
        with self.assertRaises(ValueError):self.read(r)
        self.assertEqual(r.reads,0)
    def test_wrong_status_stops_before_read(self):
        r=Response(headers={'Content-Length':'6'},status=503)
        with self.assertRaises(ValueError):self.read(r)
        self.assertEqual(r.reads,0)
    def test_foreign_endpoint_is_denied_before_budget(self):
        r=cli.Reader()
        with self.assertRaises(ValueError):r.read('https://example.com/',maximum=10)
        self.assertEqual(r.budget.requests,0)
    def test_request_budget_counts_failed_calls(self):
        b=BodyBudget(1024)
        for _ in range(512):b.reserve(1)
        with self.assertRaises(ValueError):b.reserve(1)
    def test_operator_cannot_raise_budget(self):
        with self.assertRaises(ValueError):BodyBudget(MAX_BODY+1)
    def test_cli_default_does_not_need_arrow(self):
        p=subprocess.run([sys.executable,str(Path(cli.__file__))],capture_output=True,text=True)
        self.assertEqual(p.returncode,0)
        self.assertEqual(json.loads(p.stdout)['network_calls'],0)
    def test_cli_confirmation_required_before_import(self):
        p=subprocess.run([sys.executable,str(Path(cli.__file__)),'--fetch'],capture_output=True,text=True)
        self.assertNotEqual(p.returncode,0);self.assertNotIn('pyarrow',p.stderr)
    def test_failed_capture_exits_nonzero(self):
        with patch.object(sys,'argv',['script','--fetch','--research-confirmation','METADATA_ONLY_16MIB','--output','new']),patch.object(cli,'capture',return_value={'status':'INCOMPLETE_METADATA'}):
            with self.assertRaises(SystemExit) as e:cli.main()
            self.assertEqual(e.exception.code,3)

if __name__=='__main__':unittest.main()
