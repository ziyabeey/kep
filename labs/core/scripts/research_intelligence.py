"""Read-only demo connecting current factual blockers to lab research.

No model calls, live fetches, permissions changes or production decisions.
"""
from __future__ import annotations
from pathlib import Path
import sys
import json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from kepcore.core import load_catalog,Query,decide,load_json,ROOT,reconcile_claims
from kepcore.evidence_lab import EvidenceChannel,Observation,route_research,field_research_tasks


def demo() -> dict:
    records=load_catalog()
    core=decide(records,Query(city='İstanbul',kind='place',budget=500))
    tasks=field_research_tasks(core,max_tasks=4)
    pera=load_json(ROOT/'data/raw/pera_conflict_research_fixture.json')
    disputes=reconcile_claims(pera['claims'])
    initial=EvidenceChannel('official','venue_owner',.8,.8,0,True,True)
    copy=EvidenceChannel('copy','venue_owner',.999,.999,0,True,False)
    extra=EvidenceChannel('independent','registered_partner',.9,.9,.06,True)
    lab=route_research(.70,(Observation('official','venue_owner',True),Observation('copy','venue_owner',True)),
                       (initial,copy,extra),budget=.10)
    return {
        'title':'KEP SCI demo: actual records + hypothetical probabilities',
        'core_action':core.action,
        'real_catalog_records':len(records),
        'proposed_next_fields':[t.__dict__ for t in tasks],
        'pera_disputed_fields':len([v for v in disputes.values() if v['status']=='disputed']),
        'pera_distinct_publishers_per_field':sorted({v['independent_publisher_count'] for v in disputes.values()}),
        'hypothetical_model_output':{
            'action':lab.action,'posterior':lab.belief.probability,
            'independent_roots':lab.belief.independent_roots,
            'next_source':lab.selected_probe,'not_real_world_calibrated':True},
        'warning':'No permission to publish; no AI/browser/network call; Pera retrieved-version conflict is NOT a live price claim.'
    }


if __name__=='__main__':
    print(json.dumps(demo(),indent=2,ensure_ascii=False))
