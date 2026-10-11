"""KEP-DATA-012: permanent original August artifact, offline release replay."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from kepcore.overture_archive_artifact import load_original_research_zip,replay_artifact,FROZEN_SHA

ROOT=Path(__file__).resolve().parents[1]
ARCHIVE=ROOT/"data/real/overture_istanbul_2026-08-19.0/original_actions_artifact.zip"

class DurableAugustResearchTests(unittest.TestCase):
    def test_original_zip_survived_as_pinned_file(self):
        self.assertTrue(ARCHIVE.is_file())
        self.assertFalse(ARCHIVE.is_symlink())
        self.assertEqual(ARCHIVE.stat().st_size,430240)
        raw=ARCHIVE.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),FROZEN_SHA["zip"])
        self.assertEqual(hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest(),
                         "78766b0894ddf7ddb24915425160c248e3b67856")

    def test_original_capture_and_records_verified_offline(self):
        rows,manifest,original=load_original_research_zip(ARCHIVE)
        self.assertEqual(len(rows),4650)
        self.assertEqual(manifest["source_release"],"2026-08-19.0")
        self.assertFalse(manifest["consumer_display_approved"])
        self.assertFalse(manifest["acquisition"]["upstream_authenticated_independently"])
        self.assertEqual(original["old_population_n"],4650)
        self.assertFalse(original["real_world_business_changes_estimated"])

    def test_historical_data_contains_no_private_contact_columns(self):
        rows,_,_=load_original_research_zip(ARCHIVE)
        for row in rows:
            self.assertFalse(row["consumer_verified"])
            self.assertIsNone(row["open_now"])
            self.assertIsNone(row["opening_hours"])
            for private_field in ("phones","socials","emails","private_reviewers","user_id"):
                self.assertNotIn(private_field,row)

    def test_two_real_source_releases_derive_exact_same_counts(self):
        result=replay_artifact(ARCHIVE)
        self.assertEqual((result["old_source_rows"],result["new_source_rows"]),(4650,4803))
        delta=result["record_delta"]
        self.assertEqual(delta["retained_ids"],4581)
        self.assertEqual(delta["newly_listed_ids"],222)
        self.assertEqual(delta["no_longer_listed_ids"],69)
        self.assertEqual(delta["field_or_geometry_revised_ids"],198)
        self.assertEqual(delta["confidence_only_revised_ids"],3337)
        self.assertEqual(delta["unchanged_ids"],1046)
        self.assertTrue(result["capture_order_reversed"])
        self.assertFalse(result["category_semantics_comparable"])
        self.assertIsNone(result["physical_business_closures"])
        self.assertIsNone(result["physical_business_openings"])

    def test_byte_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"bad.zip"
            p.write_bytes(ARCHIVE.read_bytes()+b"x")
            with self.assertRaisesRegex(ValueError,"ZIP"):
                load_original_research_zip(p)

    def test_archive_member_set_is_exact(self):
        with zipfile.ZipFile(ARCHIVE) as z:
            self.assertEqual(set(z.namelist()),
                {"places_minimal.json","manifest.json",
                 "historical_public_preflight.json","source_delta_provisional.json"})
            for name in z.namelist():
                self.assertEqual(hashlib.sha256(z.read(name)).hexdigest(),FROZEN_SHA[name])

    def test_persistent_cli_runs_without_network(self):
        script=ROOT/"scripts/replay_pinned_august.py"
        proc=subprocess.run([sys.executable,str(script)],cwd=ROOT,
                            capture_output=True,text=True,timeout=60)
        self.assertEqual(proc.returncode,0,proc.stderr)
        report=json.loads(proc.stdout)
        self.assertFalse(report["consumer_publish"])
        self.assertFalse(report["original_zip_required_from_external_source"])
        self.assertEqual(report["record_delta"]["retained_ids"],4581)

if __name__=="__main__":
    unittest.main()
