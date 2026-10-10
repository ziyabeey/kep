"""Compare two local code snapshots against the same authored fault overlays."""
from __future__ import annotations
from pathlib import Path
import json,subprocess,sys
from kepcore.core import Query,decide
from benchmarks.edge_cases import regression_cases

def run(out,old_root=None):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    cases=regression_cases();path=out/'new_regression_cases.json'
    path.write_text(json.dumps(cases,ensure_ascii=False,indent=2)+'\n')
    new=[]
    for c in cases:
        d=decide([c['record']],Query(**c['query']))
        new.append(dict(id=c['id'],expected=c['expected'],actual=d.action,passed=d.action==c['expected'],reasons=d.reasons,blocked=d.blocked))
    result={'type':'authored_regression_cases_not_real_user_test','cases':len(cases),'v03_passed':sum(x['passed'] for x in new),'v03':new}
    if old_root:
        script="""import json,sys
from kepcore.core import Query,decide
rows=[]
for c in json.load(open(sys.argv[1])):
 try: actual=decide([c['record']],Query(**c['query'])).action
 except Exception as e: actual='ERROR:'+type(e).__name__
 rows.append(dict(id=c['id'],expected=c['expected'],actual=actual,passed=actual==c['expected']))
print(json.dumps(rows))
"""
        p=subprocess.run([sys.executable,'-c',script,str(path.resolve())],cwd=old_root,capture_output=True,text=True,check=True)
        old=json.loads(p.stdout);result.update(v02_passed=sum(r['passed'] for r in old),v02=old)
    (out/'regression_comparison.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result
