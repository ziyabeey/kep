"""Independent expected outcomes for newly found gaps, all explicit test overlays.

Uses a real venue as the base record, NOT real opening/crowd/price observations.
"""
from __future__ import annotations
from copy import deepcopy
from kepcore.core import load_catalog,stable_hash


def sample_place():
    r=deepcopy(next(r for r in load_catalog() if r['kind']=='place'))
    r.update(synthetic=True,synthetic_overlay='v03_regression_fixture',origin_live_verified=True,
             source_observed_at='2026-10-10T17:50:00+03:00')
    return r


def schedule(sat=None):
    weekly={str(i):[['09:00','20:00']] for i in range(1,8)}
    if sat is not None:weekly['6']=sat
    return dict(timezone='Europe/Istanbul',weekly=weekly,exceptions={})


def proof(value,observed='2026-10-10T17:50:00+03:00'):
    return dict(origin_live_verified=True,observed_at=observed,value_hash=stable_hash(value))


def regression_cases():
    cases=[]
    def add(name,changes,q,expected):
        r=sample_place();r.update(changes)
        query={'city':'İstanbul','kind':'place','at':'2026-10-10T18:00:00+03:00',**q}
        cases.append(dict(id=name,record=r,query=query,expected=expected,origin='real_base_synthetic_test_overlay'))
    add('closed_hours',{'opening_hours':schedule([['09:00','17:00']])},{'open_now':True},'ABSTAIN')
    add('open_hours',{'opening_hours':schedule([['09:00','20:00']])},{'open_now':True},'DISCOVER')
    add('exact_closing_time',{'opening_hours':schedule([['09:00','18:00']])},{'open_now':True},'ABSTAIN')
    x=schedule();x['exceptions']['2026-10-10']=[]
    add('exception_closed',{'opening_hours':x},{'open_now':True},'ABSTAIN')
    add('unsupported_hours_string',{'opening_hours':'usually open'},{'open_now':True},'REFRESH')
    x=schedule();x['timezone']='Invalid/Zone'
    add('invalid_time_zone',{'opening_hours':x},{'open_now':True},'REFRESH')
    add('known_high_crowd',{'crowd':'high','field_evidence':{'crowd':proof('high')}},{'quiet':True},'ABSTAIN')
    add('fresh_low_crowd',{'crowd':'low','field_evidence':{'crowd':proof('low')}},{'quiet':True},'DISCOVER')
    add('stale_low_crowd',{'crowd':'low','field_evidence':{'crowd':proof('low','2026-10-10T10:00:00+03:00')}},{'quiet':True},'REFRESH')
    add('price_stale_despite_new_record',{'price':100,'field_evidence':{'price':proof(100,'2026-10-01T12:00:00+03:00')}},{'budget':500},'REFRESH')
    add('wrong_currency_not_compared',{'price':100,'currency':'USD'},{'budget':500},'REFRESH')
    add('fresh_price_within_budget',{'price':100},{'budget':500},'DISCOVER')
    add('invalid_boolean_price',{'price':True},{'budget':500},'REFRESH')
    add('invalid_string_price',{'price':'unknown'},{'budget':500},'REFRESH')
    add('same_hours_stale_field',{'opening_hours':schedule(),'field_evidence':{'opening_hours':proof(schedule(),'2026-10-01T12:00:00+03:00')}},{'open_now':True},'REFRESH')
    return cases
