"""Read-only browser scout contract tests; no browser, API or internet."""
import json
import unittest
from pathlib import Path
from dataclasses import replace
from kepcore.radar import Source, load_sources
from kepcore.scout import inspect_html, evaluate_scout, _date_precision, content_sha256
from benchmarks.scout_eval import benchmark

CASES=json.loads((Path(__file__).resolve().parents[1]/'benchmarks/fixtures/scout/cases.json').read_text())['cases']
SRC=Source(id='scout_test',url='https://events.example.org/program', city='Test',
           format='website_review_required',status='approved',approved_uses=('research_ingest',),
           license='synthetic',rights_evidence_url='https://example.org/rights',rights_reviewed_at='2026-10-10')


class ScoutTests(unittest.TestCase):
    def test_jsonld_event(self):
        r=evaluate_scout(SRC,CASES[0]['html'],mode='script')
        self.assertEqual(len(r.candidates),1)
        self.assertTrue(r.candidates[0].review_required)
        self.assertEqual(r.candidates[0].date_precision,'datetime')

    def test_nested_graph_deduplicated(self):
        r=evaluate_scout(SRC,CASES[2]['html'],mode='script')
        self.assertEqual(len(r.candidates),1)
        self.assertEqual(r.candidates[0].date_precision,'date')

    def test_dom_only_script_cannot_claim_success(self):
        r=evaluate_scout(SRC,CASES[1]['html'],mode='script')
        self.assertEqual(r.status,'empty')

    def test_replay_evidence_and_hybrid_fallback(self):
        r=evaluate_scout(SRC,CASES[1]['html'],mode='hybrid',replay=CASES[1]['replay'])
        self.assertTrue(r.browser_needed)
        self.assertEqual(len(r.candidates),1)
        self.assertEqual(r.candidates[0].method,'offline_manual_replay')

    def test_prompt_injection_is_not_followed(self):
        r=evaluate_scout(SRC,CASES[4]['html'],mode='manual_replay',replay=CASES[4]['replay'])
        self.assertEqual([c.title for c in r.candidates],['Resim Sergisi'])

    def test_invalid_date_not_fixed_with_guess(self):
        r=evaluate_scout(SRC,CASES[3]['html'],mode='hybrid',replay=[])
        self.assertEqual(r.status,'needs_review')

    def test_cancelled_remains_cancelled(self):
        r=evaluate_scout(SRC,CASES[5]['html'],mode='script')
        self.assertEqual(r.candidates[0].event_state,'cancelled')
        self.assertTrue(r.candidates[0].review_required)

    def test_pending_registry_sources_rejected_before_extract(self):
        source=load_sources()['zorlu_psm_events']
        r=evaluate_scout(source,CASES[0]['html'],mode='hybrid',replay=[])
        self.assertEqual(r.status,'denied')
        self.assertFalse(r.browser_needed)

    def test_bad_source_purpose_rejected(self):
        r=evaluate_scout(replace(SRC,approved_uses=('consumer_display',)),CASES[0]['html'],mode='script')
        self.assertEqual(r.status,'denied')

    def test_untrusted_replay_quote_cannot_invent(self):
        r=evaluate_scout(SRC,CASES[1]['html'],mode='manual_replay',replay=[{'title':'Wrong','starts_at':'2026-10-25','venue':'Atölye S','observed_date':'2026-10-25','quote':'wrong'}])
        self.assertFalse(r.candidates)

    def test_naive_datetime_is_invalid(self):
        self.assertIsNone(_date_precision('2026-10-25T20:00:00'))
        self.assertEqual(_date_precision('2026-10-25'),'date')
        self.assertIsNone(_date_precision('2026-02-30'))

    def test_markup_size_limited(self):
        with self.assertRaises(ValueError): inspect_html('x'*250000,SRC.url)

    def test_no_script_execution(self):
        called=[]
        html='<script>called.append("bad")</script><p>Etkinlik</p>'
        items,visible=inspect_html(html,SRC.url)
        self.assertEqual(items,())
        self.assertNotIn('called.append',visible)
        self.assertEqual(called,[])

    def test_content_hash_is_stable(self):
        self.assertEqual(content_sha256(CASES[0]['html']), content_sha256(CASES[0]['html']))

    def test_offline_comparison_labels_cost_as_zero(self):
        r=benchmark()
        self.assertEqual(r['case_count'],6)
        self.assertEqual([i['mode'] for i in r['results']],['script','manual_replay','hybrid'])
        self.assertTrue(all(i['real_model_calls']==0 and i['real_browser_calls']==0 for i in r['results']))
        self.assertEqual([i['hits'] for i in r['results']],[3,2,5])

if __name__=='__main__':unittest.main()
