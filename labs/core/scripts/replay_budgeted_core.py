"""CORE-002 exact pinned synthetic replay, with no source or network calls.

The SHA-256 is for reproducible fictional-world policy results ONLY, not
external business accuracy, statistical validity or measured currency cost.
"""
from __future__ import annotations
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from benchmarks.budgeted_core_eval import run,REGIMES,POLICIES

# Independently identical JSON from successful Python 3.11/3.13 CI run
# 38166652721, checked against the GitHub artifact ZIP digests.
PINNED_CANONICAL_SHA256='9303794055e45a668abc4d194b64c1b86ce6fb9c9c48e70fdbcac3c5c578d6cc'
EXPECTED_CASES=2400


def evaluate(*,check:bool=False)->dict:
    report=run()
    raw=json.dumps(report,sort_keys=True,ensure_ascii=False,
                   separators=(',',':')).encode('utf-8')
    digest=sha256(raw).hexdigest()
    if (report.get('study')!='KEP-CORE-002'
        or report.get('scenario_origin')!='fully_synthetic_paired_hidden_truth'
        or report.get('policy_inputs_cannot_access_truth_or_future_answers') is not True
        or report.get('consumer_publish') is not False
        or report.get('real_world_business_accuracy') is not None
        or report.get('calibrated_source_reliability') is not False
        or report.get('real_field_labels_used')!=0
        or report.get('source_downloads')!=0
        or report.get('model_calls')!=0
        or set(report.get('regimes',{}))!=set(REGIMES)
        or sum(group['methods']['voi']['cases']
               for group in report['regimes'].values())!=EXPECTED_CASES
        or any(set(group['methods'])!=set(POLICIES)
               for group in report['regimes'].values())):
        raise ValueError('CORE-002 data/claims/protocol boundary changed')
    if check and digest!=PINNED_CANONICAL_SHA256:
        raise ValueError('CORE-002 simulation changed: investigate before accepting')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true',
                        help='Fail if complete pinned experiment changes')
    args=parser.parse_args()
    print(json.dumps(evaluate(check=args.check),
                     ensure_ascii=False,indent=2,sort_keys=True))


if __name__=='__main__':
    main()
