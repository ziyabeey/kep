#!/usr/bin/env python3
"""Rebuild local evidence, preference benchmarks and tests. No network/model calls."""
from __future__ import annotations
import argparse, contextlib, io, json, sys, unittest
from pathlib import Path
import run_lab
from benchmarks.ratings import run as run_preferences
from benchmarks.replay_regressions import run as run_regressions

ROOT=Path(__file__).resolve().parent

def main() -> int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--old-v02-root',type=Path,help='Optional original v0.2 folder, read-only comparison')
    args=ap.parse_args();out=ROOT/'results';out.mkdir(exist_ok=True)
    with (out/'contract_run_log_v03.txt').open('w') as log,contextlib.redirect_stdout(log):
        contracts=run_lab.run(out/'contract')
    with (out/'preference_run_log.txt').open('w') as log,contextlib.redirect_stdout(log):
        pref=run_preferences(out)
    new_reg=run_regressions(out/'regression_current',args.old_v02_root)
    # A repeat verifies deterministic quality outputs; elapsed time is deliberately ignored.
    with contextlib.redirect_stdout(io.StringIO()):
        again=run_preferences(out/'reproducibility_repeat')
    quality=lambda x:{k:v for k,v in x.items() if k!='runtime_seconds'}
    same=quality(pref)==quality(again)
    (out/'reproducibility.json').write_text(json.dumps(dict(identical_quality_outputs=same,ignored_fields=['runtime_seconds'],independent_trials=False),indent=2)+'\n')
    suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'))
    with (out/'unit_test_log_v03.txt').open('w') as log:
        t=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    historical_path=out/'regression_comparison.json'
    historical=json.loads(historical_path.read_text()) if historical_path.exists() else {}
    core_pass=next(r['passed'] for r in contracts['policies'] if r['policy']=='query_aware')
    summary=dict(version='0.3',scope='local_historical_data_research_not_live_product',
        data=pref['dataset'],uci_source=json.loads((ROOT/'data/uci_manifest.json').read_text()),
        unit_tests=dict(run=t.testsRun,failures=len(t.failures),errors=len(t.errors),passed=t.wasSuccessful()),
        regression=dict(cases=new_reg['cases'],v03_passed=new_reg['v03_passed'],v02_passed_historical=historical.get('v02_passed'),authored_overlays=True),
        legacy_contract=dict(cases=contracts['test_scope']['designed_cases'],query_aware_passed=core_pass),
        test_count_warning='Unit tests include the 85 legacy scenarios and 15 regression cases. Do not sum them as independent trials.',
        preference=dict(split=pref['primary']['split'],selected_by_validation=pref['primary']['selected_by_validation'],models=pref['primary']['models'],paired_comparisons=pref['primary']['paired_comparisons'],cold_start=pref['cold_start']),
        reproducibility_quality_identical=same,live_llm_calls=0,paid_data_api_calls=0,real_app_user_trials=0,
        newly_acquired_live_istanbul_records=0,existing_city_catalog_records=23,github_mutations=0,
        limitations=pref['limitations']+['No real Laya/MiMo inference; structured model boundary is only an offline contract','No automatic production promotion of a winning model','New opening-hours/crowd assertions were synthetic overlays, not live source facts'])
    (out/'release_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'unit_tests':summary['unit_tests'],'contract_cases_passed':core_pass,'regression_cases_passed':new_reg['v03_passed'],'ratings':summary['data'],'reproducible':same},ensure_ascii=False,indent=2))
    return 0 if (t.wasSuccessful() and same and core_pass==85 and new_reg['v03_passed']==new_reg['cases']) else 1

if __name__=='__main__':sys.exit(main())
