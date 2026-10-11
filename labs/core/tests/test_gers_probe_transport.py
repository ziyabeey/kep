"""Mock-only DATA-015 range/CLI security gates, no network."""
import subprocess
import sys
import unittest
from unittest.mock import patch

from scripts.probe_gers_region import RemoteFile,RemoteRanges,MAX_READ_BODY

class FakeHeaders(dict):
    def get(self,k,default=None):return super().get(k,default)
class FakeResponse:
    status=206
    def __init__(self,data,start,size,etag):
        self.data=data
        self.headers=FakeHeaders({'Content-Length':str(len(data)),
            'Content-Range':f'bytes {start}-{start+len(data)-1}/{size}', 'ETag':etag})
    def read(self,n):return self.data[:n]
    def __enter__(self):return self
    def __exit__(self,*args):pass

class SourceReadTests(unittest.TestCase):
    def setUp(self):
        self.obj={'key':'changelog/2026-09-23.0/theme=places/type=place/change_type=added/part-00000-abc.parquet',
                  'etag':'"etag"','size':50}

    def test_hard_cap_and_canonical_byte_spans(self):
        with patch('urllib.request.OpenerDirector.open') as mocked:
            s=RemoteRanges()
            with self.assertRaises(ValueError):s.read(self.obj,-1,9)
            with self.assertRaises(ValueError):s.read(self.obj,0,50)
            with self.assertRaises(ValueError):s.read(self.obj,0,2**25)
            self.assertEqual(s.budget.requests,0)
            mocked.assert_not_called()

    def test_wrong_source_release_denied(self):
        bad={**self.obj,'key':self.obj['key'].replace('2026-09-23.0','2026-09-23.1')}
        with patch('urllib.request.OpenerDirector.open') as mocked:
            with self.assertRaises(ValueError):RemoteRanges().read(bad,0,3)
            mocked.assert_not_called()

    def test_range_bytes_and_etag_verified(self):
        with patch('urllib.request.OpenerDirector.open') as opener:
            opener.return_value=FakeResponse(b'PAR1',0,50,'"etag"')
            s=RemoteRanges()
            self.assertEqual(s.read(self.obj,0,3),b'PAR1')
            self.assertEqual(s.bytes_read,4)
            self.assertEqual(s.budget.requests,1)

    def test_wrong_content_range_denied_and_stops(self):
        x=FakeResponse(b'PAR1',0,50,'"etag"')
        x.headers['Content-Range']='bytes 2-5/50'
        with patch('urllib.request.OpenerDirector.open',return_value=x):
            s=RemoteRanges()
            with self.assertRaises(ValueError):s.read(self.obj,0,3)
            self.assertTrue(s.failed)
            with self.assertRaises(ValueError):s.read(self.obj,0,3)
            self.assertEqual(s.budget.requests,1)

    def test_seek_and_read_bounds(self):
        with patch('urllib.request.OpenerDirector.open',return_value=FakeResponse(b'PAR1',0,50,'"etag"')):
            s=RemoteRanges();f=RemoteFile(s,self.obj)
            self.assertEqual(f.seek(0),0)
            self.assertEqual(f.read(4),b'PAR1')
            self.assertEqual(f.tell(),4)
            self.assertEqual(f.seek(-50,2),0)
            with self.assertRaises(ValueError):f.read()
            with self.assertRaises(ValueError):f.seek(51)

    def test_cli_offline_and_explicit_confirmation(self):
        runner=['python','scripts/probe_gers_region.py']
        p=subprocess.run(runner,capture_output=True,text=True)
        self.assertEqual(p.returncode,0)
        self.assertIn('OFFLINE_DEFAULT',p.stdout)
        p=subprocess.run(runner+['--fetch'],capture_output=True,text=True)
        self.assertNotEqual(p.returncode,0)
        self.assertIn('research confirmation',p.stderr)

if __name__=='__main__':unittest.main()
