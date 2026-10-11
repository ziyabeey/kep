"""Offline DATA-017 original Parquet footer index capability replay. No network."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from kepcore.gers_index_audit import evaluate

ROOT=Path(__file__).resolve().parents[1]
REFERENCE=ROOT/'reports/KEP_DATA_017_INDEX_AUDIT.json'

def stable_projection(r):
    return {k:r[k] for k in (
      'study','origin','source_footer_zip_sha256','covered_release_paths','totals',
      'non_indexed_id_scan_bytes_all_release_paths',
      'non_indexed_id_scan_bytes_one_release',
      'non_indexed_id_scan_bytes_membership_one_release',
      'id_page_index_usable','id_bloom_filter_usable',
      'id_union_query_sha256','membership_one_release_fits_prior_budget',
      'full_id_one_release_fits_prior_budget','official_membership_agreement_fraction',
      'publisher_changelog_comparison_baseline','all_id_events_observed',
      'consumer_publish','http_requests','data_page_response_bytes')}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--check',action='store_true')
    args=p.parse_args()
    report=evaluate()
    if args.check:
        if REFERENCE.is_symlink() or not REFERENCE.is_file():
            raise SystemExit('Missing DATA-017 frozen summary')
        expected=json.loads(REFERENCE.read_text())
        if stable_projection(report)!=expected:
            raise SystemExit('DATA-017 archived original index capability drifted')
    print(json.dumps(stable_projection(report),sort_keys=True,indent=2,ensure_ascii=False))

if __name__=='__main__':main()
