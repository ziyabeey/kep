"""Offline analysis of TWO pinned Overture Places release snapshots.

Requires the exact GitHub Actions August 2026 artifact ZIP (verified against
KEP-DATA-010 frozen checksums) and the repo's immutable September 2026 place
archive. Without --august-zip this CLI displays help and fetches NOTHING.
It never interprets a missing listing as a business closure and never sends
any information to consumers or changes the source registry.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kepcore.overture_change_triage import (
    inspect_releases, build_targeted_queue, safe_public_summary, _canonical)
from kepcore.overture_archive_artifact import load_original_research_zip, FROZEN_SHA
from kepcore.overture_real import load_archive

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_DIR = (ROOT/'.local').resolve()


def run(august_zip:Path, *, queue_output:Path|None=None) -> dict:
    august, ameta, _ = load_original_research_zip(august_zip)
    september, smeta, _ = load_archive(verify=True)
    x = inspect_releases(august, september['records'])
    summary = safe_public_summary(x)
    summary.update({
        'study':'KEP-DATA-011',
        'older_release':'2026-08-19.0',
        'newer_release':'2026-09-23.1',
        'august_github_artifact_zip_sha256':FROZEN_SHA['zip'],
        'august_normalized_sha256':FROZEN_SHA['places_minimal.json'],
        'september_population_sha256':smeta['population_sha256'],
        'older_release_retrieved_at':ameta['acquisition']['observed_at'],
        'newer_release_retrieved_at':smeta['acquisition']['downloaded_at_utc'],
        'retrieval_order_reversed':True,
        'upstream_authenticated_independently':False,
        'business_identity_resolved_by_id_alone':False,
        'caution':'Confidence score revisions are supplier data changes, not calibrated accuracy, openings, closures, or moves.',
    })
    queue=build_targeted_queue(x)
    summary['targeted_review_queue_size']=queue['total_selected']
    summary['targeted_review_counts_without_place_ids']=queue['counts']
    if queue_output is not None:
        target=queue_output.expanduser().resolve()
        if not target.is_relative_to(PRIVATE_DIR) or not target.parent.is_dir() or target.exists() or target.is_symlink():
            raise ValueError('Targeted queue must use a NEW file in labs/core/.local/ (gitignored)')
        payload=dict(queue)
        payload.update({'source_releases':['2026-08-19.0','2026-09-23.1'],
                        'population_sha256':smeta['population_sha256'],
                        'not_for_prevalence_calibration':True})
        target.write_bytes(_canonical(payload)+b'\n')
        target.chmod(0o600)
    return summary


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--august-zip',type=Path,
                   help='Exact original Actions ZIP, SHA256 checked; no network')
    p.add_argument('--private-queue-output',type=Path,
                   help='Optional new output under labs/core/.local; never commit')
    args=p.parse_args()
    if args.private_queue_output and not args.august_zip:
        p.error('Queue generation requires original pinned August artifact')
    if not args.august_zip:
        print(json.dumps({'mode':'OFFLINE_ONLY','network_calls':0,
            'requires':'--august-zip ORIGINAL_PINNED_ARTIFACT.zip',
            'public_result':'aggregate summary only; source IDs never printed',
            'human_truth_labels':0},ensure_ascii=False,indent=2))
        return
    print(json.dumps(run(args.august_zip,queue_output=args.private_queue_output),
                     ensure_ascii=False,sort_keys=True,indent=2))


if __name__=='__main__':
    main()
