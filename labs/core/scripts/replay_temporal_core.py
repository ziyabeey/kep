"""KEP-CORE-001 offline exact synthetic-result regression pin, no data reads.

This is a SOFTWARE consistency check of a user-approved synthetic world, NOT
independent business evidence, external model quality or real source truth.
"""
from __future__ import annotations
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from benchmarks.temporal_core_eval import run,REGIMES,POLICIES

# Canonical SHA-256 independently reproduced from both Python 3.11 and 3.13
# GitHub Actions full synthetic result payloads before pinning.
FROZEN_CANONICAL_SHA256='1907d98db2cc142f20b393092eca9bfd81f03724ea91e0dfd7ea03629294b2ea'
EXPECTED_CASES=3000


def evaluate(*,check:bool=False)->dict:
    data=run()
    canonical=json.dumps(data,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode('utf-8')
    digest=sha256(canonical).hexdigest()
    if (data.get('study')!='KEP-CORE-001'
        or data.get('scenario_origin')!='wholly_synthetic_hidden_truth'
        or data.get('test_truth_not_available_to_pipeline') is not True
        or data.get('consumer_publish') is not False
        or data.get('model_api_calls')!=0 or data.get('new_source_downloads')!=0
        or data.get('real_field_accuracy') is not None
        or data.get('business_openings_or_closures_accuracy') is not None
        or set(data.get('results',{}))!=set(REGIMES)
        or sum(r['policies']['temporal_root']['n'] for r in data['results'].values())!=EXPECTED_CASES
        or any(set(r['policies'])!=set(POLICIES) for r in data['results'].values())):
        raise ValueError('Synthetic benchmark scope or data-access boundary changed')
    if check and digest!=FROZEN_CANONICAL_SHA256:
        raise ValueError('CORE-001 exact synthetic result SHA-256 changed; examine mechanism or seed')
    return data


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    print(json.dumps(evaluate(check=args.check),ensure_ascii=False,indent=2,sort_keys=True))


if __name__=='__main__':
    main()
