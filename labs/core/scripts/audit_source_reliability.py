"""Offline, rights-gated KEP-SCI-003 random audit planning / assessment.

NEVER touches live sources or the KEP consumer database. Sample seeds are read
from KEP_AUDIT_SEED, not command-line arguments or files tracked by Git.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kepcore.audit_sampling import design_random_audit, estimate_population_error
from kepcore.calibration import load_reviews
from kepcore.radar import load_sources
from kepcore.review_intake import _load_jsonl, ReviewCandidate

PRIVATE = (ROOT/'data'/'reviews_private').resolve()


def _save_report(result: dict, path: str) -> None:
    PRIVATE.mkdir(parents=True, exist_ok=True)
    destination = Path(path).expanduser().resolve()
    if not destination.is_relative_to(PRIVATE):
        raise PermissionError('Reports must stay inside the gitignored reviews_private directory')
    # Refuse silent overwrites that can conceal previously selected audits.
    with destination.open('x', encoding='utf-8') as file:
        os.chmod(destination, 0o600)
        json.dump(result, file, ensure_ascii=False, indent=2)
        file.write('\n')
    print(f'Research-only report written: {destination}')


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['plan','evaluate'])
    p.add_argument('--candidates',required=True,help='Strict ReviewCandidate JSONL')
    p.add_argument('--snapshots',required=True,help='Directory of <sha256>.snapshot files')
    p.add_argument('--out',required=True,help='New JSON file under data/reviews_private; no overwrite')
    p.add_argument('--asof',required=True,help='Timezone-aware ISO-8601 cutoff')
    p.add_argument('--budget',type=int,help='Number of random audit claims (plan)')
    p.add_argument('--plan',help='Frozen plan JSON path (evaluate)')
    p.add_argument('--reviewed',help='Adjudicated ReviewedClaim JSONL (evaluate)')
    p.add_argument('--synthetic',action='store_true',help='Clearly mark an offline synthetic fixture, never real data')
    args=p.parse_args()
    seed=os.getenv('KEP_AUDIT_SEED','')
    if len(seed)<16:
        p.error('KEP_AUDIT_SEED requires a private 16+ character seed')
    records=_load_jsonl(args.candidates,ReviewCandidate)
    registry=load_sources()
    if args.command=='plan':
        if args.budget is None or args.plan or args.reviewed:
            p.error('plan needs --budget, not --plan or --reviewed')
        result=design_random_audit(records,sources=registry,snapshot_dir=args.snapshots,
            asof=args.asof,budget=args.budget,seed=seed,synthetic=args.synthetic)
    else:
        if args.plan is None or args.reviewed is None or args.budget is not None:
            p.error('evaluate needs --plan and --reviewed, not --budget')
        frozen=json.loads(Path(args.plan).read_text(encoding='utf-8'))
        if args.synthetic != (frozen.get('origin')=='synthetic'):
            p.error('--synthetic must agree with the frozen audit plan')
        result=estimate_population_error(frozen,records,load_reviews(args.reviewed),
            sources=registry,snapshot_dir=args.snapshots,
            evaluation_asof=args.asof,replay_seed=seed)
    _save_report(result,args.out)

if __name__=='__main__':
    main()
