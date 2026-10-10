"""Small, explicit availability contract; not a general opening-hours parser.

Supported: complete ISO-weekday weekly intervals, IANA zone, date overrides.
Intervals are [open, close), and an end earlier than start crosses midnight.
A date override replaces the whole day's regular hours, including carry-over.
Unsupported/malformed input is UNKNOWN, never an implicit open flag.
"""
from __future__ import annotations
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import math
import hashlib
import json


def minute(text: str, *, end: bool = False) -> int:
    if not isinstance(text, str) or len(text) != 5 or text[2] != ':':
        raise ValueError('Expected HH:MM')
    h, m = int(text[:2]), int(text[3:])
    if end and h == 24 and m == 0:
        return 1440
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError('Invalid clock time')
    return h * 60 + m


def intervals(raw: object) -> list[tuple[int, int]]:
    if not isinstance(raw, list):
        raise ValueError('Intervals must be a list; [] explicitly means closed')
    out = []
    for pair in raw:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise ValueError('Expected [open, close]')
        a, b = minute(pair[0]), minute(pair[1], end=True)
        if a == b:
            raise ValueError('Equal open/close is ambiguous, use 00:00-24:00')
        out.append((a, b))
    return out


def opening_status(hours: object, at: datetime) -> str:
    if not isinstance(hours, dict) or at.tzinfo is None:
        return 'UNKNOWN'
    try:
        zone = ZoneInfo(hours['timezone'])
        here = at.astimezone(zone)
        weekly = hours['weekly']
        overrides = hours.get('exceptions', {})
        if not isinstance(weekly, dict) or not isinstance(overrides, dict):
            return 'UNKNOWN'
        # Require explicit status for all days, not missing = closed.
        if not all(str(i) in weekly for i in range(1, 8)):
            return 'UNKNOWN'
        parsed = {k: intervals(v) for k, v in weekly.items()}
        exceptions = {k: intervals(v) for k, v in overrides.items()}
        d = here.date(); prev = d - timedelta(days=1)
        m = here.hour * 60 + here.minute + here.second / 60
        today = exceptions.get(d.isoformat(), parsed[str(here.isoweekday())])
        for a, b in today:
            if (a < b and a <= m < b) or (b < a and m >= a):
                return 'OPEN'
        if d.isoformat() not in exceptions:
            yesterday = exceptions.get(prev.isoformat(), parsed[str(prev.isoweekday())])
            if any(b < a and m < b for a, b in yesterday):
                return 'OPEN'
        return 'CLOSED'
    except (KeyError, TypeError, ValueError, ZoneInfoNotFoundError, OverflowError):
        return 'UNKNOWN'


def field_is_fresh(record: dict, field: str, at: datetime, max_hours: float) -> bool:
    """Explicit field evidence overrides the broad record timestamp.

    Acquisition time is never substituted for source observation time.
    Timestamp freshness means a source was checked, not ground-truth certainty.
    """
    field_proofs = record.get('field_evidence', {})
    if not isinstance(field_proofs, dict):
        return False
    proof = field_proofs.get(field)
    if proof is None:
        proof = {'origin_live_verified': record.get('origin_live_verified'),
                 'observed_at': record.get('source_observed_at')}
    if field_proofs.get(field) is not None:
        expected=hashlib.sha256(json.dumps(record.get(field),sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
        if not isinstance(proof,dict) or proof.get('value_hash')!=expected:
            return False
    if not isinstance(proof, dict) or not proof.get('origin_live_verified'):
        return False
    if proof.get('status') in {'disputed', 'unknown', 'retracted'}:
        return False
    try:
        stamp = datetime.fromisoformat(proof['observed_at'].replace('Z', '+00:00'))
        if stamp.tzinfo is None: return False
        age = (at - stamp).total_seconds() / 3600
        if not (math.isfinite(age) and 0 <= age <= max_hours): return False
        until = proof.get('valid_until')
        if until:
            deadline = datetime.fromisoformat(until.replace('Z', '+00:00'))
            if deadline.tzinfo is None or at >= deadline: return False
        return True
    except (KeyError, TypeError, ValueError, OverflowError):
        return False
