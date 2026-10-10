"""KEP-SRC-001: transport-free policy, provenance and fetch contract tests."""
from __future__ import annotations
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from kepcore.core import load_json, ROOT
from kepcore.radar import (Source, PollState, FetchResponse, load_sources, poll, _public_https)

REGISTRY = load_sources()
NOW = datetime(2026,10,11,12,0,tzinfo=timezone.utc)


def sample_bytes():
    original = load_json(ROOT/'data/raw/izmir_events_excerpt.json')
    return json.dumps(original['records'][:2],ensure_ascii=False).encode()


class FakeTransport:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def __call__(self, url, headers, max_bytes):
        self.calls.append((url,dict(headers),max_bytes))
        return self.response


class RegistryTests(unittest.TestCase):
    def test_expected_sources_and_only_research_approved(self):
        self.assertEqual(len(REGISTRY),8)
        approved = [s.id for s in REGISTRY.values() if s.status=='approved']
        self.assertEqual(approved,['izmir_open_events'])
        self.assertTrue(REGISTRY['izmir_open_events'].allows('research_ingest'))
        self.assertFalse(REGISTRY['izmir_open_events'].allows('consumer_display'))
        self.assertTrue(all(not s.approved_uses for s in REGISTRY.values() if s.city=='İstanbul'))

    def test_no_url_for_local_or_non_https_or_credentials(self):
        for url in ['http://example.com', 'https://localhost/', 'https://127.0.0.1/',
                    'https://10.1.1.9/data', 'https://example.local/x',
                    'https://alice:secret@example.org/', 'https://example.org:8080/',
                    'https://example.org/path#fragment', 'https://example.com\\@evil.com']:
            with self.subTest(url=url),self.assertRaises(ValueError):
                _public_https(url)

    def test_approved_requires_documented_rights(self):
        d=dict(REGISTRY['izmir_open_events'].__dict__)
        d['rights_evidence_url']=''
        with self.assertRaises(ValueError):Source.parse(d)

    def test_pending_cannot_grant_uses(self):
        d=dict(REGISTRY['zorlu_psm_events'].__dict__)
        d['approved_uses']=['research_ingest']
        with self.assertRaises(ValueError):Source.parse(d)

    def test_duplicate_registry_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            original=load_json(ROOT/'sources/registry.json')['sources'][0]
            data={'version':1,'sources':[original,copy.deepcopy(original)]}
            p=Path(d)/'registry.json';p.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'Duplicate source ID'):load_sources(p)


class PollTests(unittest.TestCase):
    def setUp(self):
        self.source=REGISTRY['izmir_open_events']
        self.body=sample_bytes()

    def test_pending_blocked_before_network(self):
        fake=FakeTransport(FetchResponse(200,self.body))
        r=poll(REGISTRY['zorlu_psm_events'],now=NOW,state=PollState(),transport=fake)
        self.assertEqual(r.status,'denied');self.assertEqual(fake.calls,[])

    def test_display_rights_denied_before_network(self):
        fake=FakeTransport(FetchResponse(200,self.body))
        r=poll(self.source,now=NOW,state=PollState(),transport=fake,purpose='consumer_display')
        self.assertEqual(r.status,'denied');self.assertEqual(fake.calls,[])

    def test_changed_is_staged_and_not_approved_for_user(self):
        fake=FakeTransport(FetchResponse(200,self.body,{'ETag':'"abc"','Last-Modified':'Sun, 11 Oct 2026 00:00:00 GMT'}))
        r=poll(self.source,now=NOW,state=PollState(),transport=fake)
        self.assertEqual(r.status,'changed')
        self.assertEqual(len(r.envelope['records']),2)
        self.assertEqual(r.envelope['meta']['rights_scope'],'research_only')
        self.assertFalse(r.envelope['meta']['origin_live_verified'])
        self.assertIsNone(r.envelope['meta']['source_observed_at'])
        self.assertFalse(r.envelope['meta']['consumer_display_approved'])
        self.assertEqual(r.state.requests_today,1)
        self.assertEqual(r.state.etag,'"abc"')
        self.assertNotIn('food_rating',r.envelope['records'][0])

    def test_conditional_not_modified(self):
        first=poll(self.source,now=NOW,state=PollState(),transport=FakeTransport(FetchResponse(200,self.body,{'ETag':'"abc"'})))
        fake=FakeTransport(FetchResponse(304))
        second=poll(self.source,now=NOW+timedelta(hours=7),state=first.state,transport=fake)
        self.assertEqual(second.status,'not_modified')
        self.assertIn('If-None-Match',fake.calls[0][1])
        self.assertIsNone(second.envelope)
        self.assertEqual(second.state.requests_today,2)

    def test_identical_body_does_not_emit_new_snapshot(self):
        first=poll(self.source,now=NOW,state=PollState(),transport=FakeTransport(FetchResponse(200,self.body)))
        second=poll(self.source,now=NOW+timedelta(hours=7),state=first.state,transport=FakeTransport(FetchResponse(200,self.body)))
        self.assertEqual(second.status,'unchanged');self.assertIsNone(second.envelope)

    def test_min_interval_and_quota_prevent_network(self):
        fake=FakeTransport(FetchResponse(200,self.body))
        state=PollState(last_attempt_at=NOW.isoformat(),last_day=NOW.date().isoformat(),requests_today=1)
        early=poll(self.source,now=NOW+timedelta(minutes=20),state=state,transport=fake)
        self.assertEqual(early.status,'skipped')
        quota=PollState(last_day=NOW.date().isoformat(),requests_today=self.source.daily_request_cap)
        capped=poll(self.source,now=NOW,state=quota,transport=fake)
        self.assertEqual(capped.status,'skipped')
        self.assertEqual(fake.calls,[])

    def test_403_429_pause_until_manual_review(self):
        for status in (403,429):
            with self.subTest(status=status):
                first=poll(self.source,now=NOW,state=PollState(),transport=FakeTransport(FetchResponse(status)))
                self.assertEqual(first.status,'paused')
                self.assertIsNotNone(first.state.paused_reason)
                fake=FakeTransport(FetchResponse(200,self.body))
                second=poll(self.source,now=NOW+timedelta(hours=12),state=first.state,transport=fake)
                self.assertEqual(second.status,'paused')
                self.assertEqual(fake.calls,[])

    def test_suspicious_empty_or_schema_break_keeps_feed_in_review(self):
        for body in [b'[]', b'{}', b'{bad json}',b'[{"Id": 1}]']:
            with self.subTest(body=body):
                r=poll(self.source,now=NOW,state=PollState(),transport=FakeTransport(FetchResponse(200,body)))
                self.assertEqual(r.status,'paused');self.assertIsNone(r.envelope)

    def test_transport_failure_is_bounded_and_does_not_publish(self):
        calls=[]
        def fail(url,headers,max_bytes):
            calls.append(url)
            raise TimeoutError('timeout')
        result=poll(self.source,now=NOW,state=PollState(),transport=fail)
        self.assertEqual(result.status,'error')
        self.assertEqual(result.state.requests_today,1)
        self.assertIsNone(result.envelope)
        self.assertEqual(calls,[self.source.url])

    def test_oversized_response_paused(self):
        body=b'x'*(self.source.max_response_bytes+1)
        result=poll(self.source,now=NOW,state=PollState(),transport=FakeTransport(FetchResponse(200,body)))
        self.assertEqual(result.status,'paused')

    def test_invalid_date_fails_before_publishing(self):
        sample=json.loads(self.body)
        sample[0]['EtkinlikBaslamaTarihi']='not-a-date'
        result=poll(self.source,now=NOW,state=PollState(),transport=FakeTransport(FetchResponse(200,json.dumps(sample).encode())))
        self.assertEqual(result.status,'paused')

    def test_source_missing_or_invalid_ids_rejected(self):
        sample=json.loads(self.body)
        sample[1]['Id']=sample[0]['Id']
        result=poll(self.source,now=NOW,state=PollState(),transport=FakeTransport(FetchResponse(200,json.dumps(sample).encode())))
        self.assertEqual(result.status,'paused')

    def test_no_network_default_cli(self):
        p=subprocess.run([sys.executable,str(ROOT/'scripts/poll_source.py'),'--source','izmir_open_events'],capture_output=True,text=True,check=True)
        result=json.loads(p.stdout)
        self.assertFalse(result['network_used']);self.assertEqual(result['status'],'dry_run')

    def test_cli_list_all_sources_without_network(self):
        p=subprocess.run([sys.executable,str(ROOT/'scripts/poll_source.py'),'--list'],capture_output=True,text=True,check=True)
        self.assertEqual(len(json.loads(p.stdout)),8)


if __name__ == '__main__':unittest.main()
