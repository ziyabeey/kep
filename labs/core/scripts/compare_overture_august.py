"""OFFLINE read-only, August v1.18 -> September v2 Overture source-record diff.

Provide all four independently reviewed August bundle facts. A passing hash
check is NOT independent authentication or proof that a business opened/closed.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from kepcore.overture_august import compare_august_september


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--august-dir',type=Path,required=True)
    ap.add_argument('--august-sha256',required=True)
    ap.add_argument('--manifest-sha256',required=True)
    ap.add_argument('--stac-sha256',required=True)
    ap.add_argument('--observed-at',required=True)
    args=ap.parse_args()
    report=compare_august_september(args.august_dir,
        expected_sha256=args.august_sha256,
        expected_manifest_sha256=args.manifest_sha256,
        expected_stac_sha256=args.stac_sha256,
        expected_observed_at=args.observed_at)
    print(json.dumps(report,indent=2,sort_keys=True,ensure_ascii=False))

if __name__=='__main__':main()
