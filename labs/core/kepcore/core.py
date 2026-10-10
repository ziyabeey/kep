"""Evidence-aware discovery kernel; deliberately dependency-free.

This is an engineering prototype, not a trained recommender or calibrated
probabilistic model. Calendar, rights and factual constraints are hard gates.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any
from pathlib import Path
import hashlib
import json
import math
import unicodedata
from .availability import opening_status, field_is_fresh

IST = ZoneInfo('Europe/Istanbul')
ROOT = Path(__file__).resolve().parents[1]

def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding='utf-8'))

def stable_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',',':')).encode()).hexdigest()

def dt(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        obj = value
    else:
        obj = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return obj.replace(tzinfo=IST) if obj.tzinfo is None else obj.astimezone(IST)

def fold(text: str) -> str:
    text = text.replace('İ','I').replace('ı','i').lower()
    return ''.join(c for c in unicodedata.normalize('NFD',text) if not unicodedata.combining(c))

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    if not all(math.isfinite(v) for v in [lat1,lon1,lat2,lon2]):
        raise ValueError('Coordinates must be finite')
    if not (-90<=lat1<=90 and -90<=lat2<=90 and -180<=lon1<=180 and -180<=lon2<=180):
        raise ValueError('Invalid coordinate range')
    a,b=map(math.radians,[lat1,lat2]); x=math.radians(lat2-lat1); y=math.radians(lon2-lon1)
    h=math.sin(x/2)**2+math.cos(a)*math.cos(b)*math.sin(y/2)**2
    return 6371.0088*2*math.asin(math.sqrt(min(1,max(0,h))))

def normalize_events(envelope: dict) -> list[dict]:
    meta=envelope['meta']; out=[]
    categories={'SİNEMA':'cinema','KONSER':'music','SERGİ':'exhibition','DİĞER':'other'}
    seen=set()
    for raw in envelope['records']:
        key=f"izmir_event:{raw['Id']}"
        if key in seen: raise ValueError(f'duplicate source ID: {key}')
        seen.add(key)
        start,end=dt(raw['EtkinlikBaslamaTarihi']),dt(raw['EtkinlikBitisTarihi'])
        flags=[]
        if end<start: raise ValueError(f'backwards event interval: {key}')
        equal=end==start
        if equal: flags.append('END_EQUALS_START_DURATION_UNKNOWN')
        multi=end.date()>start.date()
        kind='exhibition_range' if raw['Tur']=='SERGİ' and multi else ('program_range' if multi else 'single_occurrence')
        if kind=='program_range': flags.append('SESSION_TIMES_NOT_ENUMERATED')
        if kind=='exhibition_range': flags.append('DAILY_OPENING_HOURS_UNKNOWN')
        venue=raw['EtkinlikMerkezi'].strip()
        ambiguous=venue in {'İlçelerde Etkinlik Alanları','İlçe Çok Amaçlı Salonlar'}
        if ambiguous: flags.append('VENUE_UNRESOLVED')
        free=raw.get('UcretsizMi')
        if free is not True and free is not False: flags.append('FREE_FLAG_UNKNOWN')
        # A false free flag does NOT encode a paid amount.
        price=0 if free is True else None
        if price is None: flags.append('PRICE_AMOUNT_UNKNOWN')
        row=dict(id=key,kind='event',event_kind=kind,name=' '.join(raw['Adi'].split()),
                 city=meta['source_city'],category=categories.get(raw['Tur'],'other'),
                 starts_at=start.isoformat(),ends_at=None if equal else end.isoformat(),
                 declared_end=end.isoformat(),time_zone='Europe/Istanbul',
                 lifecycle='scheduled_claim',evidence_status='source_recorded',
                 origin_live_verified=meta['origin_live_verified'],
                 source_observed_at=meta['source_observed_at'],acquired_date=meta['acquired_date'],
                 source_id=meta['source_id'],source_url=meta['source_url'],
                 source_item_id=str(raw['Id']),source_record_hash=stable_hash(raw),
                 publisher_root='izmir_municipality',rights_scope='open_attribution',license=meta['license'],
                 venue=venue,venue_precision='unresolved' if ambiguous else 'named_only',lat=None,lon=None,
                 price=price,currency='TRY',source_claim_free=free,opening_hours=None,crowd=None,
                 sales_link=raw.get('BiletSatisLinki'),source_slug=raw['EtkinlikUrl'],
                 flags=flags,synthetic=False)
        out.append(row)
    return out

def normalize_places(envelope: dict) -> list[dict]:
    out=[]
    for p in envelope['records']:
        row=dict(p)
        row.update(kind='place',rights_scope='open_attribution',publisher_root='wikimedia',
                   evidence_status='source_recorded',lifecycle='listed_claim',
                   price=None,currency='TRY',synthetic=False,flags=['PRICE_AMOUNT_UNKNOWN','OPENING_HOURS_UNKNOWN','CROWD_UNKNOWN'],source_record_hash=stable_hash(p))
        out.append(row)
    return out

def load_catalog() -> list[dict]:
    return normalize_events(load_json(ROOT/'data/raw/izmir_events_excerpt.json')) + normalize_places(load_json(ROOT/'data/raw/istanbul_places_excerpt.json'))

def temporal_state(record: dict, when: datetime) -> str:
    if record['kind']!='event': return 'not_applicable'
    if record.get('lifecycle')=='cancelled': return 'cancelled'
    start=dt(record['starts_at']); end=dt(record.get('ends_at') or record['starts_at'])
    if when.date()>end.date(): return 'expired'
    if when.date()<start.date(): return 'future'
    if record['event_kind'] in ('program_range','exhibition_range'): return 'in_declared_range_not_daily_availability'
    if when<start: return 'later_today'
    if record.get('ends_at') is None: return 'duration_unknown'
    return 'in_session' if when<end else 'ended_today'

def fresh(record: dict, when: datetime, max_hours: float=48) -> bool:
    observed=record.get('source_observed_at')
    if not record.get('origin_live_verified') or not observed: return False
    age=(when-dt(observed)).total_seconds()/3600
    return 0<=age<=max_hours

@dataclass(frozen=True)
class Query:
    city: str
    kind: str = 'any'
    category: str | None = None
    at: str = '2026-10-10T18:00:00+03:00'
    budget: float | None = None
    currency: str = 'TRY'
    lat: float | None = None
    lon: float | None = None
    radius_km: float | None = None
    open_now: bool = False
    quiet: bool = False
    require_exact_session: bool = False
    mode: str = 'balanced'
    proactive: bool = False
    push_opt_in: bool = False
    already_sent_today: int = 0
    limit: int = 3

    def __post_init__(self):
        if self.currency not in {'TRY','EUR','USD','GBP','MXN'}: raise ValueError('Unsupported currency')
        if (self.lat is None) != (self.lon is None): raise ValueError('Both coordinates are required')
        if self.lat is not None: haversine_km(self.lat,self.lon,self.lat,self.lon)
        if self.mode not in {'work','roam','balanced','silent'}: raise ValueError('Unknown user mode')
        if self.kind not in {'event','place','any'}: raise ValueError('Unknown object kind')
        if not self.city.strip(): raise ValueError('City is required')
        if self.budget is not None and (not math.isfinite(self.budget) or self.budget<0): raise ValueError('Invalid budget')
        if self.radius_km is not None:
            if self.radius_km<0 or not math.isfinite(self.radius_km):raise ValueError('Invalid radius')
            if self.lat is None or self.lon is None:raise ValueError('Radius requires origin')
            haversine_km(self.lat,self.lon,self.lat,self.lon)
        if self.limit<1 or self.limit>50:raise ValueError('Limit must be 1..50')
        if self.already_sent_today<0:raise ValueError('Invalid notification count')
        dt(self.at)

@dataclass
class Decision:
    action: str
    selected: list[dict]
    reasons: list[str]
    considered: int
    blocked: dict[str,list[str]]
    model_used: bool = False
    policy_version: str = 'query_aware_v0.3'

    def to_dict(self): return asdict(self)

def candidate_gate(r: dict,q: Query) -> tuple[list[str],list[str],list[str],float | None]:
    """Hard exclusion vs missing required evidence vs nonessential caveats."""
    hard=[]; needed=[]; caveats=[]; distance=None
    when=dt(q.at)
    if fold(r['city'])!=fold(q.city):hard.append('WRONG_CITY')
    if q.kind!='any' and r['kind']!=q.kind:hard.append('WRONG_KIND')
    if q.category and q.category!=r['category']:hard.append('WRONG_CATEGORY')
    if r.get('rights_scope')!='open_attribution':hard.append('RIGHTS_NOT_APPROVED')
    if r.get('lifecycle')=='cancelled':hard.append('CANCELLED')
    if r.get('evidence_status')=='disputed':needed.append('DISPUTED_EVIDENCE')
    if q.radius_km is not None:
        if r.get('lat') is None or r.get('lon') is None:needed.append('COORDINATES_UNKNOWN')
        else:
            distance=haversine_km(q.lat,q.lon,r['lat'],r['lon'])
            if distance>q.radius_km:hard.append('OUTSIDE_RADIUS')
            caveats.append('STRAIGHT_LINE_APPROXIMATE_NOT_WALKING_ROUTE')
    if q.budget is not None:
        price=r.get('price')
        if price is None:
            needed.append('PRICE_UNKNOWN')
        elif isinstance(price,bool) or not isinstance(price,(int,float)) or not math.isfinite(price) or price<0:
            needed.append('PRICE_INVALID')
        elif r.get('currency') != q.currency:
            needed.append('CURRENCY_CONVERSION_REQUIRED')
        elif not field_is_fresh(r,'price',when,48):
            needed.append('PRICE_FRESHNESS_UNVERIFIED')
        elif price>q.budget:
            hard.append('OVER_BUDGET')
    if r['kind']=='event':
        state=temporal_state(r,when)
        if state in {'expired','ended_today'}:hard.append('EVENT_ENDED')
        if not fresh(r,when):needed.append('SOURCE_FRESHNESS_UNVERIFIED')
        if r.get('venue_precision')=='unresolved':needed.append('VENUE_UNRESOLVED')
        if q.require_exact_session and r['event_kind']!='single_occurrence':needed.append('SESSION_TIMES_UNKNOWN')
        if q.open_now:
            if r['event_kind']!='single_occurrence':needed.append('DAILY_OPENING_HOURS_UNKNOWN')
            elif state in {'future','later_today'}:hard.append('NOT_STARTED')
            elif state=='duration_unknown':needed.append('DURATION_UNKNOWN')
        if r['event_kind']!='single_occurrence':caveats.append('DATE_RANGE_NOT_DAILY_SESSION_LIST')
    else:
        if q.open_now:
            hours=r.get('opening_hours')
            state=opening_status(hours,when)
            if state=='UNKNOWN':needed.append('OPENING_HOURS_UNKNOWN')
            if not field_is_fresh(r,'opening_hours',when,48):
                needed.append('SOURCE_FRESHNESS_UNVERIFIED')
            elif state=='CLOSED':hard.append('CLOSED_AT_REQUESTED_TIME')
        caveats.extend(['LIVE_STATUS_UNVERIFIED','ADMISSION_NOT_CONFIRMED'])
    if q.quiet:
        crowd=r.get('crowd')
        if not isinstance(crowd,str) or crowd not in {'low','medium','high'}:
            needed.append('CROWD_UNKNOWN')
        elif not field_is_fresh(r,'crowd',when,.5):
            needed.append('CROWD_FRESHNESS_UNVERIFIED')
        elif crowd!='low':
            hard.append('NOT_LOW_CROWD')
        else:
            caveats.append('LOW_CROWD_IS_NOT_ACOUSTIC_QUIETNESS_PROOF')
    return hard,needed,caveats,distance

def decide(catalog: list[dict], q: Query, policy: str='query_aware') -> Decision:
    if policy not in {'query_aware','blanket_verification','simple_safe'}: raise ValueError('Unknown policy')
    if q.proactive:
        if not q.push_opt_in:return Decision('SILENT',[],['PUSH_NOT_AUTHORIZED'],0,{})
        if q.mode in {'work','silent'}:return Decision('SILENT',[],['USER_MODE_BLOCK'],0,{})
        cap=2 if q.mode=='roam' else 1  # configurable, not learned optimality
        if q.already_sent_today>=cap:return Decision('SILENT',[],['DAILY_FREQUENCY_CAP'],0,{})
    blocked={}; allowed=[]; unresolved=[]
    for r in catalog:
        hard,needed,caveats,distance=candidate_gate(r,q)
        if policy=='blanket_verification':
            if not fresh(r,dt(q.at)):needed.append('BLANKET_FRESHNESS_REQUIRED')
            if r.get('price') is None:needed.append('BLANKET_PRICE_REQUIRED')
            if r.get('opening_hours') is None:needed.append('BLANKET_HOURS_REQUIRED')
        if hard:
            blocked[r['id']]=list(dict.fromkeys(hard));continue
        if needed:
            blocked[r['id']]=list(dict.fromkeys(needed));unresolved.append(r);continue
        # No invented popularity or quality signals. Both safe policies use proximity.
        allowed.append(dict(id=r['id'],name=r['name'],city=r['city'],kind=r['kind'],source_url=r['source_url'],source_record_hash=r['source_record_hash'],distance_km=None if distance is None else round(distance,4),distance_type='straight_line' if distance is not None else None,caveats=caveats,price=r.get('price') if (isinstance(r.get('price'),(int,float)) and not isinstance(r.get('price'),bool) and math.isfinite(r['price']) and r['price']>=0 and field_is_fresh(r,'price',dt(q.at),48)) else None,evidence_status=r['evidence_status']))
    allowed.sort(key=lambda a:(a['distance_km'] if a['distance_km'] is not None else float('inf'),a['id']))
    if allowed:
        # Silent/work mode affects proactive messages, NOT an explicit user question.
        return Decision('DISCOVER' if all(a['kind']=='place' for a in allowed[:q.limit]) else 'RECOMMEND',allowed[:q.limit],['REQUIRED_FIELDS_CHECKED'],len(catalog),blocked,policy_version=policy+'_v0.3')
    if unresolved:
        reasons=sorted({x for r in unresolved for x in blocked[r['id']]})
        action='CLARIFY' if reasons and all(x in {'CROWD_UNKNOWN','SESSION_TIMES_UNKNOWN'} for x in reasons) else 'REFRESH'
        return Decision(action,[],reasons,len(catalog),blocked,policy_version=policy+'_v0.3')
    return Decision('ABSTAIN',[],['NO_ELIGIBLE_RECORD'],len(catalog),blocked,policy_version=policy+'_v0.3')

def reconcile_claims(claims: list[dict]) -> dict:
    """Conflicting same-authority values remain disputed. Counts are not probabilities."""
    grouped={}
    for c in claims:
        grouped.setdefault((c['entity_id'],c['field']),[]).append(c)
    result={}
    for (entity,field),cs in grouped.items():
        values=sorted({c['value'] for c in cs})
        roots=sorted({c['publisher_root'] for c in cs})
        result[f'{entity}/{field}']=dict(status='disputed' if len(values)>1 else 'source_recorded',value=values[0] if len(values)==1 else None,observed_values=values,publisher_roots=roots,independent_publisher_count=len(roots),source_urls=sorted({c['source_url'] for c in cs}),action='REFRESH' if len(values)>1 else 'NONE')
    return result

def check_model_selection(decision: Decision, proposed_ids: list[str]) -> dict:
    """Guard for a future model adapter. This function makes no API call."""
    permitted={r['id'] for r in decision.selected}
    invalid=set(proposed_ids)-permitted
    if invalid:return dict(accepted=False,reason='MODEL_CANNOT_BYPASS_CORE',invalid_ids=sorted(invalid))
    return dict(accepted=True,selected_ids=list(dict.fromkeys(proposed_ids)),model_called=False)
