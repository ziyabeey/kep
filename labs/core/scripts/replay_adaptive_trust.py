"""CORE-003 full, offline, SHA-pinned fictional-world result regression.

The checksum proves byte reproducibility across Python runtimes, NOT real
business accuracy or independent source reliability. No source I/O.
"""
from __future__ import annotations
import argparse
import json
from hashlib import sha256
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from benchmarks.adaptive_trust_eval import run,REGIMES,POLICIES

FROZEN_CANONICAL_SHA256='c587b34c1e4801847c8bd8b71dc1b05c9ead5ee9cb28eeacab1dea1cd9c89e48'
EXPECTED_SYNTHETIC_CASES=960


def evaluate(*,check:bool=False)->dict:
    data=run()
    canonical=json.dumps(data,sort_keys=True,ensure_ascii=False,
                         separators=(',',':')).encode('utf-8')
    digest=sha256(canonical).hexdigest()
    if (data.get('study')!='KEP-CORE-003'
        or data.get('scenario_origin')!='WHOLLY_SYNTHETIC_INDEPENDENT_BACKGROUND_AUDITS'
        or data.get('actual_field_source_calibration') is not False
        or data.get('truth_and_future_answers_absent_from_policy_view') is not True
        or data.get('audit_feedback_independent_of_policy_check_selection') is not True
        or data.get('real_business_accuracy') is not None
        or data.get('real_human_reviews_used')!=0
        or data.get('source_downloads')!=0
        or data.get('model_calls')!=0
        or data.get('consumer_publish') is not False
        or set(data.get('results',{}))!=set(REGIMES)
        or sum(r['methods']['conservative']['cases'] for r in data['results'].values())
             !=EXPECTED_SYNTHETIC_CASES
        or any(set(r['methods'])!=set(POLICIES)
               for r in data['results'].values())):
        raise ValueError('CORE-003 synthetic data, scope or benchmark contract changed')
    if check and digest!=FROZEN_CANONICAL_SHA256:
        raise ValueError('CORE-003 pinned source-quality study changed: investigate before blessing')
    return data


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--check',action='store_true')
    args=p.parse_args()
    print(json.dumps(evaluate(check=args.check),
                     ensure_ascii=False,sort_keys=True,indent=2))


if __name__=='__main__':
    main()
