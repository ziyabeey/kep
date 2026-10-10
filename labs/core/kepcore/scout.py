"""KEP-EVAL-002 offline-first read-only scout evaluation primitives.

No network, browser, or model is instantiated here. Browser/model outputs are
untrusted *candidates*, never verified KEP evidence. Replays are hand-authored.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from hashlib import sha256
from html.parser import HTMLParser
from typing import Any, Mapping
import json
import re
import unicodedata

from .radar import Source

MAX_HTML_BYTES = 200_000
MAX_LD_BLOCKS = 12
MAX_CANDIDATES = 40
MAX_REPLAY_TEXT = 20_000


@dataclass(frozen=True)
class ScoutCandidate:
    title: str
    starts_at: str
    venue: str
    source_url: str
    method: str
    date_precision: str
    event_state: str = 'unspecified'
    evidence_excerpt: str = ''
    review_required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ScoutResult:
    status: str
    candidates: tuple[ScoutCandidate, ...]
    browser_needed: bool
    source_id: str
    detail: str = ''

    def to_dict(self) -> dict[str, Any]:
        return {'status': self.status, 'source_id': self.source_id,
                'browser_needed': self.browser_needed, 'detail': self.detail,
                'candidates': [c.to_dict() for c in self.candidates]}


class _PageReader(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._script_depth = 0
        self._inside_jsonld = False
        self._inside_hidden = 0
        self.jsonld_blocks: list[str] = []
        self._script_parts: list[str] = []
        self.visible_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag in {'style', 'noscript', 'template'}:
            self._inside_hidden += 1
        elif tag == 'script':
            self._script_depth += 1
            self._inside_jsonld = 'application/ld+json' in (values.get('type') or '').lower()
            self._script_parts.clear()

    def handle_data(self, data: str) -> None:
        if self._script_depth and self._inside_jsonld:
            self._script_parts.append(data)
        elif not self._script_depth and not self._inside_hidden and data.strip():
            self.visible_parts.append(data.strip())

    def handle_endtag(self, tag: str) -> None:
        if tag in {'style', 'noscript', 'template'} and self._inside_hidden:
            self._inside_hidden -= 1
        elif tag == 'script' and self._script_depth:
            if self._inside_jsonld and len(self.jsonld_blocks) < MAX_LD_BLOCKS:
                self.jsonld_blocks.append(''.join(self._script_parts))
            self._script_depth -= 1
            self._inside_jsonld = False
            self._script_parts.clear()

    @property
    def visible_text(self) -> str:
        return ' '.join(' '.join(self.visible_parts).split())[:MAX_REPLAY_TEXT]


def _date_precision(value: str) -> str | None:
    if not isinstance(value, str) or len(value) > 40:
        return None
    try:
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            date.fromisoformat(value)
            return 'date'
        moment = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if moment.tzinfo is None or moment.utcoffset() is None:
            return None
        return 'datetime'
    except (ValueError, OverflowError):
        return None


def _text(value: Any, limit: int = 220) -> str:
    return ' '.join(str(value or '').split())[:limit]


def _event_nodes(raw: Any, depth: int = 0):
    if depth > 5:
        return
    if isinstance(raw, list):
        for item in raw[:MAX_CANDIDATES]:
            yield from _event_nodes(item, depth + 1)
    elif isinstance(raw, dict):
        t = raw.get('@type', [])
        types = [t] if isinstance(t, str) else t if isinstance(t, list) else []
        if any(isinstance(t, str) and (t == 'Event' or t.endswith('/Event')) for t in types):
            yield raw
        graph = raw.get('@graph')
        if graph is not None:
            yield from _event_nodes(graph, depth + 1)


def _build_event(raw: Mapping[str, Any], source_url: str) -> ScoutCandidate | None:
    title = _text(raw.get('name'))
    starts = raw.get('startDate')
    venue_obj = raw.get('location')
    venue = _text(venue_obj.get('name')) if isinstance(venue_obj, dict) else _text(venue_obj)
    precision = _date_precision(starts)
    if not title or not venue or not precision:
        return None
    raw_status = raw.get('eventStatus', '')
    state = 'cancelled' if isinstance(raw_status, str) and raw_status.endswith('EventCancelled') else 'unspecified'
    return ScoutCandidate(title, starts, venue, source_url, 'jsonld', precision,
                          state, evidence_excerpt='JSON-LD Event; independent validation pending')


def _uniq(candidates: list[ScoutCandidate]) -> tuple[ScoutCandidate, ...]:
    result = {}
    for c in candidates:
        # Case folding is not sufficient for Turkish dotted I; NFKC makes
        # normalization stable but must never merge different dates/venues.
        key = tuple(unicodedata.normalize('NFKC', v).casefold() for v in
                    (c.title, c.starts_at, c.venue, c.source_url))
        result.setdefault(key, c)
    return tuple(result.values())


def inspect_html(html: str, source_url: str) -> tuple[tuple[ScoutCandidate, ...], str]:
    if not isinstance(html, str) or len(html.encode('utf-8')) > MAX_HTML_BYTES:
        raise ValueError('HTML payload too large or invalid')
    reader = _PageReader()
    reader.feed(html)
    candidates: list[ScoutCandidate] = []
    for block in reader.jsonld_blocks:
        try:
            parsed = json.loads(block)
        except (json.JSONDecodeError, UnicodeError):
            continue
        for item in _event_nodes(parsed):
            event = _build_event(item, source_url)
            if event is not None:
                candidates.append(event)
            if len(candidates) >= MAX_CANDIDATES:
                break
    return _uniq(candidates), reader.visible_text


def _safe_claims(replay: list[dict[str, Any]] | None, visible_text: str, source_url: str) -> tuple[ScoutCandidate, ...]:
    """A hand-authored or future model response is *not* ground truth.

    A literal excerpt must appear in DOM text. Date interpretation still
    requires human/external validation; never silently promote to verified.
    """
    if not isinstance(replay, list) or len(replay) > MAX_CANDIDATES:
        return ()
    accepted = []
    for item in replay:
        if not isinstance(item, dict) or set(item) != {'title', 'starts_at', 'venue', 'observed_date', 'quote'}:
            continue
        title, starts, venue = (_text(item.get(k)) for k in ('title', 'starts_at', 'venue'))
        precision = _date_precision(starts)
        quoted = _text(item.get('quote'), 1000)
        date_quote = _text(item.get('observed_date'), 70)
        if not all((title, starts, venue, quoted, date_quote, precision)):
            continue
        if not all(token.casefold() in quoted.casefold() for token in (title, venue, date_quote)):
            continue
        if quoted not in visible_text:
            continue
        accepted.append(ScoutCandidate(title, starts, venue, source_url,
                                       'offline_manual_replay', precision,
                                       evidence_excerpt=quoted))
    return _uniq(accepted)


def evaluate_scout(source: Source, html: str, *, mode: str,
                   replay: list[dict[str, Any]] | None = None) -> ScoutResult:
    """Compare deterministic, replay and hybrid with *identical* snapshots.

    Source has to be rights-approved even for a model replay. This method has
    no network effects and no model calls. Replays are synthetic/manual.
    """
    if mode not in {'script', 'manual_replay', 'hybrid'}:
        raise ValueError('Unknown mode')
    if not source.allows('research_ingest'):
        return ScoutResult('denied', (), False, source.id, 'SOURCE_RIGHTS_NOT_APPROVED')
    try:
        extracted, visible = inspect_html(html, source.url)
    except ValueError as exc:
        return ScoutResult('paused', (), False, source.id, str(exc))
    if mode == 'script':
        return ScoutResult('candidate' if extracted else 'empty', extracted, False, source.id)
    replayed = _safe_claims(replay, visible, source.url)
    if mode == 'manual_replay':
        return ScoutResult('candidate' if replayed else 'empty', replayed, True, source.id,
                           'HAND_AUTHORED_REPLAY_NOT_A_MODEL_RESULT')
    if extracted:
        return ScoutResult('candidate', extracted, False, source.id)
    return ScoutResult('candidate' if replayed else 'needs_review', replayed,
                       True, source.id, 'MANUAL_BROWSER_REPLAY_ONLY')


def content_sha256(html: str) -> str:
    return sha256(html.encode('utf-8')).hexdigest()
