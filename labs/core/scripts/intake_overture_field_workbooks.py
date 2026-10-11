"""Offline, read-only KEP physical-existence audit Excel intake.

Usage: python scripts/intake_overture_field_workbooks.py --reviewer-a A.xlsx \
    --reviewer-b B.xlsx --plan PRIVATE/audit_plan_unlabeled.json \
    --seed-file PRIVATE/AUDIT_PRIVATE_SEED_KEEP_SECRET.txt \
    --evaluation-asof 2026-10-12T00:00:00+03:00

No external request; no workbook changes; no personal vote/evidence URLs logged.
A rate is withheld until every frozen POI has two resolved, concordant ballots.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from kepcore.overture_field_review import evaluate_review_workbooks


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--reviewer-a',type=Path,required=True)
    ap.add_argument('--reviewer-b',type=Path,required=True)
    ap.add_argument('--plan',type=Path,required=True,help='Frozen private audit plan')
    ap.add_argument('--seed-file',type=Path,required=True,help='Private audit seed file, NEVER store in git')
    ap.add_argument('--evaluation-asof',required=True,help='Timezone-aware ISO timestamp')
    ap.add_argument('--archive',type=Path,help='Optional archived real Overture data directory')
    args=ap.parse_args()
    kwargs={}
    if args.archive:kwargs['directory']=args.archive
    out=evaluate_review_workbooks(
        reviewer_a=args.reviewer_a,reviewer_b=args.reviewer_b,
        audit_plan=args.plan,seed_file=args.seed_file,
        evaluation_asof=args.evaluation_asof,**kwargs)
    print(json.dumps(out,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
