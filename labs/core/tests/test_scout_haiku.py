"""Haiku tool permission and budget tests, independent of Anthropic SDK."""
from dataclasses import replace
from pathlib import Path
import json
import subprocess
import sys
import unittest
from kepcore.radar import Source, load_sources
from kepcore.scout_haiku import (live_preflight, tool_action_approved,
                                 estimate_uncached_usd, BROWSER_CONFIGS,
                                 READ_ONLY_BROWSER_TOOLS, json_answer_candidates)

ROOT=Path(__file__).resolve().parents[1]
SOURCES=load_sources()
MOCK=Source(id='mock',url='https://events.example.org/program',city='Test',
            format='website_review_required', status='approved',approved_uses=('research_ingest',),
            license='fixture',rights_evidence_url='https://example.org/rights',rights_reviewed_at='2026-10-10')

class BrowserSecurity(unittest.TestCase):
    def test_source_rights_gate_blocks_known_istanbul_source(self):
        allowed,reason=live_preflight(SOURCES['zorlu_psm_events'],live=True,acknowledged=True,api_key_present=True)
        self.assertFalse(allowed)
        self.assertEqual(reason,'SOURCE_RIGHTS_NOT_APPROVED')

    def test_web_browser_rejects_api_source(self):
        allowed,reason=live_preflight(SOURCES['izmir_open_events'],live=True,acknowledged=True,api_key_present=True)
        self.assertFalse(allowed)
        self.assertEqual(reason,'BROWSER_NOT_NEEDED_FOR_STRUCTURED_SOURCE')

    def test_paid_run_requires_acknowledgement_and_key(self):
        self.assertEqual(live_preflight(MOCK,live=True,acknowledged=False,api_key_present=True)[1],'REQUIRES_NETWORK_SANDBOX_ACKNOWLEDGMENT')
        self.assertEqual(live_preflight(MOCK,live=True,acknowledged=True,api_key_present=False)[1],'ANTHROPIC_API_KEY_MISSING')
        self.assertTrue(live_preflight(MOCK,live=True,acknowledged=True,api_key_present=True)[0])

    def test_disabled_toolset_does_not_allow_navigation_changes(self):
        self.assertEqual(set(k for k,v in BROWSER_CONFIGS.items() if v['enabled']),READ_ONLY_BROWSER_TOOLS)
        for member in ('left_click','javascript_exec','file_upload','new_tab','form_input','type','key','screenshot','read_network'):
            self.assertFalse(tool_action_approved(member,{},MOCK.url,MOCK.url))

    def test_only_exact_navigate_url(self):
        self.assertTrue(tool_action_approved('navigate',{'url':MOCK.url},None,MOCK.url))
        for url in ('http://events.example.org/program','https://evil.example.org/program','https://events.example.org/other','https://events.example.org/program?x=1'):
            self.assertFalse(tool_action_approved('navigate',{'url':url},None,MOCK.url))
        self.assertFalse(tool_action_approved('get_page_text',{},'https://evil.example.org/page',MOCK.url))
        self.assertTrue(tool_action_approved('get_page_text',{},MOCK.url,MOCK.url))

    def test_default_cli_has_no_network_and_zero_model_calls(self):
        p=subprocess.run([sys.executable,str(ROOT/'scripts/haiku_browser_scout.py'),'--source','zorlu_psm_events'],capture_output=True,text=True,check=True)
        self.assertEqual(json.loads(p.stdout)['network_used'],False)
        self.assertEqual(json.loads(p.stdout)['model_calls'],0)

    def test_live_pending_fails_before_sdk_import(self):
        p=subprocess.run([sys.executable,str(ROOT/'scripts/haiku_browser_scout.py'),'--source','zorlu_psm_events','--live','--network-sandbox-confirmed'],capture_output=True,text=True)
        self.assertEqual(p.returncode,2)
        self.assertIn('SOURCE_RIGHTS_NOT_APPROVED',p.stdout)

    def test_price_is_per_single_prompt_tier(self):
        self.assertAlmostEqual(estimate_uncached_usd(100000,10000,max_single_prompt_tokens=50000),.015)
        self.assertAlmostEqual(estimate_uncached_usd(100000,10000,max_single_prompt_tokens=100001),.075)

    def test_model_output_is_candidate_only(self):
        obj={'events':[{'title':'Event A','starts_at':'2026-10-25','venue':'Salon M','source_quote':'Event A · Salon M'}]}
        out=json_answer_candidates(json.dumps(obj))
        self.assertEqual(out[0]['review_state'],'needs_human_review')
        self.assertEqual(json_answer_candidates('not JSON'),[])
        obj['events'][0]['starts_at']='tomorrow'
        self.assertEqual(json_answer_candidates(json.dumps(obj)),[])

if __name__=='__main__':unittest.main()
