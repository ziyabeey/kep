"""Offline KEP-FIELD-001 blind physical-existence baseline evaluation.

Default protocol mode never reads private files or accesses the network.
For real field review, supply both A/B workbooks, frozen plan, seed and as-of.
Only aggregate counts and provisional diagnostics are printed.
"""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kepcore.field_pilot import protocol, evaluate_pilot


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--protocol', action='store_true')
    ap.add_argument('--reviewer-a', type=Path)
    ap.add_argument('--reviewer-b', type=Path)
    ap.add_argument('--plan', type=Path)
    ap.add_argument('--seed-file', type=Path)
    ap.add_argument('--evaluation-asof')
    args = ap.parse_args()
    parameters = (args.reviewer_a, args.reviewer_b, args.plan,
                  args.seed_file, args.evaluation_asof)
    if args.protocol or not any(parameters):
        if any(parameters):
            ap.error('Protocol mode cannot accept private reviewer arguments')
        result = protocol()
    else:
        if not all(parameters):
            ap.error('Private evaluation requires both reviewers, exact plan, seed file and as-of time')
        result = evaluate_pilot(
            reviewer_a=args.reviewer_a, reviewer_b=args.reviewer_b,
            audit_plan=args.plan, seed_file=args.seed_file,
            evaluation_asof=args.evaluation_asof,
        )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == '__main__':
    main()
