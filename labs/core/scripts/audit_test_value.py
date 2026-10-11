"""KEP-QA-001: test-value audit by strictly isolated mutations.

Injected defects modify disposable copies only. No real-data search, network,
models or original KEP source changes. Synthetic mutation coverage is NOT an
estimate of real defects or real-world business value.
"""
from __future__ import annotations
from pathlib import Path
from time import perf_counter
from hashlib import sha256
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
MANIFEST=ROOT/'benchmarks/test_value_protocol.json'
TARGETS=frozenset(('kepcore/temporal_pipeline.py',
                   'kepcore/budgeted_verify.py',
                   'kepcore/adaptive_trust.py'))


def protocol():
    p=json.loads(MANIFEST.read_text(encoding='utf-8'))
    muts=p.get('risk_mutations',[])
    suites=p.get('evaluation_suites',{})
    if (p.get('study')!='KEP-QA-001' or p.get('network_access') is not False
        or len(muts)!=12 or len(suites.get('sentinel',[]))!=12
        or suites.get('focused')!=[
            'tests.test_temporal_pipeline',
            'tests.test_budgeted_verify',
            'tests.test_adaptive_trust']
        or len({m['id'] for m in muts})!=12
        or any(m['file'] not in TARGETS
               or m['needle']==m['replacement']
               or type(m['priority']) is not int or not 1<=m['priority']<=5
               for m in muts)):
        raise ValueError('Mutation protocol differs from preregistered gate')
    return p


def sandbox_copy(destination):
    """Copy tiny synthetic-core fixtures, NEVER Overture archives or secrets."""
    for name in ('kepcore','tests','benchmarks','data/raw'):
        src=ROOT/name
        if not src.is_dir() or src.is_symlink():
            raise ValueError('Missing or unsafe synthetic fixture: '+name)
        dst=destination/name
        dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copytree(src,dst,ignore=shutil.ignore_patterns(
            '__pycache__','*.pyc','.local'))
    (destination/'sitecustomize.py').write_text(
        'import socket\n'
        'def blocked(*args,**kwargs):\n'
        '    raise RuntimeError("QA001_OFFLINE_ONLY")\n'
        'socket.socket.connect=blocked\n'
        'socket.create_connection=blocked\n',encoding='utf-8')


def test(destination, selectors):
    env=os.environ.copy()
    env.update(PYTHONPATH=str(destination),PYTHONDONTWRITEBYTECODE='1',
               PYTHONNOUSERSITE='1',PIP_NO_INDEX='1')
    start=perf_counter()
    try:
        p=subprocess.run([sys.executable,'-B','-m','unittest','-v',*selectors],
                         cwd=destination,env=env,capture_output=True,
                         text=True,timeout=35)
    except subprocess.TimeoutExpired as exc:
        raise ValueError('Uninterpretable test timeout: '+str(exc)) from exc
    log=p.stdout+'\n'+p.stderr
    if 'QA001_OFFLINE_ONLY' in log:
        raise RuntimeError('A targeted test attempted a network connection')
    hits=re.findall(r'Ran (\d+) tests? in ',log)
    if not hits:
        raise ValueError('No executable unit suite: '+log[-1500:])
    failures=sorted(set(re.findall(
        r'(?m)^(?:FAIL|ERROR): ([^\r\n]+)',log)))
    if p.returncode and not failures:
        raise ValueError('Cannot attribute fault detection to unit assertions')
    return {'detected':bool(p.returncode),
            'seconds':round(perf_counter()-start,3),
            'tests_executed':int(hits[-1]),
            'failed_tests':failures[:30]}


def _summary(mutants,kind):
    caught=[m for m in mutants if m[kind]['detected']]
    risk=sum(m['priority'] for m in mutants)
    return {'caught':len(caught),'total':len(mutants),
            'survivors':[m['id'] for m in mutants if not m[kind]['detected']],
            'risk_weighted_detection_fraction':round(
                sum(m['priority'] for m in caught)/risk,6),
            'test_seconds_sum':round(sum(m[kind]['seconds'] for m in mutants),3)}


def audit():
    p=protocol()
    files={name:(ROOT/name).read_bytes() for name in TARGETS}
    before={name:sha256(body).hexdigest() for name,body in files.items()}
    with tempfile.TemporaryDirectory(prefix='kep-qa001-') as workspace:
        cwd=Path(workspace)
        sandbox_copy(cwd)
        baselines={n:test(cwd,s) for n,s in p['evaluation_suites'].items()}
        if (any(b['detected'] for b in baselines.values())
            or baselines['sentinel']['tests_executed']!=12
            or baselines['focused']['tests_executed']<52):
            raise ValueError('The clean unmodified control must pass 12/52 tests')
        cases=[]
        for mutant in p['risk_mutations']:
            name=mutant['file']
            original=files[name].decode('utf-8')
            old,new=mutant['needle'],mutant['replacement']
            if original.count(old)!=1:
                raise ValueError('Exact original code snippet drift: '+mutant['id'])
            changed=original.replace(old,new,1)
            location=cwd/name
            compile(changed,str(location),'exec')
            location.write_text(changed,encoding='utf-8')
            try:
                scores={}
                for group,selectors in p['evaluation_suites'].items():
                    outcome=test(cwd,selectors)
                    if outcome['tests_executed']!=baselines[group]['tests_executed']:
                        raise ValueError('Fault changed the test-count control')
                    scores[group]=outcome
            finally:
                location.write_bytes(files[name])
            cases.append({'id':mutant['id'],
                          'priority':mutant['priority'],
                          'risk':mutant['why'],
                          **scores})
        if any((cwd/name).read_bytes()!=body for name,body in files.items()):
            raise AssertionError('Temporary sandbox was not restored')
    if any((ROOT/name).read_bytes()!=body for name,body in files.items()):
        raise AssertionError('Original KEP module unexpectedly mutated')
    return {
        'study':'KEP-QA-001',
        'basis':'12_AUTHOR_DECLARED_SYNTAX_VALID_SOURCE_MUTATIONS',
        'baseline_commit':p['baseline_commit'],
        'source_sha256':dict(sorted(before.items())),
        'clean_tests':baselines,
        'fast_sentinel':_summary(cases,'sentinel'),
        'focused_suite':_summary(cases,'focused'),
        'incremental_faults_detected_by_focused':[
            c['id'] for c in cases
            if c['focused']['detected'] and not c['sentinel']['detected']],
        'mutants':cases,
        'original_module_modified':False,
        'new_source_downloads':0,
        'external_network_requests':0,
        'consumer_publish':False,
        'real_defect_detection_probability':None,
        'note':('A score over authored faults is a regression sensitivity '
                'diagnostic, not a real-world quality, ROI, or general '
                'software error-rate estimate.')
    }


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--protocol',action='store_true')
    ap.add_argument('--output',type=Path)
    args=ap.parse_args()
    if args.protocol:
        if args.output: ap.error('Protocol-only mode cannot write')
        p=protocol()
        print(json.dumps({'study':p['study'],
                          'mutations':len(p['risk_mutations']),
                          'sentinel':len(p['evaluation_suites']['sentinel']),
                          'source_downloads':0},sort_keys=True))
        return
    if args.output and (args.output.is_symlink() or args.output.exists()
                        or not args.output.parent.is_dir()):
        raise ValueError('The report requires a new path in an existing folder')
    result=audit()
    if args.output:
        args.output.write_text(json.dumps(result,ensure_ascii=False,
                                indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(json.dumps({'study':result['study'],
                      'fast_sentinel':result['fast_sentinel'],
                      'focused_suite':result['focused_suite'],
                      'additional_catches':result['incremental_faults_detected_by_focused'],
                      'clean_tests':result['clean_tests']},
                     ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
