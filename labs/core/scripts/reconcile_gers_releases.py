"""Offline DATA-013 replay from pinned real archives and captured access metadata."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from benchmarks.gers_reconciliation_eval import evaluate
from kepcore.gers_reconciliation import load_pinned_pair, reconcile
from kepcore.overture_places import canonical

ROOT=Path(__file__).resolve().parents[1]


def export_private_queue(target: Path, report: dict) -> None:
    target=target.expanduser()
    if target.is_symlink() or target.exists():
        raise ValueError('Private research queue must be a new file')
    resolved=target.resolve()
    private_raw=ROOT/'.local'
    if private_raw.is_symlink():
        raise ValueError('Private directory cannot be a symlink')
    private=private_raw.resolve()
    if not resolved.is_relative_to(private) or not resolved.parent.is_dir():
        raise ValueError('Private queue must be under existing gitignored labs/core/.local/')
    payload={'study':'KEP-DATA-013','targeted_not_random':True,'consumer_publish':False,
        'before_population_sha256':report['before_population_sha256'],
        'after_population_sha256':report['after_population_sha256'],
        'queue':report['review_queue'],'identity':report['identity_review'],
        'human_labels':0,'physical_business_event_inference_allowed':False}
    with resolved.open('xb') as f:
        import os
        os.fchmod(f.fileno(),0o600)
        f.write(canonical(payload))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--benchmark',action='store_true')
    p.add_argument('--check',action='store_true',help='Check exact stable committed results, excluding timings')
    p.add_argument('--private-queue-output',type=Path)
    args=p.parse_args()
    result=evaluate(profile=args.benchmark)
    if args.check:
        expected=json.loads((ROOT/'reports/KEP_DATA_013_REAL_RESULTS.json').read_text())
        if result['stable_results']!=expected['stable_results']:
            raise SystemExit('DATA-013 stable source results changed; investigate before updating expected report')
    if args.private_queue_output is not None:
        before,after=load_pinned_pair()
        export_private_queue(args.private_queue_output,reconcile(before,after,allow_historical_backfill=True))
    print(json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False))


if __name__=='__main__':main()
