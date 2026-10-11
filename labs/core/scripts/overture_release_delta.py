"""Research-only Overture POI release delta; NO NETWORK, NO consumer publish.

`python scripts/overture_release_delta.py` replays the frozen real September
archive with a hypothetical October mutation fixture. DO NOT cite that as real
change in Istanbul.

To examine a future manually pinned and separately downloaded research bundle:

`python scripts/overture_release_delta.py --candidate-dir PRIVATE_DIR \\
    --candidate-release 2026-10-21.0 \\
    --candidate-sha256 <REVIEWED_SHA_FROM_INDEPENDENT_SOURCE> \\
    --candidate-observed-at 2026-10-22T10:00:00+03:00`

A recorded SHA proves matching bytes only, not physical business existence.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime,timezone

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from kepcore.overture_delta import (
    controlled_future_example, snapshot_from_frozen_archive,
    load_operator_research_bundle, compare_snapshots,
)


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate-dir',type=Path,help='Explicit future normalized Overture bundle; otherwise synthetic replay')
    parser.add_argument('--candidate-release',help='Independently reviewed exact future Overture release')
    parser.add_argument('--candidate-sha256',help='Independently reviewed SHA-256 for normalized JSON bytes')
    parser.add_argument('--candidate-observed-at',help='Timezone-aware source retrieval timestamp')
    args=parser.parse_args()
    spec=[args.candidate_dir,args.candidate_release,args.candidate_sha256,args.candidate_observed_at]
    if any(x is not None for x in spec) and not all(x is not None for x in spec):
        parser.error('Provide ALL four candidate arguments or NONE')
    if args.candidate_dir:
        if datetime.fromisoformat(args.candidate_observed_at.replace('Z','+00:00')) > datetime.now(timezone.utc):
            parser.error('Future-dated real source observation forbidden')
        before=snapshot_from_frozen_archive()
        candidate=load_operator_research_bundle(args.candidate_dir,
          expected_release=args.candidate_release,
          expected_normalized_sha256=args.candidate_sha256,
          expected_observed_at=args.candidate_observed_at)
        report=compare_snapshots(before,candidate)
    else:
        report=controlled_future_example()
    print(json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2))


if __name__=='__main__':
    main()
