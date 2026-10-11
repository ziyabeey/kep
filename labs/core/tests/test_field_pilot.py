"""All reviewer ballots in these tests are SYNTHETIC, never field evidence."""
from __future__ import annotations
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kepcore.field_pilot import protocol, evaluate_pilot
from kepcore.overture_real import DATA_DIR, prepare_private_audit, load_archive
from kepcore.overture_places import canonical
from tests.test_overture_field_review import make_book, AT, EVAL


class FieldPilotContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.seed = 'KEP-FIELD-001-PUBLIC-SYNTHETIC-TEST-SEED'
        cls.freeze = prepare_private_audit(DATA_DIR, budget=60, seed=cls.seed, sampled_at=AT)
        cls.plan = cls.freeze['plan']
        cls.ids = [r['overture_id'] for r in cls.plan['selected']]
        doc, _, _ = load_archive(DATA_DIR)
        cls.lookup = {r['overture_id']: r for r in doc['records']}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.private_plan = self.root / 'audit_plan_unlabeled.json'
        self.private_plan.write_bytes(canonical(self.plan))
        self.seed_file = self.root / 'secret.txt'
        self.seed_file.write_text(self.seed)
        self.book_a = self.root / 'Reviewer_A.xlsx'
        self.book_b = self.root / 'Reviewer_B.xlsx'

    def render(self, votes_a=None, votes_b=None):
        make_book(self.book_a, 'A', self.plan, self.lookup, votes=votes_a)
        make_book(self.book_b, 'B', self.plan, self.lookup, votes=votes_b)

    def evaluate(self):
        return evaluate_pilot(
            reviewer_a=self.book_a, reviewer_b=self.book_b,
            audit_plan=self.private_plan, seed_file=self.seed_file,
            evaluation_asof=EVAL,
        )

    def test_protocol_requires_no_network_and_no_labels(self):
        with patch('urllib.request.OpenerDirector.open', side_effect=AssertionError('NETWORK')):
            p = protocol()
        self.assertEqual(p['human_verified_labels'], 0)
        self.assertEqual(p['kep_automatic_assertions'], 0)
        self.assertIsNone(p['source_nonexistence_estimate'])
        self.assertIsNone(p['business_closures_accuracy'])
        self.assertEqual(len(p['policies']), 2)
        self.assertNotIn('overture_id', json.dumps(p))

    def test_real_60_source_rows_blank_review_denies_error_rate(self):
        self.render()
        r = self.evaluate()
        self.assertEqual(r['population_n'], 4803)
        self.assertEqual(r['sample_n'], 60)
        self.assertEqual(r['status'], 'INCOMPLETE_BLIND_AUDIT')
        self.assertEqual(r['missing_or_late'], 60)
        self.assertIsNone(r['naive_source_nonexistence_fraction'])
        self.assertIsNone(r['kep_predictive_accuracy'])
        self.assertEqual(r['baseline_always_asserts_existence_n'], 60)
        self.assertEqual(r['kep_current_unverified_source_automatic_existence_assertions_n'], 0)
        self.assertFalse(r['consumer_publish'])
        output = json.dumps(r)
        self.assertNotIn(self.seed, output)
        self.assertNotIn(self.ids[0], output)
        self.assertNotIn('example.org', output)

    def test_partial_synthetic_ballots_do_not_become_accuracy(self):
        one = {self.ids[0]: 'exists'}
        self.render(one, one)
        r = self.evaluate()
        self.assertEqual(r['reviewer_a_completed'], 1)
        self.assertEqual(r['concordant_resolved'], 1)
        self.assertEqual(r['missing_or_late'], 59)
        self.assertIsNone(r['naive_source_nonexistence_fraction'])

    def test_unknown_synthetic_ballot_keeps_rate_null(self):
        x = {rid: 'exists' for rid in self.ids}
        x[self.ids[0]] = 'unknown'
        self.render(x, x)
        r = self.evaluate()
        self.assertEqual(r['unknown_responses'], 1)
        self.assertIsNone(r['naive_source_nonexistence_fraction'])

    def test_full_synthetic_review_produces_provisional_source_rate_only(self):
        x = {rid: 'exists' for rid in self.ids}
        self.render(x, x)
        r = self.evaluate()
        self.assertEqual(r['concordant_resolved'], 60)
        self.assertEqual(r['naive_source_nonexistence_fraction'], 0)
        self.assertFalse(r['independent_human_field_truth_authenticated'])
        self.assertIsNone(r['kep_predictive_accuracy'])
        self.assertIsNone(r['real_openings_accuracy'])
        self.assertEqual(r['status'], 'ALL_BALLOTS_RESOLVED_INDEPENDENCE_REQUIRES_MANUAL_ATTESTATION')

    def test_synthetic_reported_nonexistence_is_not_physical_closure(self):
        x = {rid: 'exists' for rid in self.ids}
        x[self.ids[0]] = 'does_not_exist'
        self.render(x, x)
        r = self.evaluate()
        self.assertGreater(r['naive_source_nonexistence_fraction'], 0)
        self.assertIsNone(r['real_closures_accuracy'])
        self.assertFalse(r['consumer_publish'])

    def test_seed_change_refuses_reselection(self):
        self.render()
        self.seed_file.write_text('different-seed-not-the-original')
        with self.assertRaises(ValueError):
            self.evaluate()

    def test_sample_mutation_denied(self):
        self.render()
        plan = json.loads(self.private_plan.read_text())
        plan['selected'][0]['overture_id'] = self.ids[-1]
        self.private_plan.write_bytes(canonical(plan))
        with self.assertRaises(ValueError):
            self.evaluate()

    def test_cli_default_is_offline(self):
        proc = subprocess.run(
            [sys.executable, 'scripts/evaluate_field_pilot.py', '--protocol'],
            capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertIsNone(report['source_nonexistence_estimate'])
        self.assertFalse(report['consumer_publish'])

    def test_cli_partial_or_conflicting_args_rejected(self):
        cmd = [sys.executable, 'scripts/evaluate_field_pilot.py']
        for options in (
            ['--reviewer-a', str(self.book_a)],
            ['--protocol', '--reviewer-a', str(self.book_a)],
        ):
            proc = subprocess.run(cmd + options, capture_output=True, text=True)
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn('error:', proc.stderr)


if __name__ == '__main__':
    unittest.main()
