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

from kepcore.availability import field_is_fresh, intervals, minute, opening_status  # noqa: E402
from kepcore.core import stable_hash  # noqa: E402

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
             '2026-10-10T17:50:00.+03:00', '2026-10-10T17:50:00+3:00', '2026-10-10T17:50:00+03:60',
             # Accepted by Python 3.11+, rejected by the Rust subset (fails closed; see isotime.rs).
             '20261010T175000+0300', '2026-W41-6T17:50:00+03:00', '2026-10-10T175000+03:00',
             '2026-10-10T17:50:00 +03:00', '2026-10-10T17:50:00+03:00:30.5']
    out = []
    for t in texts:
        res = outcome(lambda x: datetime.fromisoformat(x.replace('Z', '+00:00')).isoformat(), t)
        out.append({'name': f'iso_{t!r}', 'text': t, 'expect': res})
    return out


def build():
    return {
        'reference': 'labs/core (Python); see docs/adr/0034-rust-core-port.md',
        'canon': canon_cases(),
        'isotime': isotime_cases(),
        'minute': minute_cases(),
        'intervals': intervals_cases(),
        'opening_status': opening_cases(),
        'field_is_fresh': fresh_cases(),
    }


def render(data):
    return json.dumps(data, ensure_ascii=False, indent=1, sort_keys=False) + '\n'


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--check', action='store_true', help='exit 1 if the committed vectors differ')
    a = p.parse_args()
    target = HERE / 'availability.json'
    text = render(build())
    if a.check:
        if not target.exists() or target.read_text(encoding='utf-8') != text:
            print(f'{target} is stale; run python3 rust/parity/export_vectors.py', file=sys.stderr)
            return 1
        print(f'{target.name}: up to date')
        return 0
    target.write_text(text, encoding='utf-8')
    print(f'wrote {target}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
