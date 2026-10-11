"""DATA-016 mocked bounded patch transport; never contacts S3 during tests."""
import subprocess
import sys
import unittest
from unittest.mock import patch
from kepcore.gers_access_cost import DATA_DIR,PINNED_ZIP_SHA256,load_capture
from kepcore.gers_patch_pair import select_patch_counterparts
from scripts.probe_gers_region import RemoteRanges,RemoteFile,source_item

class FakeResponse:
    def __init__(self,body,size,etag):
        self.status=206;self._body=body
        self.headers={'Content-Length':str(len(body)),
                      'Content-Range':f'bytes 0-{len(body)-1}/{size}', 'ETag':etag}
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,n):return self._body[:n]

class PatchTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        m=load_capture(DATA_DIR/'footers.zip',PINNED_ZIP_SHA256)
        cls.item=source_item(select_patch_counterparts(m)['selected'][0])

    def test_default_data015_rejects_patch_without_optin(self):
        with patch('urllib.request.OpenerDirector.open') as opener:
            with self.assertRaises(ValueError):RemoteRanges().read(self.item,0,3)
            opener.assert_not_called()

    def test_invalid_release_or_scope_rejected(self):
        for bad in ('latest','2026-08-19.0','2026-09-23.2','2026-09-23.1/../evil',None):
            with self.subTest(bad=bad),self.assertRaises(ValueError):RemoteRanges(release=bad)

    def test_explicit_patch_release_can_read_exact_pinned_range(self):
        fake=FakeResponse(b'PAR1',self.item['size'],self.item['etag'])
        with patch('urllib.request.OpenerDirector.open',return_value=fake) as opener:
            src=RemoteRanges(release='2026-09-23.1')
            self.assertEqual(src.read(self.item,0,3),b'PAR1')
            self.assertEqual(src.budget.bytes_reserved,4)
            self.assertEqual(src.bytes_read,4)
            self.assertEqual(src.budget.requests,1)
            opener.assert_called_once()

    def test_mismatched_etag_stops_capture(self):
        fake=FakeResponse(b'PAR1',self.item['size'],'"bad"')
        with patch('urllib.request.OpenerDirector.open',return_value=fake):
            src=RemoteRanges(release='2026-09-23.1')
            with self.assertRaises(ValueError):src.read(self.item,0,3)
            self.assertTrue(src.failed)

    def test_foreign_partitions_blocked_without_network(self):
        item={**self.item,'key':self.item['key'].replace('type=place','type=address')}
        with patch('urllib.request.OpenerDirector.open') as opener:
            with self.assertRaises(ValueError):RemoteRanges(release='2026-09-23.1').read(item,0,3)
            opener.assert_not_called()

    def test_patch_stream_seeks_are_bounded(self):
        stream=RemoteFile(RemoteRanges(release='2026-09-23.1'),self.item)
        self.assertEqual(stream.seek(-8,2),self.item['size']-8)
        with self.assertRaises(ValueError):stream.seek(self.item['size']+1)
        with self.assertRaises(ValueError):stream.read()

    def test_patch_cli_offline_default_and_explicit_confirmation(self):
        runner=[sys.executable,'scripts/probe_gers_patch.py']
        out=subprocess.run(runner,capture_output=True,text=True)
        self.assertEqual(out.returncode,0)
        self.assertIn('OFFLINE_DEFAULT',out.stdout)
        out=subprocess.run(runner+['--fetch'],capture_output=True,text=True)
        self.assertNotEqual(out.returncode,0)
        self.assertIn('research',out.stderr.lower())

if __name__=='__main__':unittest.main()
