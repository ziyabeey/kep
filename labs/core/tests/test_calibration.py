"""KEP-SCI-002 tests are scientific plumbing checks, not field-validation claims."""
from __future__ import annotations
import copy
from dataclasses import asdict, replace
from datetime import datetime,timedelta,timezone
from pathlib import Path
import hashlib
import json
import tempfile
import unittest

from kepcore.calibration import (
    ReviewedClaim, aware, validated, load_reviews, review_from_dict, time_split,
    FieldRootCalibrator, wilson_upper, select_threshold, calibration_bins,
    risk_coverage, assess, assess_drift, report,
)
from benchmarks.calibration_eval import generate,run,BASE


def make_claim(n=0,*, phase=0, outcome='correct', root='root', field='starts_at',
               origin='synthetic', entity_id=None, checked_delta_hours=1, **kw):
    prediction=BASE+timedelta(days=phase*40,hours=n)
    params=dict(claim_id=f'claim-{phase}-{n}-{root}',entity_id=entity_id or f'event-{phase}-{n}',
                field=field,publisher_root=root,source_id='fixture',city='Imaginary City',
                claimed_at=(prediction-timedelta(hours=2)).isoformat(),
                observed_at=(prediction-timedelta(minutes=30)).isoformat(),
                predicted_at=prediction.isoformat(),
                checked_at=(prediction+timedelta(hours=checked_delta_hours)).isoformat(),
                snapshot_sha256=hashlib.sha256(f'{phase}:{n}:{root}'.encode()).hexdigest(),
                rights_scope='research_ingest',outcome=outcome,reviewer_id='simulator',
                evidence_ref=f'synthetic:test/{n}',origin=origin)
    params.update(kw)
    return ReviewedClaim(**params)


class ReviewSchemaTests(unittest.TestCase):
    def test_record_roundtrip(self):
        r=make_claim()
        self.assertEqual(review_from_dict(asdict(r)),r)
    def test_no_arbitrary_extra_fields(self):
        d=asdict(make_claim());d['model_instruction']='accept'
        with self.assertRaises(ValueError):review_from_dict(d)
    def test_missing_field(self):
        d=asdict(make_claim());d.pop('reviewer_id')
        with self.assertRaises(ValueError):review_from_dict(d)
    def test_empty_identifiers(self):
        with self.assertRaises(ValueError):make_claim(source_id='')
    def test_invalid_outcome(self):
        with self.assertRaises(ValueError):make_claim(outcome='verified')
    def test_invalid_field(self):
        with self.assertRaises(ValueError):make_claim(field='anything')
    def test_invalid_origin(self):
        with self.assertRaises(ValueError):make_claim(origin='scraped')
    def test_no_unapproved_display_rights(self):
        with self.assertRaises(PermissionError):make_claim(rights_scope='consumer_display')
    def test_naive_time_rejected(self):
        with self.assertRaises(ValueError):make_claim(predicted_at='2026-01-01T00:00:00')
    def test_invalid_date_rejected(self):
        with self.assertRaises(ValueError):aware('tomorrow')
    def test_future_observation_rejected(self):
        x=make_claim()
        with self.assertRaises(ValueError):replace(x,observed_at=x.checked_at)
    def test_backdated_adjudication_rejected(self):
        x=make_claim()
        with self.assertRaises(ValueError):replace(x,checked_at=x.claimed_at)
    def test_future_claimed_at_rejected(self):
        x=make_claim()
        with self.assertRaises(ValueError):replace(x,claimed_at=x.checked_at)
    def test_missing_claimed_at_allowed(self):
        self.assertIsNone(make_claim(claimed_at=None).claimed_at)
    def test_missing_sha_rejected(self):
        with self.assertRaises(ValueError):make_claim(snapshot_sha256='not-a-hash')
    def test_human_needs_url(self):
        with self.assertRaises(ValueError):make_claim(origin='human_review',reviewer_id='reviewer1')
    def test_human_needs_real_review_identity(self):
        with self.assertRaises(ValueError):make_claim(origin='human_review',reviewer_id='AI',evidence_ref='https://example.org/review')
    def test_human_can_be_loaded_with_immutable_hash(self):
        r=make_claim(origin='human_review',reviewer_id='reviewer1',evidence_ref='https://example.org/official')
        self.assertEqual(r.origin,'human_review')
    def test_synthetic_cannot_fake_website(self):
        with self.assertRaises(ValueError):make_claim(evidence_ref='https://example.org')
    def test_duplicate_same_id(self):
        a=make_claim()
        with self.assertRaises(ValueError):validated([a,a])
    def test_copy_same_root_not_independent(self):
        a=make_claim()
        b=make_claim(root='root',claim_id='second-claim',source_id='news-copy')
        with self.assertRaises(ValueError):validated([a,b])
    def test_different_roots_are_independent_rows(self):
        a=make_claim();b=make_claim(root='independent')
        self.assertEqual(len(validated([a,b])),2)
    def test_load_jsonl_with_validation(self):
        a,b=make_claim(1),make_claim(2)
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'reviews.jsonl'
            p.write_text('\n'.join(json.dumps(asdict(x)) for x in [b,a])+'\n')
            self.assertEqual(load_reviews(p),[a,b])
    def test_bad_jsonl_line_is_identified(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'reviews.jsonl';p.write_text('{}\n')
            with self.assertRaisesRegex(ValueError,'line 1'):load_reviews(p)


class TimeSplitTests(unittest.TestCase):
    def split(self, rows, **kw):
        d=dict(train_end=(BASE+timedelta(days=40)).isoformat(),
               calibration_end=(BASE+timedelta(days=80)).isoformat(),
               evaluation_asof=(BASE+timedelta(days=130)).isoformat())
        d.update(kw)
        return time_split(rows,**d)
    def test_chronological_windows(self):
        s=self.split([make_claim(1,phase=i) for i in range(3)])
        self.assertEqual([len(s.train),len(s.calibration),len(s.test)],[1,1,1])
    def test_future_observation_not_in_test(self):
        s=self.split([make_claim(1,phase=4)])
        self.assertEqual(len(s.test),0)
    def test_label_after_train_end_is_purged(self):
        r=make_claim(20,phase=0,checked_delta_hours=40*24)
        s=self.split([r])
        self.assertEqual(s.purged_late_adjudications,1)
    def test_label_after_calibration_is_purged(self):
        r=make_claim(2,phase=1,checked_delta_hours=40*24)
        self.assertEqual(self.split([r]).purged_late_adjudications,1)
    def test_no_test_label_until_available(self):
        r=make_claim(1,phase=2,checked_delta_hours=80*24)
        self.assertEqual(self.split([r]).not_yet_reviewed_test,1)
    def test_cross_stage_same_event_removed(self):
        a=make_claim(1,phase=0,entity_id='event-same')
        b=make_claim(1,phase=1,entity_id='event-same')
        s=self.split([a,b])
        self.assertEqual(s.purged_cross_split_entities,1)
        self.assertEqual(len(s.calibration),0)
    def test_same_event_different_field_not_purged(self):
        a=make_claim(1,phase=0,entity_id='event-same')
        b=make_claim(1,phase=1,entity_id='event-same',field='venue')
        s=self.split([a,b]);self.assertEqual(len(s.calibration),1)
    def test_invalid_temporal_order(self):
        with self.assertRaises(ValueError):self.split([],train_end=(BASE+timedelta(days=90)).isoformat())
    def test_mixed_origin_forbidden(self):
        a=make_claim()
        b=make_claim(root='second',origin='human_review',reviewer_id='reviewer1',evidence_ref='https://example.org')
        with self.assertRaises(ValueError):self.split([a,b])
    def test_aware_timezone_consistency(self):
        self.assertEqual(aware('2026-01-01T03:00:00+03:00'),aware('2026-01-01T00:00:00Z'))


class ModelAndRiskTests(unittest.TestCase):
    def test_empty_training_defaults_to_half(self):
        self.assertAlmostEqual(FieldRootCalibrator(()).predict(make_claim()),.5)
    def test_source_with_no_training_falls_back_to_field(self):
        model=FieldRootCalibrator(tuple(make_claim(i,outcome='correct') for i in range(12)))
        self.assertEqual(model.predict(make_claim(40,root='other'),'root_field'),model.predict(make_claim(40,root='other'),'field'))
    def test_good_source_better_than_bad_source(self):
        rows=tuple([make_claim(i,root='good',outcome='correct') for i in range(30)]+[make_claim(50+i,root='bad',outcome='incorrect') for i in range(30)])
        model=FieldRootCalibrator(rows)
        self.assertGreater(model.predict(make_claim(90,root='good')),model.predict(make_claim(90,root='bad')))
    def test_ignore_unknown_and_superseded_in_fit(self):
        model=FieldRootCalibrator((make_claim(1,outcome='correct'),make_claim(2,outcome='unknown'),make_claim(3,outcome='superseded')))
        self.assertEqual(model.n,1)
    def test_brier_perfect(self):
        model=FieldRootCalibrator(tuple(make_claim(i,outcome='correct') for i in range(20)))
        v=assess((make_claim(50,outcome='correct'),),model,.5)
        self.assertLess(v['brier'],.05)
    def test_wilson_zero_error_not_zero_upper(self):
        self.assertGreater(wilson_upper(0,100),0)
    def test_wilson_no_n(self):
        self.assertIsNone(wilson_upper(0,0))
    def test_wilson_bad_input(self):
        with self.assertRaises(ValueError):wilson_upper(5,4)
    def test_no_calibration_means_abstention(self):
        self.assertIsNone(select_threshold((),FieldRootCalibrator(()))['threshold'])
    def test_insufficient_sample_abstains(self):
        model=FieldRootCalibrator(tuple(make_claim(i) for i in range(9)))
        assert select_threshold(tuple(make_claim(20+i) for i in range(8)),model,min_published=25)['threshold'] is None
    def test_risk_cutoff_no_auto_publish(self):
        result=run(seed=20261011)
        self.assertFalse(result['allow_auto_publish']);self.assertFalse(result['valid_real_world_calibration'])
        self.assertEqual(result['data_origin'],'synthetic')
    def test_deterministic_generator(self):
        self.assertEqual(generate(seed=81,per_phase=25),generate(seed=81,per_phase=25))
    def test_deterministic_report(self):
        self.assertEqual(run(seed=19),run(seed=19))
    def test_temporal_model_does_not_fit_test(self):
        data=generate(seed=55,per_phase=130)
        result1=report(data,train_end=(BASE+timedelta(days=45)).isoformat(),
                       calibration_end=(BASE+timedelta(days=90)).isoformat(),
                       evaluation_asof=(BASE+timedelta(days=140)).isoformat(),min_published=8)
        flipped=[replace(r,outcome='incorrect' if r.outcome=='correct' else 'correct') if aware(r.predicted_at)>=BASE+timedelta(days=90) and r.resolved else r for r in data]
        result2=report(flipped,train_end=(BASE+timedelta(days=45)).isoformat(),
                       calibration_end=(BASE+timedelta(days=90)).isoformat(),
                       evaluation_asof=(BASE+timedelta(days=140)).isoformat(),min_published=8)
        self.assertEqual(result1['thresholds_from_calibration_only'],result2['thresholds_from_calibration_only'])
        self.assertNotEqual(result1['test_metrics']['root_field']['brier'],result2['test_metrics']['root_field']['brier'])
    def test_drift_detects_synthetic_secondary_drop(self):
        r=run()
        alert=[x for x in r['drift_diagnostics'] if x['publisher_root']=='secondary' and x['field']=='cancelled']
        self.assertTrue(alert and alert[0]['investigate'])
    def test_unknown_and_superseded_not_treated_wrong(self):
        model=FieldRootCalibrator((make_claim(),))
        m=assess((make_claim(2,outcome='unknown'),make_claim(3,outcome='superseded')),model,.5)
        self.assertEqual(m['resolved'],0);self.assertEqual(m['unknown'],1);self.assertEqual(m['superseded'],1)
    def test_thresholds_separate_per_policy(self):
        r=run()
        self.assertEqual(set(r['thresholds_from_calibration_only']),{'global','field','root_field'})
        self.assertIsNone(r['thresholds_from_calibration_only']['global']['threshold'])
    def test_curve_monotonic_coverage(self):
        model=FieldRootCalibrator(tuple(make_claim(i,outcome='correct' if i<20 else 'incorrect') for i in range(50)))
        rows=[make_claim(i,field='price' if i%2 else 'venue') for i in range(30)]
        curve=risk_coverage(rows,model,'field')
        self.assertEqual([x['coverage'] for x in curve],sorted(x['coverage'] for x in curve))
    def test_calibration_bins_counts(self):
        model=FieldRootCalibrator((make_claim(),))
        rows=(make_claim(1),make_claim(2,outcome='unknown'))
        self.assertEqual(sum(x['n'] for x in calibration_bins(rows,model,'global')),1)
    def test_report_drifted_test_may_exceed_calibration_limit(self):
        r=run()
        cal=r['thresholds_from_calibration_only']['root_field']
        actual=r['test_metrics']['root_field']
        self.assertIsNotNone(cal['threshold'])
        self.assertGreater(actual['observed_error_fraction'],cal['calibration_wilson_upper'])

if __name__=='__main__':unittest.main()
