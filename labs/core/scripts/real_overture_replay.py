"""Offline replay of the pinned, actual Overture Istanbul research sample.

This CLI never scrapes the web, calls an LLM or publishes consumer content.
For a real human field audit, pass a private off-repository seed file.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from kepcore.overture_places import canonical
from kepcore.overture_real import quality_report, check_core_publish_gate, prepare_private_audit, DATA_DIR


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--directory',type=Path,default=DATA_DIR,help='Pinned local snapshot folder')
    ap.add_argument('--audit-seed-file',type=Path,help='Private 16+ character seed file, never pass literal on CLI')
    ap.add_argument('--audit-output',type=Path,help='New local directory to write the unlabelled field-review sheet')
    ap.add_argument('--audit-budget',type=int,default=60)
    ap.add_argument('--sampled-at',default='2026-10-11T03:00:00+03:00',
                    help='Explicit snapshot-as-of time (with UTC offset)')
    args=ap.parse_args()
    if bool(args.audit_seed_file) != bool(args.audit_output):
        ap.error('--audit-seed-file and --audit-output are required together')
    summary=quality_report(args.directory)
    summary['core_gate']=check_core_publish_gate(args.directory)
    if args.audit_output:
        if args.audit_seed_file.is_symlink() or not args.audit_seed_file.is_file():
            ap.error('Private seed file must exist and must not be a symlink')
        seed=args.audit_seed_file.read_text(encoding='utf-8').strip()
        if len(seed)<16:
            ap.error('Private seed must have 16+ characters')
        result=prepare_private_audit(args.directory,budget=args.audit_budget,
                                     seed=seed,sampled_at=args.sampled_at)
        args.audit_output.mkdir(parents=True,exist_ok=False)
        (args.audit_output/'audit_plan_unlabeled.json').write_bytes(canonical(result['plan']))
        (args.audit_output/'field_review_sheet_unlabeled.json').write_bytes(
            canonical(result['unlabeled_review_sheet']))
        summary['audit_plan_written']=True
        summary['audit_sample_size']=len(result['unlabeled_review_sheet'])
        summary['audit_output_directory']=str(args.audit_output)
        summary['audit_labels_completed']=0
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
