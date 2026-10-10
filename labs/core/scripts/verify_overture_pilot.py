"""Offline KEP-DATA-002 integrity checker and private-seed audit draw.

No network calls or AI model usage. Verify local artifacts before human review.
Neither manifest fields nor source hashes prove the upstream author.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from kepcore.overture_audit import verify_artifact,design_existence_audit
from kepcore.overture_places import canonical


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory',required=True,type=Path)
    p.add_argument('--require-live',action='store_true',help='Refuse operator-supplied data. Does not independently authenticate origin.')
    p.add_argument('--audit-seed-file',type=Path,help='Off-repo private seed, not a CLI literal')
    p.add_argument('--audit-budget',type=int)
    p.add_argument('--audit-plan-output',type=Path)
    args=p.parse_args()
    if any(x is not None for x in (args.audit_seed_file,args.audit_budget,args.audit_plan_output)):
        if not all(x is not None for x in (args.audit_seed_file,args.audit_budget,args.audit_plan_output)):
            p.error('Creating an audit plan requires a private seed file, budget and new output filename')
    result=verify_artifact(args.directory,require_live=args.require_live)
    if args.audit_seed_file:
        seed_path=args.audit_seed_file
        if seed_path.is_symlink() or not seed_path.is_file():
            raise ValueError('Invalid private seed file')
        seed=seed_path.read_text(encoding='utf-8').strip()
        sampled_at=datetime.now(timezone.utc).isoformat()
        plan=design_existence_audit(args.directory,budget=args.audit_budget,
                                    seed=seed,sampled_at=sampled_at)
        output=args.audit_plan_output
        output.parent.mkdir(parents=True,exist_ok=True)
        # O_EXCL: never overwrite a frozen audit draw with post-review choices.
        fd=os.open(str(output),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        try:
            with os.fdopen(fd,'wb') as dest:
                dest.write(canonical(plan))
        except Exception:
            try:output.unlink(missing_ok=True)
            except OSError:pass
            raise
        result['audit_plan_saved_to']=str(output)
        result['audit_selection_size']=len(plan['selected'])
        result['human_labels_collected']=0
        result['sample_seed_not_in_output']=True
    print(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True))


if __name__=='__main__':main()
