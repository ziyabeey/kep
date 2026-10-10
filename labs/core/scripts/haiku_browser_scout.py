"""Run an explicitly approved Browser Scout experiment (OFFLINE by default)."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kepcore.radar import load_sources
from kepcore.scout_haiku import MODEL_ID, BROWSER_CONFIGS, live_preflight, execute_live_research


def main() -> int:
    parser=argparse.ArgumentParser(description='KEP read-only Haiku browser research scout')
    parser.add_argument('--source',required=True,help='Source ID in reviewed registry')
    parser.add_argument('--live',action='store_true',help='Explicitly permit paid API research')
    parser.add_argument('--network-sandbox-confirmed',action='store_true',help='Confirm external network egress isolation and redirect filtering, not supplied by this tool')
    args=parser.parse_args()
    sources=load_sources()
    source=sources.get(args.source)
    if source is None:
        print(json.dumps({'status':'denied','reason':'UNKNOWN_SOURCE'}))
        return 2
    permitted,reason=live_preflight(source,live=args.live,acknowledged=args.network_sandbox_confirmed,
                                    api_key_present=bool(os.environ.get('ANTHROPIC_API_KEY')))
    if not permitted:
        print(json.dumps({'status':'denied','source_id':source.id,'reason':reason,
                          'network_used':False,'model_calls':0,'enabled_tools':list(k for k,v in BROWSER_CONFIGS.items() if v['enabled'])}))
        return 0 if not args.live else 2
    try:
        result=asyncio.run(execute_live_research(source))
    except ImportError:
        print(json.dumps({'status':'error','reason':'INSTALL_OPTIONAL_BROWSER_SDK','network_used':False}))
        return 2
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
