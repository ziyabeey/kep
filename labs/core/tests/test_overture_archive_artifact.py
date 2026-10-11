"""Offline tests of the independent source-level comparator (no archive download)."""
import tempfile
import unittest
from pathlib import Path
from kepcore.overture_archive_artifact import (
    ORIGINAL_GITHUB_RUN,FROZEN_SHA,compare_source_records,load_original_research_zip,
)

def item(key, **fields):
    d={'overture_id':key,'name':'A','address':'Example','basic_category':'cafe',
       'taxonomy_primary':'cafe','operating_status':None,'locality':'Test',
       'country':'TR','source_provenance':[],'lon':29.,'lat':41.,
       'cell':'besiktas_center','confidence':.8}
    d.update(fields)
    return d

class SourceComparisonTests(unittest.TestCase):
    def test_addition_and_removal_are_catalog_operations(self):
        r=compare_source_records([item('a'),item('b')],[item('a'),item('c')])
        self.assertEqual((r['retained_ids'],r['newly_listed_ids'],r['no_longer_listed_ids']),(1,1,1))
        self.assertEqual(r['unchanged_ids'],1)
    def test_confidence_only_is_not_factual_revision(self):
        r=compare_source_records([item('a',confidence=.8)],[item('a',confidence=.5)])
        self.assertEqual(r['confidence_only_revised_ids'],1)
        self.assertEqual(r['field_or_geometry_revised_ids'],0)
    def test_name_and_confidence_overlap(self):
        r=compare_source_records([item('a')],[item('a',name='B',confidence=.4)])
        self.assertEqual(r['field_or_geometry_revised_ids'],1)
        self.assertEqual(r['confidence_only_revised_ids'],0)
        self.assertEqual(r['field_change_counts']['name'],1)
    def test_provenance_reordering_not_a_real_edit(self):
        s=[{'provider':'a'},{'provider':'b'}]
        r=compare_source_records([item('a',source_provenance=s)],
                                 [item('a',source_provenance=s[::-1])])
        self.assertEqual(r['unchanged_ids'],1)
    def test_duplicate_id_rejected(self):
        with self.assertRaises(ValueError):
            compare_source_records([item('a'),item('a')],[item('a')])
    def test_wrong_archive_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'bad.zip'
            p.write_bytes(b'PK-not-real')
            with self.assertRaises(ValueError):
                load_original_research_zip(p)
    def test_original_capture_sha_frozen(self):
        self.assertEqual(ORIGINAL_GITHUB_RUN,38121005943)
        self.assertEqual(FROZEN_SHA['zip'],'cb9ee86c128b4839a00722e1b192f460691c0f33e358f0b0b9ae458ea403ef05')

if __name__=='__main__':unittest.main()
