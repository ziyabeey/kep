"""Offline human adjudication intake for KEP-SCI-002B (no network or publishing)."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kepcore.review_intake import load_intake, resolve_reviews, verify_research_snapshots


def _private_output(target: str) -> Path:
    private = (ROOT / 'data' / 'reviews_private').resolve()
    dest = Path(target).expanduser().resolve()
    if not dest.is_relative_to(private) or dest.suffix != '.jsonl':
        raise ValueError('Review labels must be written as JSONL under labs/core/data/reviews_private/')
    if not private.exists() or not private.is_dir():
        raise ValueError('Create the private review directory first')
    return dest


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidates', required=True, help='Human-selected field claims JSONL')
    p.add_argument('--ballots', required=True, help='Independent human review ballots JSONL')
    p.add_argument('--adjudications', help='Third-human adjudications JSONL for conflicts')
    p.add_argument('--asof', required=True, help='Time cutoff with timezone, freezes eligible reviews')
    p.add_argument('--output', help='Optional immutable JSONL label export under private review directory')
    p.add_argument('--snapshot-dir', help='Required with --output: pinned local source bytes named <sha256>.snapshot')
    args = p.parse_args()
    candidates, ballots, adjudications = load_intake(args.candidates, args.ballots, args.adjudications)
    result = resolve_reviews(candidates, ballots, adjudications, asof=args.asof)
    if args.output:
        if not args.snapshot_dir:
            p.error('--output requires --snapshot-dir and registered approved source rights')
        integrity = verify_research_snapshots(candidates, args.snapshot_dir)
        target = _private_output(args.output)
        # Never overwrite an earlier adjudication export, even on rerun.
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        fd = os.open(target, flags, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            for row in result['reviews']:
                stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n')
    # Audit summary does not expose raw claim values. Source URLs and claimed
    # values remain in operator-owned private input files.
    public_summary = {key: val for key, val in result.items() if key != 'reviews'}
    if args.output:
        public_summary['snapshot_integrity_gate'] = integrity
    print(json.dumps(public_summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
