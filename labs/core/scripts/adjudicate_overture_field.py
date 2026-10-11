"""KEP-DATA-005 offline, research-only human adjudication and holdout forecast.

NO API calls, no AI evaluation, no source permission changes, no consumer publish.
All A/B/C votes, raw evidence links, private seed and cases stay OFF GitHub.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from kepcore.overture_real import DATA_DIR, prepare_private_audit
from kepcore.overture_adjudication import (
    blind_case_templates, new_holdout_forecast, reconcile,
)


def _verified_plan(plan_path:Path,seed_path:Path,archive:Path):
    if seed_path.is_symlink() or not seed_path.is_file() or plan_path.is_symlink():
        raise ValueError('Private frozen study inputs missing or unsafe')
    p=json.loads(plan_path.read_text(encoding='utf-8'))
    actual=prepare_private_audit(archive,budget=p['audit_budget'],
                                 seed=seed_path.read_text(encoding='utf-8').strip(),
                                 sampled_at=p['sampled_at'])['plan']
    if actual != p:
        raise ValueError('Private frozen plan and archived Overture frame mismatch')
    return p


def main() -> None:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--mode',required=True,choices=['forecast','blinded-cases','reconcile'])
    ap.add_argument('--reviewer-a',type=Path)
    ap.add_argument('--reviewer-b',type=Path)
    ap.add_argument('--plan',required=True,type=Path)
    ap.add_argument('--seed-file',required=True,type=Path)
    ap.add_argument('--evaluation-asof',help='ISO date with timezone; required for third-review cases/results')
    ap.add_argument('--archive',type=Path,default=DATA_DIR)
    ap.add_argument('--third-ballots',type=Path,help='Strict off-repo JSONL, only for discordant A/B outcomes')
    ap.add_argument('--cases-output',type=Path,help='New off-repo JSONL; never overwrite')
    args=ap.parse_args()
    if args.mode=='forecast':
        if args.third_ballots or args.cases_output:
            ap.error('Forecast never accepts review outputs')
        p=_verified_plan(args.plan,args.seed_file,args.archive)
        result=new_holdout_forecast(p)
    else:
        if not args.reviewer_a or not args.reviewer_b or not args.evaluation_asof:
            ap.error('Both A/B workbooks and --evaluation-asof are required')
        params=dict(reviewer_a=args.reviewer_a,reviewer_b=args.reviewer_b,
                    audit_plan=args.plan,seed_file=args.seed_file,
                    evaluation_asof=args.evaluation_asof,directory=args.archive)
        if args.mode=='blinded-cases':
            if args.third_ballots or not args.cases_output:
                ap.error('Blinded cases require --cases-output and no third ballots')
            cases=blind_case_templates(**params)
            out=args.cases_output
            if out.is_symlink() or out.exists() or not out.parent.is_dir():
                raise ValueError('Case JSONL must be a NEW file in an existing private folder')
            with out.open('x',encoding='utf-8') as handle:
                for case in cases:
                    handle.write(json.dumps(case,ensure_ascii=False,sort_keys=True)+'\n')
            result={'study':'KEP-DATA-005','status':'BLINDED_CASES_ISSUED',
                    'cases_n':len(cases),'research_only':True,'consumer_publish':False,
                    'contains_ab_ballot_values':False,'contains_truth_labels':False}
        else:
            if args.cases_output:
                ap.error('Reconcile does not generate templates')
            result=reconcile(**params,adjudications=args.third_ballots)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
