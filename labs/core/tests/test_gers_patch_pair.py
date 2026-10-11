"""DATA-016 synthetic patch-pair contracts and pinned real footer checks."""
import json
import unittest
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from kepcore.gers_access_cost import DATA_DIR, PINNED_ZIP_SHA256, load_capture
from kepcore.gers_patch_pair import select_patch_counterparts, compare_regional_fingerprints

REPORT=Path(__file__).resolve().parents[1]/"reports/KEP_DATA_015_REGIONAL_EVENTS.json"

class SyntheticPatchComparison(unittest.TestCase):
    def fixture(self, *, fingerprint='a'*64):
        previous = {'regional_observation_sha256':'a'*64,
                    'regional_event_type_counts':{'added':2,'removed':1,'data_changed':0,'unchanged':0},
                    'regional_rows':3,'unique_regional_ids':3,'matched_union_ids':3,
                    'conflicting_regional_ids':0,'duplicate_exact_observations':0,
                    'scanned_rows':10}
        current = {**previous,'regional_observation_sha256':fingerprint}
        return previous,current

    def test_equal_fingerprint_proves_only_regional_observation_equivalence(self):
        p,c=self.fixture()
        result=compare_regional_fingerprints(p,c)
        self.assertTrue(result['regional_observation_sets_equal'])
        self.assertFalse(result['safe_to_compose_as_independent_adjacent_hops'])
        self.assertIsNone(result['official_membership_agreement_fraction'])
        self.assertIsNone(result['verified_changelog_comparison_baseline'])
        self.assertEqual(result['independent_publisher_roots'],1)
        self.assertFalse(result['business_event_accuracy_available'])
        self.assertFalse(result['complete_for_all_union_ids'])

    def test_unequal_fingerprint_is_not_a_conclusion_about_patch_baseline(self):
        p,c=self.fixture(fingerprint='b'*64)
        result=compare_regional_fingerprints(p,c)
        self.assertFalse(result['regional_observation_sets_equal'])
        self.assertEqual(result['status'],'REGIONAL_PROJECTION_DIFFERENCE_REQUIRES_REVIEW')
        self.assertIsNone(result['verified_changelog_comparison_baseline'])

    def test_changed_counts_are_not_overridden_by_matching_fingerprint(self):
        p,c=self.fixture();c['regional_rows']+=1
        with self.assertRaises(ValueError):compare_regional_fingerprints(p,c)

    def test_conflicts_or_duplicates_refuse_clean_alias_label(self):
        for key in ('conflicting_regional_ids','duplicate_exact_observations'):
            p,c=self.fixture();c[key]=1
            with self.subTest(key=key),self.assertRaises(ValueError):
                compare_regional_fingerprints(p,c)

    def test_digest_incorrect_type_rejected(self):
        for value in (None,'oops','F'*64):
            p,c=self.fixture();c['regional_observation_sha256']=value
            with self.subTest(value=value),self.assertRaises(ValueError):
                compare_regional_fingerprints(p,c)

    def test_extra_private_fields_cannot_be_leaked_into_public_report(self):
        p,c=self.fixture();c['raw_ids']=['private']
        with self.assertRaises(ValueError):compare_regional_fingerprints(p,c)

    def test_prior_receipt_is_pinned_not_a_synthetic_source(self):
        raw=REPORT.read_bytes()
        self.assertEqual(sha256(raw).hexdigest(),
                         "8796914fb07117ddd5551c7480def866d17e8e7c8b04df8ed42af52d79598a10")
        result=json.loads(raw)
        self.assertEqual(result['aggregate']['regional_observation_sha256'],
                         '524aeb660c7be71ddcd4fcd67f54c0c9af5bc15828ffe6208a85f81991d204c3')

class PinnedRealCounterparts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest=load_capture(DATA_DIR/'footers.zip',PINNED_ZIP_SHA256)

    def test_real_selects_only_two_patch_groups(self):
        plan=select_patch_counterparts(self.manifest)
        self.assertEqual(plan['release'],'2026-09-23.1')
        self.assertEqual(len(plan['selected']),2)
        self.assertEqual([x['change_type'] for x in plan['selected']],['added','removed'])
        self.assertEqual(sum(x['rows'] for x in plan['selected']),207733)
        self.assertEqual(sum(x['estimated_compressed_column_bytes'] for x in plan['selected']),7890995)
        self.assertTrue(plan['all_counterpart_metadata_equal'])
        self.assertFalse(plan['complete_for_all_union_ids'])
        self.assertIsNone(plan['verified_changelog_comparison_baseline'])

    def test_footer_mutation_cannot_impersonate_pinned_capture(self):
        c=deepcopy(self.manifest);c['objects'][0]['etag']='"tamper"'
        with self.assertRaises(ValueError):select_patch_counterparts(c)

    def test_missing_patch_counterpart_fails_closed(self):
        c=deepcopy(self.manifest)
        c['objects']=[o for o in c['objects'] if not (o['release']=='2026-09-23.1' and o['change_type']=='added')]
        with self.assertRaises(ValueError):select_patch_counterparts(c)

    def test_local_immutable_manifest_does_not_contain_official_event_rows(self):
        plan=select_patch_counterparts(self.manifest)
        self.assertEqual(plan['observed_event_rows'],0)
        self.assertEqual(plan['source_metadata_zip_sha256'],PINNED_ZIP_SHA256)
        self.assertFalse(plan['consumer_publish'])

if __name__=='__main__':unittest.main()
