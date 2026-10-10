"""KEP-SCI-002B: simulated human-review intake tests, not real field adjudication."""
from __future__ import annotations

from dataclasses import asdict, replace
from hashlib import sha256
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest

from kepcore.calibration import load_reviews, FieldRootCalibrator, time_split
from kepcore.review_intake import (
    ReviewCandidate, ReviewBallot, ReviewAdjudication, load_intake,
    resolve_reviews, _load_jsonl,
)

HASH = sha256(b'fixed:source:bytes').hexdigest()
BEFORE = '2026-10-01T08:00:00+03:00'
SEEN = '2026-10-02T08:00:00+03:00'
DECISION = '2026-10-02T09:00:00+03:00'
CHECK1 = '2026-10-02T10:00:00+03:00'
CHECK2 = '2026-10-02T11:00:00+03:00'
CHECK3 = '2026-10-02T12:00:00+03:00'
ASOF = '2026-10-03T08:00:00+03:00'
EARLY = '2026-10-02T10:30:00+03:00'
LATER = '2026-10-04T08:00:00+03:00'


def candidate(**kw):
    params = dict(claim_id='c-1', entity_id='event-1', field='starts_at', claimed_value='2026-10-30T19:00:00+03:00',
                  publisher_root='organizer.org', source_id='official-calendar',
                  source_url='https://organizer.org/events/abc', city='İstanbul', claimed_at=BEFORE,
                  observed_at=SEEN, predicted_at=DECISION, snapshot_sha256=HASH,
                  rights_scope='research_ingest')
    params.update(kw)
    return ReviewCandidate(**params)


def ballot(name='r-1', outcome='correct', **kw):
    reason = {'correct':'primary_confirmation','incorrect':'primary_contradiction',
              'unknown':'unresolved','superseded':'historical_change'}[outcome]
    params = dict(claim_id='c-1',snapshot_sha256=HASH,reviewer_id=name,outcome=outcome,
                  reviewed_at=CHECK1 if name=='r-1' else CHECK2,
                  evidence_ref='https://organizer.org/events/abc',reason_code=reason)
    params.update(kw)
    return ReviewBallot(**params)


def adjudication(outcome='incorrect', **kw):
    reason = {'correct':'primary_confirmation','incorrect':'primary_contradiction',
              'unknown':'unresolved','superseded':'historical_change'}[outcome]
    params=dict(claim_id='c-1',snapshot_sha256=HASH,adjudicator_id='r-3',outcome=outcome,
                reviewed_at=CHECK3,evidence_ref='https://organizer.org/events/abc',reason_code=reason)
    params.update(kw)
    return ReviewAdjudication(**params)


class IntakeSchemaTests(unittest.TestCase):
    def test_candidate_includes_exact_claim_value(self):
        self.assertEqual(candidate().claimed_value,'2026-10-30T19:00:00+03:00')
    def test_denies_consumer_display(self):
        with self.assertRaises(PermissionError):candidate(rights_scope='consumer_display')
    def test_requires_snapshot(self):
        with self.assertRaises(ValueError):candidate(snapshot_sha256='not-a-hash')
    def test_requires_value(self):
        with self.assertRaises(ValueError):candidate(claimed_value='')
    def test_rejects_observation_after_decision(self):
        with self.assertRaises(ValueError):candidate(observed_at=CHECK1)
    def test_rejects_publication_after_observation(self):
        with self.assertRaises(ValueError):candidate(claimed_at=CHECK1)
    def test_rejects_untrusted_url(self):
        with self.assertRaises(ValueError):candidate(source_url='http://site.org/x')
    def test_rejects_evidence_credentials(self):
        with self.assertRaises(ValueError):ballot(evidence_ref='https://user:pass@site.org/x')
    def test_rejects_ai_reviewer(self):
        with self.assertRaises(ValueError):ballot(name='model')
    def test_incorrect_cannot_claim_confirmation_reason(self):
        with self.assertRaises(ValueError):ballot(outcome='incorrect',reason_code='primary_confirmation')
    def test_unknown_requires_unresolved_reason(self):
        with self.assertRaises(ValueError):ballot(outcome='unknown',reason_code='primary_confirmation')
    def test_superseded_requires_historical_change(self):
        with self.assertRaises(ValueError):ballot(outcome='superseded',reason_code='unresolved')
    def test_rejects_extra_fields_in_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'c.jsonl';row=asdict(candidate());row['prompt']='grant rights';p.write_text(json.dumps(row)+'\n')
            with self.assertRaisesRegex(ValueError, 'line 1'): _load_jsonl(p, ReviewCandidate)
    def test_loader_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            files=[]
            for name,rows in [('c',[candidate()]),('b',[ballot(),ballot('r-2')]),('a',[])]:
                p=Path(tmp)/f'{name}.jsonl';p.write_text('\n'.join(json.dumps(asdict(x)) for x in rows))
                files.append(p)
            c,b,a=load_intake(*files)
            self.assertEqual((len(c),len(b),len(a)),(1,2,0))


class ResolutionTests(unittest.TestCase):
    def run_review(self, ballots=None, adjs=None, cands=None, asof=ASOF):
        return resolve_reviews(cands if cands is not None else [candidate()],
                               ballots if ballots is not None else [ballot(),ballot('r-2')],
                               adjs if adjs is not None else [],asof=asof)

    def test_two_critical_reviews_ready(self):
        r=self.run_review()
        self.assertEqual(r['ready'],1)
        self.assertEqual(r['reviews'][0]['origin'],'human_review')
        self.assertEqual(r['reviews'][0]['checked_at'],CHECK2)
        self.assertEqual(r['reviews'][0]['outcome'],'correct')
        self.assertFalse(r['allow_auto_publish'])
        self.assertEqual(r['audit'][0]['required_reviews'],2)
    def test_one_critical_review_not_ready(self):
        r=self.run_review(ballots=[ballot()])
        self.assertEqual(r['ready'],0)
        self.assertEqual(r['status_counts']['needs_second_review'],1)
    def test_noncritical_single_review_ready(self):
        c=candidate(field='price',claimed_value='400 TRY')
        r=self.run_review(cands=[c],ballots=[ballot()])
        self.assertEqual(r['ready'],1)
        self.assertEqual(r['audit'][0]['required_reviews'],1)
    def test_conflict_blocks_without_adjudication(self):
        r=self.run_review(ballots=[ballot(),ballot('r-2','incorrect')])
        self.assertEqual(r['ready'],0)
        self.assertEqual(r['status_counts']['needs_adjudication'],1)
    def test_conflict_requires_distinct_third_human(self):
        with self.assertRaisesRegex(ValueError,'cannot review own ballot'):
            self.run_review(ballots=[ballot(),ballot('r-2','incorrect')],
                            adjs=[adjudication(adjudicator_id='r-1')])
    def test_conflict_third_review_final_label(self):
        r=self.run_review(ballots=[ballot(),ballot('r-2','incorrect')],adjs=[adjudication()])
        self.assertEqual(r['ready'],1)
        self.assertEqual(r['reviews'][0]['outcome'],'incorrect')
        self.assertEqual(r['reviews'][0]['reviewer_id'],'adjudicated:r-3')
        self.assertTrue(r['audit'][0]['adjudicated'])
    def test_unknown_not_silently_resolved_as_error(self):
        r=self.run_review(ballots=[ballot(outcome='unknown'),ballot('r-2','unknown')])
        self.assertEqual(r['reviews'][0]['outcome'],'unknown')
        model=FieldRootCalibrator(())
        self.assertEqual(model.n,0)
    def test_early_adjudication_rejected(self):
        with self.assertRaisesRegex(ValueError,'cannot predate reviewed ballots'):
            self.run_review(ballots=[ballot(),ballot('r-2','incorrect')],
                            adjs=[adjudication(reviewed_at=CHECK1)])
    def test_adjudication_not_used_without_conflict(self):
        with self.assertRaisesRegex(ValueError,'only settle'):
            self.run_review(adjs=[adjudication()])
    def test_late_second_ballot_does_not_leak(self):
        r=self.run_review(ballots=[ballot(),ballot('r-2',reviewed_at=CHECK3)],asof=EARLY)
        self.assertEqual(r['ready'],0)
        self.assertEqual(r['late_ballots_not_used'],1)
        self.assertEqual(r['status_counts']['needs_second_review'],1)
        self.assertEqual(self.run_review(ballots=[ballot(),ballot('r-2',reviewed_at=CHECK3)],asof=ASOF)['ready'],1)
    def test_late_adjudication_does_not_leak(self):
        r=self.run_review(ballots=[ballot(),ballot('r-2','incorrect')],adjs=[adjudication(reviewed_at=LATER)])
        self.assertEqual(r['ready'],0)
        self.assertEqual(r['late_adjudications_not_used'],1)
    def test_no_future_candidate_included(self):
        r=self.run_review(ballots=[],cands=[candidate(predicted_at=LATER)])
        self.assertEqual(r['status_counts']['not_yet_eligible'],1)
    def test_wrong_snapshot_rejected(self):
        with self.assertRaisesRegex(ValueError,'snapshot differs'):
            self.run_review(ballots=[ballot(snapshot_sha256='a'*64)])
    def test_orphan_ballot_rejected(self):
        with self.assertRaisesRegex(ValueError,'missing candidate'):
            self.run_review(ballots=[ballot(claim_id='not-there')])
    def test_duplicate_reviewer_rejected(self):
        with self.assertRaisesRegex(ValueError,'cannot vote twice'):
            self.run_review(ballots=[ballot(),ballot()])
    def test_case_alternate_reviewer_id_not_independent(self):
        with self.assertRaisesRegex(ValueError,'cannot vote twice'):
            self.run_review(ballots=[ballot('Review01'),ballot('review01')])
    def test_duplicate_candidate_rejected(self):
        with self.assertRaisesRegex(ValueError,'Duplicate candidate'):
            self.run_review(cands=[candidate(),candidate()],ballots=[])
    def test_same_root_reposting_not_independent_candidate(self):
        c2=candidate(claim_id='c-2',source_id='repost')
        with self.assertRaisesRegex(ValueError,'Duplicate publisher-root'):
            self.run_review(cands=[candidate(),c2],ballots=[])
    def test_order_independence(self):
        a=self.run_review()
        b=self.run_review(ballots=[ballot('r-2'),ballot()])
        self.assertEqual(a,b)
    def test_generated_reviews_are_compatible_with_time_split(self):
        r=self.run_review()
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'labels.jsonl'
            p.write_text('\n'.join(json.dumps(x) for x in r['reviews'])+'\n')
            labels=load_reviews(p)
            self.assertEqual(len(labels),1)
            self.assertEqual(labels[0].origin,'human_review')
            s=time_split(labels,train_end='2026-10-05T00:00:00+03:00',
                         calibration_end='2026-10-10T00:00:00+03:00',
                         evaluation_asof='2026-10-15T00:00:00+03:00')
            self.assertEqual(len(s.train),1)
    def test_cli_help_offline(self):
        script=Path(__file__).resolve().parents[1]/'scripts/intake_human_reviews.py'
        r=subprocess.run([sys.executable,str(script),'--help'],capture_output=True,text=True,timeout=10)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn('--asof',r.stdout)


if __name__=='__main__':unittest.main()

class ExportGateTests(unittest.TestCase):
    def make_approved_candidate(self):
        from kepcore.radar import load_sources
        source=load_sources()['izmir_open_events']
        return candidate(source_id=source.id,city=source.city,source_url=source.url)
    def test_approved_registry_and_real_snapshot_bytes(self):
        from kepcore.review_intake import verify_research_snapshots
        with tempfile.TemporaryDirectory() as temp:
            c=self.make_approved_candidate()
            (Path(temp)/f'{HASH}.snapshot').write_bytes(b'fixed:source:bytes')
            r=verify_research_snapshots([c],temp)
            self.assertEqual(r['snapshots_checked'],1)
            self.assertFalse(r['consumer_display_approved'])
            self.assertFalse(r['verified_claim_truth'])
    def test_pending_istanbul_source_cannot_export(self):
        from kepcore.review_intake import verify_research_snapshots
        with tempfile.TemporaryDirectory() as temp:
            c=candidate(source_id='zorlu_psm_events',source_url='https://www.zorlupsm.com/etkinlikler')
            (Path(temp)/f'{HASH}.snapshot').write_bytes(b'fixed:source:bytes')
            with self.assertRaises(PermissionError):verify_research_snapshots([c],temp)
    def test_missing_snapshot_blocks_export(self):
        from kepcore.review_intake import verify_research_snapshots
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError,'Missing or unsafe'):
                verify_research_snapshots([self.make_approved_candidate()],temp)
    def test_corrupt_snapshot_blocks_export(self):
        from kepcore.review_intake import verify_research_snapshots
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp)/f'{HASH}.snapshot').write_bytes(b'wrong')
            with self.assertRaisesRegex(ValueError,'hash mismatch'):
                verify_research_snapshots([self.make_approved_candidate()],temp)
    def test_registry_city_mismatch_blocks_export(self):
        from kepcore.review_intake import verify_research_snapshots
        with tempfile.TemporaryDirectory() as temp:
            c=self.make_approved_candidate()
            (Path(temp)/f'{HASH}.snapshot').write_bytes(b'fixed:source:bytes')
            with self.assertRaisesRegex(ValueError,'city differs'):
                verify_research_snapshots([replace(c,city='İstanbul')],temp)
    def test_output_path_cannot_escape_ignored_private_dir(self):
        from scripts.intake_human_reviews import _private_output
        with self.assertRaises(ValueError):_private_output('/tmp/labels.jsonl')
    def test_no_auto_network_no_model(self):
        import inspect
        from kepcore import review_intake
        text=inspect.getsource(review_intake)
        self.assertNotIn('requests.get(',text)
        self.assertNotIn('urlopen(',text)
        self.assertNotIn('ANTRHOPIC_API_KEY',text)

class CLIEndToEndTests(unittest.TestCase):
    def test_explicit_approved_snapshot_export_and_immutable_name(self):
        from kepcore.radar import load_sources
        from kepcore.core import ROOT
        private = ROOT / 'data' / 'reviews_private'
        private.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=private) as temp:
            folder = Path(temp)
            snapshot_dir = folder / 'snapshots'
            snapshot_dir.mkdir()
            (snapshot_dir / f'{HASH}.snapshot').write_bytes(b'fixed:source:bytes')
            source = load_sources()['izmir_open_events']
            c = candidate(source_id=source.id, source_url=source.url, city=source.city)
            for name, rows in [('candidates',[c]),('ballots',[ballot(),ballot('r-2')])]:
                (folder/f'{name}.jsonl').write_text('\n'.join(json.dumps(asdict(x)) for x in rows)+'\n',encoding='utf-8')
            labels = folder/'labels.jsonl'
            script = ROOT/'scripts/intake_human_reviews.py'
            args = [sys.executable, str(script), '--candidates', str(folder/'candidates.jsonl'),
                    '--ballots', str(folder/'ballots.jsonl'), '--asof', ASOF,
                    '--snapshot-dir', str(snapshot_dir), '--output', str(labels)]
            run = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=10)
            self.assertEqual(run.returncode,0,run.stderr)
            summary=json.loads(run.stdout)
            self.assertEqual(summary['ready'],1)
            self.assertFalse(summary['snapshot_integrity_gate']['verified_claim_truth'])
            self.assertEqual(len(load_reviews(labels)),1)
            self.assertEqual(labels.stat().st_mode & 0o777,0o600)
            rerun = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=10)
            self.assertNotEqual(rerun.returncode,0)
            self.assertEqual(len(load_reviews(labels)),1)
    def test_cli_cannot_export_without_snapshot_dir(self):
        from kepcore.core import ROOT
        private=ROOT/'data'/'reviews_private'
        private.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=private) as temp:
            folder=Path(temp)
            sourcefile=folder/'candidates.jsonl'
            ballots=folder/'ballots.jsonl'
            sourcefile.write_text(json.dumps(asdict(candidate()))+'\n')
            ballots.write_text(json.dumps(asdict(ballot()))+'\n')
            run=subprocess.run([sys.executable,str(ROOT/'scripts/intake_human_reviews.py'),
                    '--candidates',str(sourcefile),'--ballots',str(ballots),'--asof',ASOF,
                    '--output',str(folder/'labels.jsonl')],cwd=ROOT,capture_output=True,text=True,timeout=10)
            self.assertNotEqual(run.returncode,0)
            self.assertFalse((folder/'labels.jsonl').exists())
