#!/usr/bin/env python3
"""CLI for source-registry inspection and explicit research-only API polling.

No network call by default. Never promotes source records to user-visible data.
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kepcore.radar import PollState, load_sources, poll, https_transport


def load_state(path: Path, source_id: str) -> PollState:
    if not path.exists():
        return PollState()
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict) or payload.get('version') != 1:
        raise ValueError('Unknown persisted polling state version')
    entries = payload.get('sources', {})
    if not isinstance(entries, dict):
        raise ValueError('Malformed persisted state')
    state = entries.get(source_id, {})
    if not isinstance(state, dict) or set(state) - set(PollState.__dataclass_fields__):
        raise ValueError('Malformed source state')
    return PollState(**state)


def save_state(path: Path, source_id: str, state: PollState) -> None:
    from dataclasses import asdict
    payload = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'version':1, 'sources':{}}
    if payload.get('version') != 1 or not isinstance(payload.get('sources'), dict):
        raise ValueError('Unknown persisted polling state')
    payload['sources'][source_id] = asdict(state)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    with tmp.open('w', encoding='utf-8') as handle:
        os.chmod(tmp, 0o600)
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write('\n')
        handle.flush()
        os.fsync(handle.fileno())
    tmp.replace(path)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--list', action='store_true', help='Inspect sources; no network access')
    ap.add_argument('--source', help='Registered source identifier')
    ap.add_argument('--fetch', action='store_true', help='Explicitly make one bounded HTTP request (opt-in)')
    ap.add_argument('--out', type=Path, help='Unique local JSON output for a changed research snapshot')
    ap.add_argument('--state', type=Path, default=ROOT/'.local/radar_state.json')
    args = ap.parse_args()
    sources = load_sources()
    if args.list:
        print(json.dumps([{'id':s.id,'city':s.city,'status':s.status,'approved_uses':list(s.approved_uses)}
                          for s in sources.values()], indent=2, ensure_ascii=False))
        return 0
    if not args.source:
        ap.error('Pass --list or --source')
    if args.source not in sources:
        ap.error('Unknown source identifier')
    source = sources[args.source]
    if not args.fetch:
        print(json.dumps({'source':source.id,'status':'dry_run','fetch_allowed':source.allows('research_ingest'),
                          'consumer_display_allowed':source.allows('consumer_display'),
                          'network_used':False}, ensure_ascii=False))
        return 0
    if not args.out:
        ap.error('An explicit new --out destination is required for --fetch')
    if args.out.exists():
        ap.error('Output already exists: choose a unique path')
    state = load_state(args.state, source.id)
    result = poll(source, now=datetime.now(timezone.utc), state=state, transport=https_transport)
    if result.status != 'denied':
        save_state(args.state, source.id, result.state)
    if result.envelope:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        # Only a new research snapshot is written; no automatic user publication.
        with args.out.open('x', encoding='utf-8') as handle:
            json.dump(result.envelope, handle, ensure_ascii=False, indent=2)
            handle.write('\n')
    print(json.dumps({'source':source.id,'status':result.status,'reason':result.reason,
                      'records':len(result.envelope['records']) if result.envelope else 0,
                      'consumer_display_approved':False,'network_used':result.status != 'denied'}, ensure_ascii=False))
    return 0 if result.status in {'changed','unchanged','not_modified','skipped'} else 2 if result.status == 'denied' else 1

if __name__ == '__main__':
    raise SystemExit(main())
