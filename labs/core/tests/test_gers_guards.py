"""Adversarial synthetic envelopes and access-file integrity, not field labels."""
import copy
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import shutil
import subprocess
import sys
import unittest
from kepcore.gers_reconciliation import (load_capture, public_summary,
    assess_changelog_compatibility, ACCESS_DIRECTORY, reconcile, load_pinned_pair)
from tests.test_gers_reconciliation import pair, poi, bundle, event, run
from kepcore.overture_places import canonical


class ReconciliationGuardTests(unittest.TestCase):
    def test_conflicts_preserved_even_when_predecessor_unknown(self):
        a,b=pair();c=bundle(a,b,[event(1,'unchanged'),event(1,'removed')])
        c['transition_evidence']['status']='unverified'
        x=run(a,b,c)
        self.assertEqual(x['official']['status'],'PAIR_NOT_VERIFIED')
        self.assertEqual(len(x['conflicts']),1)
        self.assertEqual(len(x['conflicts'][0]['official_events']),2)
        self.assertIsNone(x['official']['membership_agreement_fraction'])

    def test_public_projection_drops_unknown_private_fields(self):
        r=run(*pair());r['private_reviewer']='DO_NOT_EXPORT'
        self.assertNotIn('DO_NOT_EXPORT',str(public_summary(r)))

    def test_canonical_capture_roundtrip(self):
        a,b=pair();c=bundle(a,b,[event(1,'unchanged')]);raw=canonical(c)
        with TemporaryDirectory() as td:
            p=Path(td)/'c.json';p.write_bytes(raw)
            self.assertEqual(load_capture(p,sha256(raw).hexdigest()),c)

    def test_reformatted_capture_fails_even_with_matching_new_hash(self):
        with TemporaryDirectory() as td:
            p=Path(td)/'c.json';raw=b'{ "duplicate": 1, "duplicate": 2 }';p.write_bytes(raw)
            with self.assertRaises(ValueError):load_capture(p,sha256(raw).hexdigest())

    def test_capture_symlink_rejected(self):
        with TemporaryDirectory() as td:
            p=Path(td)/'c.json';raw=b'{}';p.write_bytes(raw)
            q=Path(td)/'link.json';q.symlink_to(p)
            with self.assertRaises(ValueError):load_capture(q,sha256(raw).hexdigest())

    def test_capture_byte_tamper_rejected(self):
        with TemporaryDirectory() as td:
            p=Path(td)/'c.json';p.write_bytes(b'{}')
            with self.assertRaises(ValueError):load_capture(p,'0'*64)

    def test_access_catalog_byte_tamper_fails(self):
        with TemporaryDirectory() as td:
            shutil.copytree(ACCESS_DIRECTORY,Path(td)/'access')
            p=Path(td)/'access/2026-09-23.1.catalog.json';p.write_bytes(p.read_bytes()+b' ')
            with self.assertRaises(ValueError):assess_changelog_compatibility(p.parent)

    def test_access_receipt_byte_tamper_fails(self):
        with TemporaryDirectory() as td:
            shutil.copytree(ACCESS_DIRECTORY,Path(td)/'access')
            p=Path(td)/'access/capture_attempt.json.gz';p.write_bytes(b'not-the-receipt')
            with self.assertRaises(ValueError):assess_changelog_compatibility(p.parent)

    def test_unknown_event_type_shape_rejected(self):
        a,b=pair()
        for kind in ([],{},True,7,None):
            with self.subTest(kind=kind),self.assertRaises(ValueError):
                run(a,b,bundle(a,b,[event(1,kind)]))

    def test_null_and_empty_unchanged_columns_deduplicate(self):
        a,b=pair()
        x=run(a,b,bundle(a,b,[event(1,'unchanged'),event(1,'unchanged',[])]))
        self.assertEqual(x['official']['duplicate_rows_collapsed'],1)

    def test_capture_before_release_is_not_backdated_evidence(self):
        a,b=pair();c=bundle(a,b,[event(1,'unchanged')],retrieved_at='2026-01-01T00:00:00Z')
        with self.assertRaises(ValueError):run(a,b,c)

    def test_wrong_source_root_is_not_same_publisher(self):
        a,b=pair();c=bundle(a,b,[event(1,'unchanged')],source_root='not-overture')
        with self.assertRaises(ValueError):run(a,b,c)

    def test_changed_geographic_footprint_rejected(self):
        a,b=pair()
        object.__setattr__(b,'sampling_cells',('besiktas_center',))
        with self.assertRaises(ValueError):run(a,b)

    def test_no_operator_flag_can_skip_known_real_intermediate(self):
        # An empty UNTRUSTED envelope must not override actual pinned STAC metadata.
        a,b=load_pinned_pair();c=bundle(a,b,[])
        c.update(origin='official_capture',source_url='https://overturemaps-us-west-2.s3.us-west-2.amazonaws.com/changelog/2026-09-23.1/theme=places/type=place/')
        c['transition_evidence']={'status':'operator_reviewed',
            'url':'https://stac.overturemaps.org/2026-09-23.1/catalog.json','sha256':'a'*64}
        with self.assertRaisesRegex(ValueError,'Nonconsecutive'):
            reconcile(a,b,changelog=c,expected_changelog_sha256=sha256(canonical(c)).hexdigest(),allow_historical_backfill=True)

    def test_capture_cli_default_is_offline_without_duckdb(self):
        p=Path(__file__).resolve().parents[1]/'scripts/capture_gers_chain_manual.py'
        result=subprocess.run([sys.executable,str(p)],capture_output=True,text=True,check=True)
        self.assertIn('"network_calls": 0',result.stdout)

    def test_capture_cli_missing_confirmation_fails_before_optional_import(self):
        p=Path(__file__).resolve().parents[1]/'scripts/capture_gers_chain_manual.py'
        result=subprocess.run([sys.executable,str(p),'--fetch'],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('RESEARCH_ONLY',result.stderr)
        self.assertNotIn('ModuleNotFoundError',result.stderr)


class PrivateExportAndCaptureExitTests(unittest.TestCase):
    def test_private_queue_outside_ignored_directory_rejected(self):
        from scripts import reconcile_gers_releases as cli
        with TemporaryDirectory() as td:
            with self.assertRaises(ValueError):cli.export_private_queue(Path(td)/'public.json',{})

    def test_private_queue_never_overwrites(self):
        from scripts import reconcile_gers_releases as cli
        with TemporaryDirectory() as td:
            p=Path(td)/'exists';p.write_text('keep')
            with self.assertRaises(ValueError):cli.export_private_queue(p,{})
            self.assertEqual(p.read_text(),'keep')

    def test_private_queue_mode_and_minimized_contract(self):
        from scripts import reconcile_gers_releases as cli
        from unittest.mock import patch
        with TemporaryDirectory() as td,patch.object(cli,'ROOT',Path(td)):
            private=Path(td)/'.local';private.mkdir();target=private/'queue.json'
            cli.export_private_queue(target,run(*pair()))
            self.assertEqual(target.stat().st_mode & 0o777,0o600)
            self.assertNotIn('private_reviewer',target.read_text())

    def test_symlinked_private_root_is_not_a_public_export_bypass(self):
        from scripts import reconcile_gers_releases as cli
        from unittest.mock import patch
        with TemporaryDirectory() as td,patch.object(cli,'ROOT',Path(td)):
            public=Path(td)/'public';public.mkdir();(Path(td)/'.local').symlink_to(public)
            with self.assertRaises(ValueError):cli.export_private_queue(Path(td)/'.local/q.json',run(*pair()))

    def test_incomplete_capture_causes_nonzero_exit(self):
        from scripts import capture_gers_chain_manual as cli
        from unittest.mock import patch
        with patch.object(sys,'argv',['capture','--fetch','--research-confirmation','RESEARCH_ONLY','--output','/unused']), \
             patch.object(cli,'capture',return_value={'status':'INCOMPLETE_CAPTURE'}):
            with self.assertRaises(SystemExit) as cm:cli.main()
            self.assertNotEqual(cm.exception.code,0)


if __name__=='__main__':unittest.main()
