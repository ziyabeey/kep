"""Small deterministic SYNTHETIC GeoJSON contract benchmark, NOT actual POIs."""
from __future__ import annotations

from tempfile import TemporaryDirectory
from pathlib import Path
import json
import uuid

from kepcore.overture_places import ingest_geojson, pilot_audit_plan, PILOT


def example(fid, cell, name, category, dx=0, dy=0, **props):
    xmin, ymin, xmax, ymax = PILOT[cell]
    return {'type':'Feature','geometry':{'type':'Point','coordinates':[(xmin+xmax)/2+dx,(ymin+ymax)/2+dy]},
            'properties':{'id':str(uuid.UUID(int=fid)), 'theme':'places', 'type':'place',
                          'names':{'primary':name},'taxonomy':{'primary':category},
                          'basic_category':category,'confidence':.65,'sources':[{'dataset':'synthetic_test','license':'synthetic'}],**props}}


def run():
    a,b=sorted(PILOT)
    with TemporaryDirectory() as temp:
        paths={name:Path(temp)/f'{name}.json' for name in PILOT}
        rows={a:[example(11,a,'Cafe Örnek','cafe'),example(12,a,'Cafe Örnek','cafe',dx=.00009),
                 example(13,a,'Tarihi Müze','museum',confidence=None)],
              b:[example(14,b,'Ornek Lokanta','restaurant'), example(15,b,'Mekân','bar',socials=['do-not-copy'])]}
        for name in PILOT:
            paths[name].write_text(json.dumps({'type':'FeatureCollection','features':rows[name]},ensure_ascii=False))
        result=ingest_geojson(paths,pinned_release='2026-09-23.1')
        plan=pilot_audit_plan(result,budget=3,seed='explicit-lab-seed-2026-not-live')
    return {'origin':'synthetic_contract_fixture','real_istanbul_pois':0,
            'raw_records':result['audit']['rows_read'],'accepted':result['audit']['accepted'],
            'missing_confidence':result['audit']['missing_confidence'],
            'suspected_duplicate_pairs':len(result['audit']['potential_duplicate_pairs']),
            'random_audit_count':len(plan['selected']),
            'verified_real_world_place_count':0,
            'uses_live_api':False}


if __name__=='__main__':
    print(json.dumps(run(),indent=2,ensure_ascii=False))
