"""Offline independently repeat REAL August->September Overture source comparison.

Requires ORIGINAL ZIP from GitHub Actions #38121005943. No HTTP or API keys.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from kepcore.overture_archive_artifact import replay_artifact

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--zip',type=Path,required=True,
                   help='Original GitHub Actions artifact ZIP, copied locally')
    args=p.parse_args()
    print(json.dumps(replay_artifact(args.zip),sort_keys=True,ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
