"""Reproducible KEP-DATA-006: 4,803 real records + ARTIFICIAL later edits.

Counts measure implementation behavior on a frozen research dataset, NOT real
longitudinal change in Istanbul. There is no true second release observation.
"""
from __future__ import annotations
from kepcore.overture_delta import controlled_future_example
import json


def run():
    r=controlled_future_example()
    c=r['source_record_churn']
    assert r['synthetic_second_release'] is True
    assert r['old_population_n']==4803 and r['new_population_n']==4803
    assert c['retained_ids']==4801 and c['newly_listed_ids']==2 and c['no_longer_listed_ids']==2
    assert c['field_or_geometry_revised_ids']==5 and c['confidence_only_revised_ids']==1
    assert len(c['possible_id_reassignment_hints'])==1
    assert r['real_world_business_changes_estimated'] is False
    return {'study':'KEP-DATA-006','reference':'real pinned 4,803 Overture records',
            'second_snapshot':'synthetic_overlay_NOT_REAL_OCTOBER_RELEASE',
            'old_population_n':r['old_population_n'],'new_population_n':r['new_population_n'],
            'retained_ids':c['retained_ids'],'added_to_source':c['newly_listed_ids'],
            'absent_from_source':c['no_longer_listed_ids'],
            'field_or_geometry_revised':c['field_or_geometry_revised_ids'],
            'confidence_only':c['confidence_only_revised_ids'],
            'possible_identity_reassignments_review_only':len(c['possible_id_reassignment_hints']),
            'actual_october_source_observations':0,'real_world_closures_verified':0,
            'report_is_offline_and_non_publishing':True}

if __name__=='__main__':print(json.dumps(run(),ensure_ascii=False,sort_keys=True,indent=2))
