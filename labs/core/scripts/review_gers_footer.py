"""Offline DATA-014 cost and patch-baseline review, with stable-result checking."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kepcore.gers_access_cost import DATA_DIR, PINNED_ZIP_SHA256, load_capture
from kepcore.gers_footer_review import review_metadata
from scripts.gers_footer_study import replay

ROOT = Path(__file__).resolve().parents[1]


def evaluate():
    result = replay()
    manifest = load_capture(DATA_DIR / 'footers.zip', PINNED_ZIP_SHA256)
    result['metadata_alias_review'] = review_metadata(manifest['objects'])
    result['artifact_sha256'] = PINNED_ZIP_SHA256
    result['costs_are_per_release_reads_without_cross_release_cache_deduplication'] = True
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    result = evaluate()
    if args.check:
        expected = json.loads((ROOT / 'reports/KEP_DATA_014_FOOTER_RESULTS.json').read_text())
        alias = json.loads((ROOT / 'reports/KEP_DATA_014_ALIAS_REVIEW.json').read_text())
        if ({k:result[k] for k in ('stable_results','observed_capture')} != expected
                or result['metadata_alias_review'] != alias):
            raise SystemExit('DATA-014 reference changed: investigate, do not silently bless')
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
