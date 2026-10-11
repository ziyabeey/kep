"""Offline exact GitHub Actions August research artifact comparison.

This keeps both source releases reproducible after the seven-day GitHub
artifact retention expires. It never accesses the network, checks whether
an actual business is open, unlocks consumer publishing or runs any AI model.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from kepcore.overture_archive_artifact import replay_artifact

ARCHIVE=(Path(__file__).resolve().parents[1] /
         "data/real/overture_istanbul_2026-08-19.0/original_actions_artifact.zip")

def main()->None:
    report=replay_artifact(ARCHIVE)
    if (report["old_source_rows"]!=4650 or report["new_source_rows"]!=4803 or
        report["record_delta"]["retained_ids"]!=4581 or
        report["record_delta"]["confidence_only_revised_ids"]!=3337 or
        report["consumer_publish"] is not False or
        report["independent_upstream_s3_attestation"] is not False):
        raise ValueError("Pinned release replay did not match the research contract")
    report["archive_preservation"]="ORIGINAL_GITHUB_ACTIONS_ZIP_COMMITTED_AS_PINNED_RESEARCH_SOURCE"
    report["original_zip_required_from_external_source"]=False
    print(json.dumps(report,sort_keys=True,ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
