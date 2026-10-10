"""KEP-SRC-001: bounded source registry and research-only ingestion.

Production scraping and commercial content redistribution are NOT enabled.
Requests are opt-in, pinned to reviewed URLs, no redirects/retries.
This is an offline-testable prototype, not a hardened network sandbox.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone, timedelta
from pathlib import Path
from .core import dt
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError
import hashlib
import ipaddress
import json

ROOT = Path(__file__).resolve().parents[1]
REGISTERED_USES = frozenset({'research_ingest', 'consumer_display'})
VALID_STATUSES = frozenset({'pending', 'approved', 'paused', 'blocked'})
VALID_FORMATS = frozenset({'izmir_event_json', 'website_review_required'})
EVENT_FIELDS = ('Id', 'Tur', 'Adi', 'EtkinlikBaslamaTarihi',
                'EtkinlikBitisTarihi', 'EtkinlikMerkezi', 'UcretsizMi',
                'EtkinlikUrl', 'BiletSatisLinki')
MANDATORY_EVENT_FIELDS = EVENT_FIELDS[:6]


def _public_https(url: str) -> str:
    """Reject non-web, local, credentialed or nonstandard-ported URLs.

    This syntactic check alone is NOT a DNS rebinding / egress firewall.
    """
    if not isinstance(url, str) or not url or any(ch.isspace() or ord(ch) < 32 for ch in url):
        raise ValueError('Invalid URL')
    u = urlsplit(url)
    try:
        port = u.port
        host = (u.hostname or '').lower().rstrip('.')
    except ValueError as exc:
        raise ValueError('Invalid URL port') from exc
    if (u.scheme != 'https' or not host or u.username or u.password or u.fragment
            or port not in (None, 443) or '\\' in url):
        raise ValueError('Only plain HTTPS origins are allowed')
    if host in {'localhost'} or host.endswith(('.localhost', '.local', '.internal')) or '.' not in host:
        raise ValueError('Local origins are forbidden')
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError('IP literal origins are forbidden')
    return host


@dataclass(frozen=True)
class Source:
    id: str
    url: str
    city: str
    format: str
    status: str
    approved_uses: tuple[str, ...]
    license: str = ''
    rights_evidence_url: str = ''
    rights_reviewed_at: str = ''
    attribution: str = ''
    min_poll_minutes: int = 360
    max_poll_minutes: int = 1440
    daily_request_cap: int = 4
    max_response_bytes: int = 2_000_000
    review_note: str = ''

    @classmethod
    def parse(cls, raw: Mapping[str, Any]) -> 'Source':
        allowed = set(cls.__dataclass_fields__)
        if not isinstance(raw, dict) or set(raw) - allowed:
            raise ValueError('Unsupported source fields')
        data = dict(raw)
        uses = data.get('approved_uses', [])
        if not isinstance(uses, list) or any(not isinstance(x, str) for x in uses):
            raise ValueError('Approved uses must be a string list')
        data['approved_uses'] = tuple(uses)
        source = cls(**data)
        source.validate()
        return source

    def validate(self) -> None:
        if not self.id or not all(ch.isascii() and (ch.isalnum() or ch == '_') for ch in self.id):
            raise ValueError('Invalid source ID')
        _public_https(self.url)
        if not self.city.strip() or self.format not in VALID_FORMATS or self.status not in VALID_STATUSES:
            raise ValueError('Invalid source classification')
        if not set(self.approved_uses) <= REGISTERED_USES or len(set(self.approved_uses)) != len(self.approved_uses):
            raise ValueError('Invalid approved uses')
        if self.status != 'approved' and self.approved_uses:
            raise ValueError('A pending/blocked source cannot grant data rights')
        if self.status == 'approved':
            if not self.approved_uses or not self.license or not self.rights_evidence_url or not self.rights_reviewed_at:
                raise ValueError('An approved source needs documented rights review')
            _public_https(self.rights_evidence_url)
            datetime.fromisoformat(self.rights_reviewed_at).date()
        elif self.format != 'website_review_required' and not self.review_note:
            raise ValueError('Non-approved data adapter requires review note')
        if not (1 <= self.min_poll_minutes <= self.max_poll_minutes <= 43200):
            raise ValueError('Invalid poll bounds')
        if not (1 <= self.daily_request_cap <= 10000):
            raise ValueError('Invalid request cap')
        if not (1024 <= self.max_response_bytes <= 5_000_000):
            raise ValueError('Invalid response bound')

    def allows(self, purpose: str) -> bool:
        return self.status == 'approved' and purpose in self.approved_uses


def load_sources(path: Path = ROOT / 'sources/registry.json') -> dict[str, Source]:
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or set(data) != {'version', 'sources'} or data['version'] != 1:
        raise ValueError('Unsupported source registry version')
    if not isinstance(data['sources'], list):
        raise ValueError('Sources must be a list')
    results: dict[str, Source] = {}
    for raw in data['sources']:
        source = Source.parse(raw)
        if source.id in results:
            raise ValueError('Duplicate source ID')
        results[source.id] = source
    return results


@dataclass(frozen=True)
class PollState:
    last_attempt_at: str | None = None
    last_day: str | None = None
    requests_today: int = 0
    etag: str | None = None
    last_modified: str | None = None
    last_body_sha256: str | None = None
    paused_reason: str | None = None


@dataclass(frozen=True)
class FetchResponse:
    status: int
    body: bytes = b''
    headers: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class PollResult:
    status: str
    state: PollState
    envelope: dict[str, Any] | None = None
    reason: str | None = None


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def https_transport(url: str, headers: Mapping[str, str], max_bytes: int) -> FetchResponse:
    """Explicit production HTTPS transport; source URL is always looked up in registry.

    Only call from a controlled egress environment. No automatic redirect or retry.
    """
    _public_https(url)
    request = Request(url, headers=dict(headers), method='GET')
    opener = build_opener(_NoRedirect())
    try:
        with opener.open(request, timeout=20) as response:
            body = response.read(max_bytes + 1)
            return FetchResponse(response.status, body, dict(response.headers.items()))
    except HTTPError as exc:
        if exc.code == 304:
            return FetchResponse(304, b'', dict(exc.headers.items()))
        return FetchResponse(exc.code, b'', dict(exc.headers.items()))


def _select_izmir_events(body: bytes) -> list[dict]:
    raw = json.loads(body)
    if not isinstance(raw, list) or len(raw) > 20_000:
        raise ValueError('Unexpected events response shape or size')
    if not raw:
        raise ValueError('Suspicious empty event feed: review required')
    records = []
    seen = set()
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError('Invalid event item')
        if any(k not in item for k in MANDATORY_EVENT_FIELDS):
            raise ValueError('Missing required event field')
        if not isinstance(item['Id'], int) or isinstance(item['Id'], bool) or item['Id'] in seen:
            raise ValueError('Invalid or duplicate event ID')
        seen.add(item['Id'])
        if any(not isinstance(item[k], str) or not item[k].strip() for k in ('Tur', 'Adi', 'EtkinlikBaslamaTarihi', 'EtkinlikBitisTarihi', 'EtkinlikMerkezi')):
            raise ValueError('Invalid required event string')
        if dt(item['EtkinlikBitisTarihi']) < dt(item['EtkinlikBaslamaTarihi']):
            raise ValueError('Reversed event interval')
        if item.get('UcretsizMi') is not None and not isinstance(item['UcretsizMi'], bool):
            raise ValueError('Invalid free flag')
        for k in ('EtkinlikUrl', 'BiletSatisLinki'):
            if item.get(k) is not None and not isinstance(item[k], str):
                raise ValueError('Invalid optional event link')
        records.append({k: item.get(k) for k in EVENT_FIELDS})
    return records


def poll(source: Source, *, now: datetime, state: PollState, transport: Callable[[str, Mapping[str, str], int], FetchResponse], purpose: str = 'research_ingest') -> PollResult:
    """A single controlled fetch. Nothing is published or stored automatically."""
    if not source.allows(purpose):
        return PollResult('denied', state, reason='SOURCE_RIGHTS_NOT_APPROVED')
    if source.format != 'izmir_event_json':
        return PollResult('denied', state, reason='ADAPTER_NOT_APPROVED')
    if now.tzinfo is None:
        raise ValueError('Clock must be timezone-aware')
    instant = now.astimezone(timezone.utc)
    today = instant.date().isoformat()
    count = state.requests_today if state.last_day == today else 0
    if state.paused_reason:
        return PollResult('paused', state, reason=state.paused_reason)
    if state.last_attempt_at is not None:
        last = datetime.fromisoformat(state.last_attempt_at)
        if last.tzinfo is None:
            raise ValueError('Invalid stored timestamp')
        elapsed = (instant - last.astimezone(timezone.utc)).total_seconds()/60
        if elapsed < 0:
            return PollResult('denied', state, reason='CLOCK_MOVED_BACKWARDS')
        if elapsed < source.min_poll_minutes:
            return PollResult('skipped', state, reason='MIN_INTERVAL_NOT_ELAPSED')
    if count >= source.daily_request_cap:
        return PollResult('skipped', state, reason='DAILY_QUOTA_REACHED')
    request_headers = {'User-Agent': 'KEPResearch/0.4 (+https://github.com/ziyabeey/kep)', 'Accept': 'application/json'}
    if state.etag:
        request_headers['If-None-Match'] = state.etag
    if state.last_modified:
        request_headers['If-Modified-Since'] = state.last_modified
    new_state = replace(state, last_attempt_at=instant.isoformat(), last_day=today, requests_today=count + 1)
    try:
        result = transport(source.url, request_headers, source.max_response_bytes)
    except (OSError, TimeoutError) as exc:
        # A failed network request still consumes one local attempt slot.
        # No immediate retry storm and no partial updates.
        return PollResult('error', new_state, reason=f'NETWORK_ERROR:{type(exc).__name__}')
    headers = {str(k).lower(): str(v) for k, v in result.headers.items()}
    if result.status in (401, 403, 429):
        return PollResult('paused', replace(new_state, paused_reason=f'HTTP_{result.status}_REVIEW_REQUIRED'), reason=f'HTTP_{result.status}_REVIEW_REQUIRED')
    if result.status == 304:
        return PollResult('not_modified', new_state)
    if result.status != 200:
        return PollResult('error', new_state, reason=f'HTTP_{result.status}')
    if not isinstance(result.body, bytes) or len(result.body) > source.max_response_bytes:
        return PollResult('paused', replace(new_state, paused_reason='RESPONSE_TOO_LARGE'), reason='RESPONSE_TOO_LARGE')
    try:
        records = _select_izmir_events(result.body)
    except (UnicodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return PollResult('paused', replace(new_state, paused_reason='SCHEMA_REVIEW_REQUIRED'), reason=f'SCHEMA_REVIEW_REQUIRED:{type(exc).__name__}')
    digest = hashlib.sha256(result.body).hexdigest()
    new_state = replace(new_state, etag=headers.get('etag', state.etag), last_modified=headers.get('last-modified', state.last_modified), last_body_sha256=digest)
    if digest == state.last_body_sha256:
        return PollResult('unchanged', new_state)
    captured_at = instant.isoformat()
    envelope = {'meta': {'source_id': source.id, 'source_city': source.city, 'source_url': source.url,
                         'license': source.license, 'rights_evidence_url': source.rights_evidence_url,
                         'attribution': source.attribution, 'acquisition_method': 'reviewed_api_json',
                         'http_retrieved_at': captured_at, 'acquired_date': today,
                         'source_observed_at': None, 'origin_live_verified': False,
                         'rights_scope': 'research_only', 'consumer_display_approved': False,
                         'response_headers': {k: v for k, v in headers.items() if k in ('etag', 'last-modified', 'cache-control', 'date')},
                         'sha256_http_body': digest, 'selected_fields_only': True,
                         'review_required': 'Response retrieval is not event-level live verification'},
                'records': records}
    return PollResult('changed', new_state, envelope)
