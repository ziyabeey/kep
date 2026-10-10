"""Read-only calibration lab. NO external calls; NO production policy writes."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kepcore.calibration import load_reviews,report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',required=True,help='Reviewed, licensed local JSONL file')
    parser.add_argument('--train-end',required=True)
    parser.add_argument('--calibration-end',required=True)
    parser.add_argument('--evaluation-asof',required=True)
    parser.add_argument('--target-risk',type=float,default=.2)
    parser.add_argument('--minimum-accepted',type=int,default=25)
    args=parser.parse_args()
    rows=load_reviews(args.input)
    result=report(rows,train_end=args.train_end,calibration_end=args.calibration_end,
                  evaluation_asof=args.evaluation_asof,target_risk=args.target_risk,
                  min_published=args.minimum_accepted)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
