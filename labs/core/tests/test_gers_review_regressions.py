"""Synthetic-only regression strengthening from PR review, never real labels."""
import unittest
from tests.test_gers_reconciliation import pair, poi, event, bundle, run


class ReviewedAbstentionTests(unittest.TestCase):
    def test_conflict_suppresses_nonzero_membership_agreement(self):
        before, after = pair([poi(1), poi(2)], [poi(2), poi(3)])
        capture = bundle(before, after, [event(1, 'removed'),
            event(2, 'unchanged'), event(2, 'removed'), event(3, 'added')])
        report = run(before, after, capture)
        self.assertEqual(report['official']['status'], 'CONFLICTED')
        self.assertEqual(report['source_record_delta']['newly_listed_ids'], 1)
        self.assertEqual(report['source_record_delta']['no_longer_listed_ids'], 1)
        self.assertIsNone(report['official']['membership_agreement_fraction'])
        self.assertEqual(report['official']['membership_comparable_ids'], 0)
        self.assertEqual(len(report['conflicts'][0]['official_events']), 2)

    def test_unscanned_partition_suppresses_nonzero_membership_agreement(self):
        before, after = pair([poi(1), poi(2)], [poi(2), poi(3)])
        capture = bundle(before, after, [event(1, 'removed'),
            event(2, 'unchanged'), event(3, 'added')])
        capture['query']['all_partitions_scanned'] = False
        report = run(before, after, capture)
        self.assertEqual(report['official']['status'], 'PARTIAL_SCOPE')
        self.assertEqual(report['official']['missing_union_ids'], 0)
        self.assertIsNone(report['official']['membership_agreement_fraction'])
        self.assertEqual(report['official']['membership_comparable_ids'], 0)
        self.assertIsNone(report['physical_closures'])


if __name__ == '__main__':
    unittest.main()
