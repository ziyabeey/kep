"""Reproducible *synthetic* scout policy comparison, no Anthropic call."""
from __future__ import annotations
from dataclasses import asdict
import json
from pathlib import Path
from kepcore.radar import Source
from kepcore.scout import evaluate_scout

BASE = Path(__file__).resolve().parent / 'fixtures/scout/cases.json'


def benchmark() -> dict:
    raw = json.loads(BASE.read_text(encoding='utf-8'))
    assert raw['origin'].startswith('hand-authored synthetic')
    source = Source(id='offline_fixture', url='https://events.example.org/program',
                    city='Test City', format='website_review_required', status='approved',
                    approved_uses=('research_ingest',), license='fixture / synthetic',
                    rights_evidence_url='https://example.org/rights', rights_reviewed_at='2026-10-10')
    summaries = []
    for mode in ('script', 'manual_replay', 'hybrid'):
        hit = false = misses = fallback = 0
        for case in raw['cases']:
            result = evaluate_scout(source, case['html'], replay=case['replay'], mode=mode)
            got = {(v.title, v.starts_at, v.venue) for v in result.candidates}
            gold = {(v['title'], v['starts_at'], v['venue']) for v in case['gold']}
            hit += len(got & gold)
            false += len(got - gold)
            misses += len(gold - got)
            fallback += int(result.browser_needed)
        summaries.append({'mode':mode,'hits':hit,'false_candidates':false,
                          'misses':misses,'simulated_fallbacks':fallback,
                          'real_model_calls':0, 'real_browser_calls':0})
    return {'benchmark':'SCOUT-SYNTHETIC-REPLAY-001','origin':raw['origin'],
            'case_count':len(raw['cases']), 'results':summaries,
            'warning':'Replay outcomes are hand-authored, not Haiku performance. No live source accuracy claims.'}


if __name__ == '__main__':
    print(json.dumps(benchmark(), indent=2, ensure_ascii=False))
