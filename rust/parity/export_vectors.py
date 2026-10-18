#!/usr/bin/env python3
"""Write Rust parity vectors from the Python reference lab (ADR-0034).

The Python modules in labs/core are the reference. This script runs them on a
fixed, deterministic input set and writes the expected outputs as JSON. Rust
tests read the same files and must reproduce every result exactly.

    python3 rust/parity/export_vectors.py           # rewrite vectors
    python3 rust/parity/export_vectors.py --check   # fail if vectors drifted

No network, randomness or wall clock is used.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1] / 'labs' / 'core'
sys.path.insert(0, str(LAB))

import copy  # noqa: E402
import itertools  # noqa: E402

from benchmarks.edge_cases import proof, regression_cases, schedule  # noqa: E402
from kepcore.availability import field_is_fresh, intervals, minute, opening_status  # noqa: E402
from kepcore.core import (Query, check_model_selection, decide, dt, fold, haversine_km,  # noqa: E402
                          load_catalog, load_json, normalize_events, reconcile_claims, stable_hash,
                          temporal_state)
from kepcore.model_boundary import context_for_model, validate_structured_reply  # noqa: E402
from kepcore.scheduler import SourceClock, due_sources  # noqa: E402

AT = '2026-10-10T18:00:00+03:00'  # Saturday, as in tests/test_v03.py


def outcome(fn, *args, **kwargs):
    """Return {'ok': value} or {'raises': ExceptionName}; Python raising is part of the contract."""
    try:
        return {'ok': fn(*args, **kwargs)}
    except Exception as exc:  # the reference may raise; Rust must report the same class
        return {'raises': type(exc).__name__}


def week(day=None, value=None, tz='Europe/Istanbul', base=(('09:00', '20:00'),)):
    weekly = {str(i): [list(p) for p in base] for i in range(1, 8)}
    if day is not None:
        weekly[str(day)] = value
    return {'timezone': tz, 'weekly': weekly, 'exceptions': {}}


def canon_cases():
    values = [
        None, True, False, 0, -0, 1, -17, 2**53, 2**63 - 1, 2**64, 10**30,
        0.0, -0.0, 1.0, -1.5, 0.1, 0.0001, 0.00001, 1e-7, 123456.789, 1e15, 1e16,
        1.5e300, 5e-324, 2.5, 100.0, 1e22, 0.30000000000000004,
        # Shortest digits where Rust's own `{}` picks a different same-length string.
        999999999987524.2, 2.2250738585072014e-308, 1.7976931348623157e308, 9007199254740993.0,
        '', 'İstanbul', 'ışık ğüş', 'quote " back \\ slash', 'tab\tnl\ncr\r',
        '\b\f\x00\x01\x1f\x7f', '  ', 'emoji 🎟️', 'é (NFC) vs é (NFD)',
        [], [1, 'a', None], {}, {'b': 1, 'a': 2, 'A': 3, 'İ': 4, 'i': 5, '': 6, 'aa': 7},
        {'nested': {'z': [1.0, {'y': None, 'x': True}], 'k': 'v'}},
        [['09:00', '20:00']], {'timezone': 'Europe/Istanbul', 'weekly': {'1': []}},
    ]
    out = []
    for i, v in enumerate(values):
        text = json.dumps(v, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
        out.append({'name': f'canon_{i:02d}', 'value': v, 'canonical': text, 'sha256': stable_hash(v)})
    # JSON number forms whose parsed Python value differs from the literal text.
    for i, literal in enumerate(['1e2', '1E2', '-0', '-0.0', '1.50', '1e400', '-1e400', '12345678901234567890123',
                                 '0.1e1', '3.0e-5', '[1.0,2,3e0]', '{"a":1,"a":2}']):
        v = json.loads(literal)
        out.append({'name': f'canon_literal_{i:02d}', 'json': literal,
                    'canonical': json.dumps(v, sort_keys=True, ensure_ascii=False, separators=(',', ':'))})
    return out


def minute_cases():
    texts = ['00:00', '09:30', '23:59', '24:00', '24:01', '25:00', '12:60', '9:30', '09:3', '09-30',
             '0930', '', ' 9:30', '9 :30', '+9:30', '-0:00', '09:+5', '09: 5', 'ab:cd', '1_:00',
             '09:30 ', '٠٩:٣٠', None, 930]
    out = []
    for t in texts:
        for end in (False, True):
            out.append({'name': f'minute_{t!r}_{end}', 'text': t, 'end': end,
                        'expect': outcome(minute, t, end=end)})
    return out


def intervals_cases():
    raws = [[], [['09:00', '20:00']], [['22:00', '02:00']], [['00:00', '24:00']], [['00:00', '00:00']],
            [['09:00']], [['09:00', '10:00', '11:00']], ['09:00-10:00'], None, {}, 'open',
            [['10:00', '09:00'], ['12:00', '13:00']], [['24:00', '01:00']], [[9, 10]]]
    return [{'name': f'intervals_{i:02d}', 'raw': r, 'expect': outcome(intervals, r)} for i, r in enumerate(raws)]


def opening_cases():
    cases = []

    def add(name, hours, at=AT):
        cases.append({'name': name, 'hours': hours, 'at': at,
                      'expect': outcome(opening_status, hours, datetime.fromisoformat(at))})

    # Mirrors tests/test_v03.py availability tests.
    add('open_regular', week())
    add('overnight_carry', week(5, [['22:00', '02:00']]), '2026-10-10T01:00:00+03:00')
    add('overnight_exact_close', week(5, [['22:00', '02:00']]), '2026-10-10T02:00:00+03:00')
    h = week(5, [['22:00', '02:00']]); h['exceptions']['2026-10-10'] = []
    add('exception_overrides_carry', h, '2026-10-10T01:00:00+03:00')
    add('utc_conversion', week(), '2026-10-10T06:00:00+00:00')
    h = week(); del h['weekly']['6']
    add('missing_weekday_unknown', h)
    add('equal_hours_unknown', week(base=(('00:00', '00:00'),)))
    add('all_day_explicit', week(base=(('00:00', '24:00'),)), '2026-10-10T23:59:00+03:00')
    for i, bad in enumerate([None, [], {}, 'open', week(base=(('30:00', '31:00'),))]):
        add(f'invalid_schedule_{i}', bad)

    # Boundaries on the [open, close) interval, seconds included.
    for t in ['08:59:59', '09:00:00', '19:59:59', '20:00:00', '20:00:30']:
        add(f'boundary_{t}', week(), f'2026-10-10T{t}+03:00')
    add('closed_day_empty_list', week(6, []))
    add('two_intervals_gap', week(6, [['09:00', '12:00'], ['19:00', '23:00']]))
    add('two_intervals_in_gap', week(6, [['09:00', '12:00'], ['19:00', '23:00']]), '2026-10-10T15:00:00+03:00')
    h = week(); h['exceptions']['2026-10-10'] = [['17:00', '18:30']]
    add('exception_open_window', h)
    h = week(); h['exceptions']['2026-10-09'] = [['22:00', '19:00']]
    add('yesterday_exception_carry', h, '2026-10-10T08:00:00+03:00')
    h = week(); h['exceptions']['not-a-date'] = [['25:00', '26:00']]
    add('bad_exception_value_unknown', h)
    h = week(); h['weekly']['8'] = 'x'
    add('extra_weekday_key_bad_value_unknown', h)
    h = week(); h['weekly']['8'] = [['01:00', '02:00']]
    add('extra_weekday_key_ignored', h)
    h = week(); h['exceptions'] = []
    add('exceptions_not_dict_unknown', h)
    h = week(); del h['exceptions']
    add('exceptions_missing_ok', h)
    h = week(); del h['timezone']
    add('timezone_missing_unknown', h)
    for i, tz in enumerate(['UTC', 'Europe/London', 'America/New_York', 'Asia/Tokyo', 'Not/AZone', '',
                            'europe/istanbul', '../etc/passwd', 5]):
        add(f'timezone_{i}', week(tz=tz))
    # DST transitions (tzdata-sensitive; kept to well-established past/near rules).
    add('london_dst_end', week(tz='Europe/London', base=(('01:00', '02:00'),)), '2026-10-25T01:30:00+00:00')
    add('newyork_dst_start', week(tz='America/New_York', base=(('02:00', '03:30'),)), '2026-03-08T07:15:00+00:00')
    add('weekly_not_dict_unknown', {'timezone': 'Europe/Istanbul', 'weekly': [], 'exceptions': {}})
    add('intervals_tuple_like_list', week(6, [['09:00', '20:00'], ['20:00', '24:00']]), '2026-10-10T23:00:00+03:00')
    return cases


def fresh_cases():
    cases = []
    price_proof = {'origin_live_verified': True, 'observed_at': '2026-10-10T17:50:00+03:00',
                   'value_hash': stable_hash(100)}

    def add(name, record, field='price', at=AT, max_hours=48):
        cases.append({'name': name, 'record': record, 'field': field, 'at': at, 'max_hours': max_hours,
                      'expect': outcome(field_is_fresh, record, field, datetime.fromisoformat(at), max_hours)})

    base = {'origin_live_verified': True, 'source_observed_at': '2026-10-10T17:50:00+03:00', 'price': 100}
    add('record_level_fresh', dict(base))
    add('record_level_not_live', {**base, 'origin_live_verified': False})
    add('record_level_too_old', {**base, 'source_observed_at': '2026-10-08T17:00:00+03:00'})
    add('record_level_exact_48h', {**base, 'source_observed_at': '2026-10-08T18:00:00+03:00'})
    add('record_level_future_observation', {**base, 'source_observed_at': '2026-10-10T18:00:01+03:00'})
    add('record_level_naive_timestamp', {**base, 'source_observed_at': '2026-10-10T17:50:00'})
    add('record_level_zulu', {**base, 'source_observed_at': '2026-10-10T14:50:00Z'})
    add('record_level_fraction', {**base, 'source_observed_at': '2026-10-10T17:50:00.123456+03:00'})
    add('record_level_space_separator', {**base, 'source_observed_at': '2026-10-10 17:50:00+03:00'})
    add('record_level_bad_timestamp', {**base, 'source_observed_at': 'yesterday'})
    add('record_level_missing_timestamp_raises', {'origin_live_verified': True, 'price': 100})
    add('record_level_numeric_timestamp_raises', {**base, 'source_observed_at': 1700000000})
    add('record_level_missing_everything', {})
    add('field_proof_fresh', {**base, 'field_evidence': {'price': dict(price_proof)}})
    add('field_proof_value_mismatch', {**base, 'price': 200, 'field_evidence': {'price': dict(price_proof)}})
    add('field_proof_float_vs_int_hash', {**base, 'price': 100.0, 'field_evidence': {'price': dict(price_proof)}})
    add('field_proof_expired', {**base, 'field_evidence': {'price': {**price_proof, 'valid_until': AT}}})
    add('field_proof_valid_until_later', {**base, 'field_evidence': {'price': {**price_proof, 'valid_until': '2026-10-10T18:00:01+03:00'}}})
    add('field_proof_valid_until_naive', {**base, 'field_evidence': {'price': {**price_proof, 'valid_until': '2026-10-11T00:00:00'}}})
    add('field_proof_valid_until_numeric_raises', {**base, 'field_evidence': {'price': {**price_proof, 'valid_until': 5}}})
    for status in ['disputed', 'unknown', 'retracted', 'confirmed', None]:
        add(f'field_proof_status_{status}', {**base, 'field_evidence': {'price': {**price_proof, 'status': status}}})
    add('field_proof_status_list_raises', {**base, 'field_evidence': {'price': {**price_proof, 'status': ['disputed']}}})
    add('field_proof_not_live', {**base, 'field_evidence': {'price': {**price_proof, 'origin_live_verified': False}}})
    add('field_proof_not_dict', {**base, 'field_evidence': {'price': 'yes'}})
    add('field_evidence_not_dict', {**base, 'field_evidence': ['price']})
    add('field_evidence_null', {**base, 'field_evidence': None})
    add('field_proof_null_falls_back', {**base, 'field_evidence': {'price': None}})
    add('other_field_proof_ignored', {**base, 'field_evidence': {'crowd': {'origin_live_verified': False}}})
    hours = week()
    add('opening_hours_proof', {**base, 'opening_hours': hours, 'field_evidence': {'opening_hours': {
        'origin_live_verified': True, 'observed_at': '2026-10-10T17:50:00+03:00', 'value_hash': stable_hash(hours)}}},
        field='opening_hours')
    add('missing_field_hash_of_null', {**base, 'field_evidence': {'crowd': {
        'origin_live_verified': True, 'observed_at': '2026-10-10T17:50:00+03:00', 'value_hash': stable_hash(None)}}},
        field='crowd')
    crowd = {**base, 'crowd': 'low', 'field_evidence': {'crowd': {
        'origin_live_verified': True, 'observed_at': '2026-10-10T17:35:00+03:00', 'value_hash': stable_hash('low')}}}
    add('crowd_half_hour_window_ok', crowd, field='crowd', max_hours=.5)
    add('crowd_half_hour_window_exceeded', crowd, field='crowd', at='2026-10-10T18:05:00.000001+03:00', max_hours=.5)
    add('cross_offset_age', {**base, 'source_observed_at': '2026-10-09T20:00:00-04:00'}, max_hours=0.5)
    return cases


def isotime_cases():
    texts = ['2026-10-10T17:50:00+03:00', '2026-10-10T17:50:00Z', '2026-10-10T17:50:00-04:00',
             '2026-10-10 17:50:00+03:00', '2026-10-10x17:50:00+03:00', '2026-10-10T17:50+03:00',
             '2026-10-10T17+03:00', '2026-10-10T17:50:00.1+03:00', '2026-10-10T17:50:00.123456+03:00',
             '2026-10-10T17:50:00.1234567+03:00', '2026-10-10T17:50:00,5+03:00', '2026-10-10T17:50:00+0300',
             '2026-10-10T17:50:00+03', '2026-10-10T17:50:00+03:00:30', '2026-10-10T17:50:00-00:00',
             '2026-10-10T17:50:00', '2026-10-10', '2026-10-10T24:00:00+03:00', '2026-10-10T17:50:00+24:00',
             '2026-10-10T17:50:60+03:00', '2026-02-30T00:00:00+03:00', '+2026-10-10T17:50:00+03:00',
             '0000-01-01T00:00:00+00:00', 'yesterday', '', '2026-10-10T', '2026-10-10T17:5+03:00',
             # '2026-10-10T17:50:00.+03:00' (empty fraction) is left out: Python 3.11
             # accepts it and 3.13 rejects it, so the reference itself is not stable.
             '2026-10-10T17:50:00+3:00', '2026-10-10T17:50:00+1€', '2026-10-10T17:50:00+€€',
             '2026-10-10T17:50:00+0€:00', '2026-10-10T17:5€+03:00', '2026-10-1€T17:50:00+03:00', '2026-10-10T17:50:00+03:60',
             # Accepted by Python 3.11+, rejected by the Rust subset (fails closed; see isotime.rs).
             '20261010T175000+0300', '2026-W41-6T17:50:00+03:00', '2026-10-10T175000+03:00',
             '2026-10-10T17:50:00 +03:00', '2026-10-10T17:50:00+03:00:30.5']
    out = []
    for t in texts:
        res = outcome(lambda x: datetime.fromisoformat(x.replace('Z', '+00:00')).isoformat(), t)
        out.append({'name': f'iso_{t!r}', 'text': t, 'expect': res})
    return out


def build_availability():
    return {
        'reference': 'labs/core (Python); see docs/adr/0034-rust-core-port.md',
        'canon': canon_cases(),
        'isotime': isotime_cases(),
        'minute': minute_cases(),
        'intervals': intervals_cases(),
        'opening_status': opening_cases(),
        'field_is_fresh': fresh_cases(),
    }


# ---------------------------------------------------------------- core.py

GALATA = (41.02563232, 28.97415319)
IZMIR = (38.4237, 27.1428)


def fold_cases():
    texts = ['İstanbul', 'ISTANBUL', 'istanbul', 'İZMİR', 'Izmir', 'ızmir', 'Çeşme', 'ŞİŞLİ', 'Ğ ğ Ü ü Ö ö',
             'Café', 'Cafe\u0301', 'ǅ', 'ΣΟΦΟΣ', 'Straße', 'ﬁ', '', '  İzmir  ', 'Kadıköy']
    return [{'name': f'fold_{i:02d}', 'text': t, 'expect': fold(t)} for i, t in enumerate(texts)]


def haversine_cases():
    pts = [
        (41.0, 29.0, 41.0, 29.0), (*GALATA, 41.026, 28.98293889), (*GALATA, *IZMIR), (0, 0, 0, 180),
        (90, 0, -90, 0), (0, 0, 0, 0.000001), (-33.8688, 151.2093, 51.5074, -0.1278), (41.0, 29.0, 41.009, 29.0),
        (90.000001, 0, 0, 0), (0, 180.5, 0, 0), (-91, 0, 0, 0), (0, -180, 0, 180),
    ]
    out = []
    for i, p in enumerate(pts):
        res = outcome(haversine_km, *p)
        if 'ok' in res:
            res = {'ok': res['ok'], 'rounded': round(res['ok'], 4)}
        out.append({'name': f'haversine_{i:02d}', 'args': list(p), 'expect': res})
    return out


def dt_cases():
    texts = ['2026-10-10T18:00:00+03:00', '2026-10-10T18:00:00', '2026-10-10T15:00:00Z', '2026-10-10T18:00:00-04:00',
             '2026-08-10T21:00:00', '2026-10-10', 'not a date', '2026-03-29T03:30:00+00:00',
             '2015-03-29T03:30:00', '2015-11-08T03:30:00', '2015-11-08T01:30:00+00:00']
    return [{'name': f'dt_{i:02d}', 'text': t, 'expect': outcome(lambda x: dt(x).isoformat(), t)}
            for i, t in enumerate(texts)]


def normalize_error_cases():
    raw = load_json(LAB / 'data/raw/izmir_events_excerpt.json')
    cases = []
    dup = copy.deepcopy(raw); dup['records'].append(copy.deepcopy(dup['records'][0]))
    cases.append(('duplicate_id', dup))
    back = copy.deepcopy(raw); r = back['records'][0]; r['EtkinlikBitisTarihi'] = '2026-08-09T21:00:00'
    cases.append(('backwards_interval', back))
    odd = copy.deepcopy(raw); r = odd['records'][1]
    r.update(Id='x-7', Tur='TİYATRO', Adi='  Çok   boşluklu\tad  ', EtkinlikMerkezi=' İlçe Çok Amaçlı Salonlar ', UcretsizMi=None)
    r.pop('BiletSatisLinki', None)
    cases.append(('unknown_type_venue_free_flag', odd))
    zone = copy.deepcopy(raw); zone['records'][2]['EtkinlikBaslamaTarihi'] = '2026-08-05T08:30:00Z'
    cases.append(('utc_start', zone))
    listed = copy.deepcopy(raw); listed['records'][0]['Tur'] = ['SERGİ']
    cases.append(('unhashable_type', listed))
    return [{'name': n, 'envelope': env, 'expect': outcome(normalize_events, env)} for n, env in cases]


def query_cases():
    qs = [
        {'city': 'İstanbul'}, {'city': ' '}, {'city': 'X', 'currency': 'JPY'}, {'city': 'X', 'lat': 41.0},
        {'city': 'X', 'lat': 91, 'lon': 0}, {'city': 'X', 'mode': 'party'}, {'city': 'X', 'kind': 'person'},
        {'city': 'X', 'budget': -1}, {'city': 'X', 'radius_km': 1}, {'city': 'X', 'radius_km': -1, 'lat': 1, 'lon': 1},
        {'city': 'X', 'limit': 0}, {'city': 'X', 'limit': 51}, {'city': 'X', 'limit': 50},
        {'city': 'X', 'already_sent_today': -1}, {'city': 'X', 'at': 'tomorrow'}, {'city': 'X', 'at': '2026-10-10'},
        {'city': 'X', 'surprise': 1}, {}, {'city': 'X', 'lat': 0, 'lon': 0, 'radius_km': 0},
    ]
    return [{'name': f'query_{i:02d}', 'query': q, 'expect': outcome(lambda d: Query(**d) and True, q)}
            for i, q in enumerate(qs)]


def live(record, observed):
    r = copy.deepcopy(record)
    r.update(origin_live_verified=True, source_observed_at=observed, synthetic=True)
    return r


def decide_cases(catalog):
    cases = []

    def add(name, query, records=None, policy='query_aware'):
        cat = catalog if records is None else records
        res = outcome(lambda: decide(cat, Query(**query), policy).to_dict())
        cases.append({'name': name, 'catalog': 'lab' if records is None else records, 'query': query,
                      'policy': policy, 'expect': res})

    options = {
        'plain': {}, 'open_now': {'open_now': True}, 'quiet': {'quiet': True}, 'budget500': {'budget': 500},
        'budget0': {'budget': 0}, 'galata1km': {'lat': GALATA[0], 'lon': GALATA[1], 'radius_km': 1, 'limit': 7},
        'izmir5km': {'lat': IZMIR[0], 'lon': IZMIR[1], 'radius_km': 5}, 'exact': {'require_exact_session': True},
    }
    ats = {'default': {}, 'aug_evening': {'at': '2026-08-10T21:30:00+03:00'}, 'december': {'at': '2026-12-01T12:00:00Z'}}
    for city, kind, (oname, opt), (aname, at) in itertools.product(
            ['İstanbul', 'izmir', 'Ankara'], ['any', 'event', 'place'], options.items(), ats.items()):
        add(f'lab_{city}_{kind}_{oname}_{aname}', {'city': city, 'kind': kind, **opt, **at})
    for policy, city, (oname, opt) in itertools.product(['blanket_verification', 'simple_safe'], ['İstanbul', 'izmir'],
                                                         options.items()):
        add(f'lab_{policy}_{city}_{oname}', {'city': city, **opt}, policy=policy)
    for cat in ['museum', 'cinema', 'music', 'exhibition', 'nothing', '']:
        add(f'lab_category_{cat or "empty"}', {'city': 'İzmir', 'category': cat, 'at': '2026-08-10T12:00:00+03:00'})
    for limit in [1, 2, 50]:
        add(f'lab_limit_{limit}', {'city': 'İstanbul', 'limit': limit, 'lat': GALATA[0], 'lon': GALATA[1], 'radius_km': 3})
    add('lab_unknown_policy', {'city': 'İstanbul'}, policy='best')
    for mode, opt, sent in itertools.product(['work', 'roam', 'balanced', 'silent'], [False, True], [0, 1, 2]):
        add(f'proactive_{mode}_{opt}_{sent}', {'city': 'İstanbul', 'proactive': True, 'push_opt_in': opt,
                                               'mode': mode, 'already_sent_today': sent})

    for c in regression_cases():
        add(f'regression_{c["id"]}', c['query'], records=[c['record']])

    # Live-verified synthetic overlays on real event rows reach every event branch.
    events = {r['id']: r for r in catalog if r['kind'] == 'event'}
    single_open = events['izmir_event:6960']     # 21:00-21:30, known end
    single_unknown = events['izmir_event:6927']  # duration unknown
    program = events['izmir_event:6949']
    exhibit = events['izmir_event:6958']
    for t in ['2026-08-19T20:00:00+03:00', '2026-08-19T21:10:00+03:00', '2026-08-19T21:30:00+03:00',
              '2026-08-20T09:00:00+03:00', '2026-08-18T12:00:00+03:00']:
        for extra in [{}, {'open_now': True}, {'require_exact_session': True}, {'budget': 10}]:
            add(f'event_single_{t}_{sorted(extra)}', {'city': 'İzmir', 'at': t, **extra},
                records=[live(single_open, '2026-08-19T08:00:00+03:00')])
    for t in ['2026-08-10T20:00:00+03:00', '2026-08-10T22:00:00+03:00']:
        add(f'event_unknown_duration_{t}', {'city': 'İzmir', 'at': t, 'open_now': True},
            records=[live(single_unknown, '2026-08-10T08:00:00')])
    for rec, name in [(program, 'program'), (exhibit, 'exhibition')]:
        for extra in [{}, {'open_now': True}, {'require_exact_session': True}]:
            add(f'event_{name}_{sorted(extra)}', {'city': 'İzmir', 'at': '2026-08-11T12:00:00+03:00', **extra},
                records=[live(rec, '2026-08-11T10:00:00+03:00')])
    stale = live(single_open, '2026-08-01T08:00:00+03:00')
    add('event_stale_source', {'city': 'İzmir', 'at': '2026-08-19T20:00:00+03:00'}, records=[stale])
    cancelled = live(single_open, '2026-08-19T08:00:00+03:00'); cancelled['lifecycle'] = 'cancelled'
    disputed = live(program, '2026-08-11T10:00:00+03:00'); disputed['evidence_status'] = 'disputed'
    private = live(exhibit, '2026-08-11T10:00:00+03:00'); private['rights_scope'] = 'all_rights_reserved'
    add('event_mixed_blocks', {'city': 'izmir', 'at': '2026-08-11T12:00:00+03:00'}, records=[cancelled, disputed, private])
    add('event_bad_observed_raises', {'city': 'İzmir', 'at': '2026-08-19T20:00:00+03:00'},
        records=[live(single_open, 'soon')])

    # Places: crowd, prices, coordinates and ties in distance ordering.
    place = next(r for r in catalog if r['kind'] == 'place')
    base = live(place, '2026-10-10T17:50:00+03:00')
    variants = {
        'crowd_medium': {'crowd': 'medium', 'field_evidence': {'crowd': proof('medium')}},
        'crowd_odd': {'crowd': 'empty'},
        'price_free_fresh': {'price': 0},
        'price_nan_string': {'price': 'NaN'},
        'price_negative': {'price': -5},
        'price_float': {'price': 99.5},
        'no_coords': {'lat': None, 'lon': None},
        'bad_coords_raise': {'lat': 123.0},
        'string_coords_raise': {'lat': 'north'},
        'hours_fresh_closed': {'opening_hours': schedule([['09:00', '17:00']])},
        'hours_unknown_tz': {'opening_hours': {**schedule(), 'timezone': 'Mars/Base'}},
    }
    for name, change in variants.items():
        r = copy.deepcopy(base); r.update(change)
        for q in [{'quiet': True}, {'budget': 100}, {'open_now': True},
                  {'lat': GALATA[0], 'lon': GALATA[1], 'radius_km': 2}]:
            add(f'place_{name}_{sorted(q)}', {'city': 'İstanbul', 'kind': 'place', **q}, records=[r])
    twins = []
    for i, rid in enumerate(['b', 'a', 'c']):
        r = copy.deepcopy(base); r.update(id=f'twin:{rid}', lat=41.0256, lon=28.9741 + (0.001 if i == 2 else 0))
        twins.append(r)
    add('place_distance_ties', {'city': 'İstanbul', 'lat': GALATA[0], 'lon': GALATA[1], 'radius_km': 2}, records=twins)
    priced = copy.deepcopy(base); priced['price'] = 100
    for budget in [100, 99.99, 100.01]:
        add(f'place_budget_boundary_{budget}', {'city': 'İstanbul', 'budget': budget}, records=[priced])
    ring = []
    for i, dlat in enumerate([0.0081, 0.0089, 0.0090, 0.0091, 0.0108]):  # about 0.90 to 1.20 km north
        r = copy.deepcopy(base); r.update(id=f'ring:{i}', lat=GALATA[0] + dlat, lon=GALATA[1]); ring.append(r)
    add('place_radius_boundary', {'city': 'İstanbul', 'lat': GALATA[0], 'lon': GALATA[1], 'radius_km': 1, 'limit': 9},
        records=ring)
    dup = [copy.deepcopy(base), copy.deepcopy(base)]; dup[1]['rights_scope'] = 'none'
    add('place_duplicate_ids', {'city': 'İstanbul'}, records=dup)
    add('empty_catalog', {'city': 'İstanbul'}, records=[])

    # Malformed availability input reaching a decision end to end.
    for text in [' 9:00', '+9:00', '٠٩:٠٠', '09: 0']:
        r = copy.deepcopy(base); r['opening_hours'] = schedule([[text, '20:00']])
        add(f'place_loose_clock_{text!r}', {'city': 'İstanbul', 'kind': 'place', 'open_now': True}, records=[r])
    no_stamp = copy.deepcopy(base); no_stamp['price'] = 100; del no_stamp['source_observed_at']
    add('place_live_without_timestamp', {'city': 'İstanbul', 'budget': 500}, records=[no_stamp])
    for bad in [{'observed_at': 1700000000}, {'valid_until': 0}, {'status': ['disputed']}]:
        r = copy.deepcopy(base); r['price'] = 100; r['field_evidence'] = {'price': {**proof(100), **bad}}
        add(f'place_malformed_price_proof_{sorted(bad)[0]}', {'city': 'İstanbul', 'budget': 500}, records=[r])

    # Naive times are Istanbul local; 2015-03-29 03:30 fell in a DST gap.
    for at in ['2015-03-29T03:30:00', '2015-11-08T03:30:00', '2026-10-10T18:00:00']:
        add(f'naive_at_{at}', {'city': 'İstanbul', 'at': at}, records=[base])
    # Python keeps a DST-gap wall time as given, and compares or subtracts two
    # Istanbul datetimes by wall clock (same tzinfo), not by instant.
    gap_hours = live(base, '2015-03-29T00:30:00+02:00'); gap_hours['opening_hours'] = schedule()
    gap_hours['opening_hours']['weekly']['7'] = [['03:00', '04:00']]  # 2015-03-29 was a Sunday
    for at in ['2015-03-29T03:30:00', '2015-03-29T04:30:00']:
        add(f'dst_gap_hours_{at}', {'city': 'İstanbul', 'kind': 'place', 'open_now': True, 'at': at},
            records=[gap_hours])
    fold_seen = live(base, '2015-11-08T03:15:00+02:00'); fold_seen.update(price=0, opening_hours=schedule())
    add('dst_fold_blanket_age', {'city': 'İstanbul', 'at': '2015-11-08T03:30:00'}, records=[fold_seen],
        policy='blanket_verification')
    fold_event = live(single_open, '2015-11-08T03:00:00+03:00')
    fold_event.update(starts_at='2015-11-08T03:15:00+02:00', ends_at='2015-11-08T03:45:00+02:00')
    for at in ['2015-11-08T03:30:00', '2015-11-08T03:50:00']:
        add(f'dst_fold_event_{at}', {'city': 'İzmir', 'at': at}, records=[fold_event])
    return cases


def temporal_cases(catalog):
    out = []
    events = [r for r in catalog if r['kind'] == 'event'][:6] + [next(r for r in catalog if r['kind'] == 'place')]
    for r in events:
        for t in ['2026-07-01T00:00:00+03:00', '2026-08-10T20:59:59+03:00', '2026-08-10T21:00:00+03:00',
                  '2026-08-19T21:29:59+03:00', '2026-08-19T21:30:00+03:00', '2026-08-31T23:59:59+03:00',
                  '2026-08-10T18:30:00Z']:
            out.append({'name': f'temporal_{r["id"]}_{t}', 'id': r['id'], 'at': t,
                        'expect': outcome(temporal_state, r, dt(t))})
    return out


def reconcile_cases():
    c = lambda e, f, v, root, url='https://example.org/a': {  # noqa: E731
        'entity_id': e, 'field': f, 'value': v, 'publisher_root': root, 'source_url': url}
    sets = {
        'agree': [c('p1', 'price', 100, 'muni'), c('p1', 'price', 100, 'wiki', 'https://example.org/b')],
        'dispute': [c('p1', 'price', 100, 'muni'), c('p1', 'price', 120, 'muni')],
        'multi_entity': [c('p1', 'hours', '09-17', 'a'), c('p2', 'hours', '10-18', 'b'), c('p1', 'hours', '09-18', 'a')],
        'int_float_equal': [c('p1', 'price', 100, 'a'), c('p1', 'price', 100.0, 'b')],
        'bool_int_equal': [c('p1', 'price', 1, 'a'), c('p1', 'price', True, 'b')],
        'mixed_types_raise': [c('p1', 'price', 100, 'a'), c('p1', 'price', 'free', 'b')],
        'unhashable_raise': [c('p1', 'hours', ['09', '17'], 'a')],
        'single_null': [c('p1', 'crowd', None, 'a')],
        'numeric_entity': [c(5, 'price', 1, 'a'), c(5.0, 'price', 2, 'a')],
        'big_ints': [c('p1', 'id', 9007199254740993, 'a'), c('p1', 'id', 9007199254740992, 'b'),
                     c('p1', 'id', 9007199254740992.0, 'c')],
        'empty': [],
    }
    return [{'name': f'reconcile_{k}', 'claims': v, 'expect': outcome(reconcile_claims, v)} for k, v in sets.items()]


def model_selection_cases(catalog):
    d = decide(catalog, Query(city='İstanbul', lat=GALATA[0], lon=GALATA[1], radius_km=3, limit=3))
    ids = [r['id'] for r in d.selected]
    proposals = [[], ids[:1], ids[::-1], ids + ids[:1], ['wikidata:Q0'], ids[:1] + ['x', 'a']]
    return {'decision': d.to_dict(), 'cases': [
        {'name': f'model_{i}', 'proposed': p, 'expect': check_model_selection(d, p)} for i, p in enumerate(proposals)]}


def cli_cases():
    out = []
    for path in sorted((LAB / 'examples').glob('*.json')):
        result = decide(load_catalog(), Query(**load_json(path)))
        out.append({'name': path.name, 'query': load_json(path),
                    'stdout': json.dumps(result.to_dict(), ensure_ascii=False, indent=2)})
    return out


def build_core():
    catalog = load_catalog()
    return {
        'reference': 'labs/core/kepcore/core.py (Python); see docs/adr/0034-rust-core-port.md',
        'fold': fold_cases(),
        'haversine': haversine_cases(),
        'dt': dt_cases(),
        'catalog': catalog,
        'normalize_errors': normalize_error_cases(),
        'query': query_cases(),
        'temporal_state': temporal_cases(catalog),
        'decide': decide_cases(catalog),
        'reconcile': reconcile_cases(),
        'model_selection': model_selection_cases(catalog),
        'cli': cli_cases(),
    }


def context_queries():
    return [
        {'city': 'İstanbul', 'lat': GALATA[0], 'lon': GALATA[1], 'radius_km': 3, 'limit': 3},
        {'city': 'İstanbul', 'budget': 100, 'limit': 2},
        {'city': 'İzmir', 'at': '2026-08-10T12:00:00+03:00', 'category': 'cinema'},
        {'city': 'İstanbul', 'kind': 'place', 'open_now': True},
        {'city': 'Nowhere'},
        {'city': 'İstanbul', 'proactive': True, 'mode': 'work'},
    ]


def reply_cases(catalog):
    ctx = context_for_model(decide(catalog, Query(**context_queries()[0])))
    c0, c1 = ctx['candidates'][0], ctx['candidates'][1]
    ok_claim = {'id': c0['id'], 'field': 'name', 'value': c0['facts']['name'],
                'source_record_hash': c0['source_record_hash']}
    fact_field = next(f for f in ('distance_km', 'price', 'kind') if f in c0['facts'])
    replies = {
        'not_object': [c0['id']],
        'extra_field': {'snapshot_hash': ctx['snapshot_hash'], 'selected_ids': [], 'note': 'hi'},
        'stale': {'snapshot_hash': 'x' * 64, 'selected_ids': [c0['id']]},
        'missing_hash': {'selected_ids': [c0['id']]},
        'ok_ids_only': {'snapshot_hash': ctx['snapshot_hash'], 'selected_ids': [c1['id'], c0['id']]},
        'ok_empty': {'snapshot_hash': ctx['snapshot_hash'], 'selected_ids': []},
        'ids_missing': {'snapshot_hash': ctx['snapshot_hash']},
        'ids_not_list': {'snapshot_hash': ctx['snapshot_hash'], 'selected_ids': c0['id']},
        'ids_non_str': {'snapshot_hash': ctx['snapshot_hash'], 'selected_ids': [c0['id'], 7]},
        'ids_duplicate': {'snapshot_hash': ctx['snapshot_hash'], 'selected_ids': [c0['id'], c0['id']]},
        'ids_unknown': {'snapshot_hash': ctx['snapshot_hash'], 'selected_ids': ['wikidata:Q0']},
        'claims_null': {'snapshot_hash': ctx['snapshot_hash'], 'selected_ids': [c0['id']], 'claims': None},
        'claims_dict': {'snapshot_hash': ctx['snapshot_hash'], 'selected_ids': [c0['id']], 'claims': {}},
        'claim_ok': {'snapshot_hash': ctx['snapshot_hash'], 'selected_ids': [c0['id']], 'claims': [ok_claim]},
        'claim_numeric_fact': {'snapshot_hash': ctx['snapshot_hash'], 'selected_ids': [c0['id']], 'claims': [
            {**ok_claim, 'field': fact_field, 'value': c0['facts'][fact_field]}]},
        'claim_float_vs_int': {'snapshot_hash': ctx['snapshot_hash'], 'selected_ids': [c0['id']], 'claims': [
            {**ok_claim, 'field': fact_field, 'value': float(c0['facts'][fact_field])
             if isinstance(c0['facts'][fact_field], int) else c0['facts'][fact_field]}]},
        'claim_extra_key': {'snapshot_hash': ctx['snapshot_hash'], 'selected_ids': [c0['id']], 'claims': [
            {**ok_claim, 'why': 'x'}]},
        'claim_not_object': {'snapshot_hash': ctx['snapshot_hash'], 'selected_ids': [c0['id']], 'claims': ['x']},
        'claim_id_type': {'snapshot_hash': ctx['snapshot_hash'], 'selected_ids': [c0['id']], 'claims': [
            {**ok_claim, 'id': 1}]},
        'claim_unselected': {'snapshot_hash': ctx['snapshot_hash'], 'selected_ids': [c1['id']], 'claims': [ok_claim]},
        'claim_unknown_field': {'snapshot_hash': ctx['snapshot_hash'], 'selected_ids': [c0['id']], 'claims': [
            {**ok_claim, 'field': 'opening_hours'}]},
        'claim_wrong_revision': {'snapshot_hash': ctx['snapshot_hash'], 'selected_ids': [c0['id']], 'claims': [
            {**ok_claim, 'source_record_hash': '0' * 64}]},
        'claim_wrong_value': {'snapshot_hash': ctx['snapshot_hash'], 'selected_ids': [c0['id']], 'claims': [
            {**ok_claim, 'value': 'Somewhere else'}]},
        'claim_bool_for_zero': {'snapshot_hash': ctx['snapshot_hash'], 'selected_ids': [c0['id']], 'claims': [
            {**ok_claim, 'field': fact_field, 'value': False}]},
    }
    out = [{'name': f'reply_{k}', 'context': ctx, 'reply': v, 'expect': outcome(validate_structured_reply, ctx, v)}
           for k, v in replies.items()]
    # Hand-built contexts reach the reference's error paths.
    ok = {'snapshot_hash': 'h', 'selected_ids': ['a'], 'claims': [
        {'id': 'a', 'field': 'name', 'value': 'A', 'source_record_hash': 'r'}]}
    row = {'id': 'a', 'source_record_hash': 'r', 'facts': {'name': 'A'}}
    contexts = {
        'no_hash': {'candidates': [row]},
        'no_candidates': {'snapshot_hash': 'h'},
        'candidates_null': {'snapshot_hash': 'h', 'candidates': None},
        'candidates_empty_str': {'snapshot_hash': 'h', 'candidates': ''},
        'candidates_str': {'snapshot_hash': 'h', 'candidates': 'a'},
        'candidate_not_object': {'snapshot_hash': 'h', 'candidates': [['a']]},
        'candidate_no_id': {'snapshot_hash': 'h', 'candidates': [{'source_record_hash': 'r'}]},
        'candidate_list_id': {'snapshot_hash': 'h', 'candidates': [{'id': ['a']}]},
        'candidate_int_id': {'snapshot_hash': 'h', 'candidates': [{'id': 1}, row]},
        'duplicate_ids_last_wins': {'snapshot_hash': 'h', 'candidates': [row, {**row, 'source_record_hash': 's'}]},
        'facts_missing': {'snapshot_hash': 'h', 'candidates': [{'id': 'a', 'source_record_hash': 'r'}]},
        'facts_list': {'snapshot_hash': 'h', 'candidates': [{**row, 'facts': ['name']}]},
        'facts_str': {'snapshot_hash': 'h', 'candidates': [{**row, 'facts': 'surname'}]},
        'facts_null': {'snapshot_hash': 'h', 'candidates': [{**row, 'facts': None}]},
        'row_no_revision': {'snapshot_hash': 'h', 'candidates': [{'id': 'a', 'facts': {'name': 'A'}}]},
        'hash_int_float': {'snapshot_hash': 1, 'candidates': [row]},
        'context_list': [row],
    }
    for k, c in contexts.items():
        reply = {**ok, 'snapshot_hash': 1.0} if k == 'hash_int_float' else ok
        out.append({'name': f'context_{k}', 'context': c, 'reply': reply,
                    'expect': outcome(validate_structured_reply, c, reply)})
    return out


def scheduler_cases():
    s = lambda sid, e, lo=1, hi=24, **kw: {'source_id': sid, 'elapsed_hours': e,  # noqa: E731
                                           'min_interval_hours': lo, 'max_interval_hours': hi, **kw}
    sets = {
        'empty': ([], 3),
        'too_soon': ([s('a', 0.5)], 3),
        'at_min': ([s('a', 1)], 3),
        'overdue_beats_popular': ([s('pop', 10, priority=50, observed_change_rate=3), s('beat', 24)], 1),
        'overdue_ratio_order': ([s('x', 30), s('y', 48), s('z', 25, hi=12)], 3),
        'score_order': ([s('a', 5, priority=2), s('b', 5, observed_change_rate=1.5), s('c', 6)], 3),
        'tie_by_id': ([s('b', 5), s('a', 5), s('c', 5)], 3),
        'zero_priority_tie': ([s('b', 5, priority=0), s('a', 5, priority=-0.0)], 2),
        'negative_priority': ([s('a', 5, priority=-1), s('b', 5)], 2),
        'budget_cut': ([s('a', 5), s('b', 6), s('c', 7)], 2),
        'budget_zero': ([s('a', 5)], 0),
        'not_approved': ([s('a', 5, approved=False), s('b', 5)], 2),
        'daily_cap': ([s('a', 5, calls_today=24), s('b', 5, calls_today=3, daily_cap=3), s('c', 5, calls_today=2)], 3),
        'retry_after': ([s('a', 50, retry_after_hours=0.5), s('b', 5)], 2),
        'float_counts': ([s('a', 5, calls_today=2.5, daily_cap=3)], 1),
        'negative_budget': ([s('a', 5)], -1),
        'bad_min': ([s('a', 5, lo=0)], 1),
        'bad_max': ([s('a', 5, lo=4, hi=3)], 1),
        'bad_elapsed': ([s('a', -1)], 1),
        'bad_rate': ([s('a', 5, observed_change_rate=-0.1)], 1),
        'unknown_field': ([{**s('a', 5), 'popularity': 1}], 1),
        'missing_field': ([{'source_id': 'a', 'elapsed_hours': 5}], 1),
    }

    def run(raw, budget):
        return due_sources([SourceClock(**r) for r in raw], budget)
    return [{'name': f'due_{k}', 'sources': v, 'budget': b, 'expect': outcome(run, v, b)}
            for k, (v, b) in sets.items()]


def build_boundary():
    catalog = load_catalog()
    return {
        'reference': 'labs/core/kepcore/{model_boundary,scheduler}.py (Python); see docs/adr/0034-rust-core-port.md',
        'context': [{'name': f'context_{i}', 'query': q,
                     'expect': outcome(lambda q: context_for_model(decide(catalog, Query(**q))), q)}
                    for i, q in enumerate(context_queries())],
        'reply': reply_cases(catalog),
        'due_sources': scheduler_cases(),
    }


OUTPUTS = {'availability.json': build_availability, 'core.json': build_core,
           'boundary.json': build_boundary}


def render(data):
    return json.dumps(data, ensure_ascii=False, indent=1, sort_keys=False) + '\n'


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--check', action='store_true', help='exit 1 if the committed vectors differ')
    a = p.parse_args()
    stale = 0
    for name, build in OUTPUTS.items():
        target = HERE / name
        text = render(build())
        if a.check:
            if not target.exists() or target.read_text(encoding='utf-8') != text:
                print(f'{target} is stale; run python3 rust/parity/export_vectors.py', file=sys.stderr)
                stale = 1
            else:
                print(f'{name}: up to date')
        else:
            target.write_text(text, encoding='utf-8')
            print(f'wrote {target}')
    return stale


if __name__ == '__main__':
    sys.exit(main())
