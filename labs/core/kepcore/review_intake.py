"""KEP-SCI-002B: auditable, offline human field-claim review intake.

Input assertions are not verified by this program: operator must confirm the
source right, immutable capture and reviewer independence. This module
never fetches URLs or grants permission to publish or notify users.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlsplit
from collections import Counter, defaultdict
import json
import re

from .calibration import FIELDS, OUTCOMES, ReviewedClaim, aware, validated

CRITICAL_FIELDS = frozenset({'starts_at', 'venue', 'cancelled'})
REASONS = frozenset({
    'primary_confirmation', 'independent_confirmation', 'primary_contradiction',
    'unresolved', 'historical_change',
})


def _identifier(value: str, name: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r'[a-zA-Z0-9][\w.:-]{0,127}', value, re.ASCII):
        raise ValueError(f'{name}: invalid opaque identifier')


def _https(url: str, name: str) -> None:
    if not isinstance(url, str) or url.strip() != url or len(url) > 2048:
        raise ValueError(f'{name}: invalid URL')
    parts = urlsplit(url)
    try:
        port = parts.port
    except ValueError as exc:
        raise ValueError(f'{name}: invalid port') from exc
    if (parts.scheme != 'https' or not parts.hostname or '.' not in parts.hostname
            or parts.username or parts.password or port not in (None, 443)
            or any(ord(c) < 32 or c.isspace() for c in url)):
        raise ValueError(f'{name}: HTTPS evidence URL required')


@dataclass(frozen=True)
class ReviewCandidate:
    claim_id: str
    entity_id: str
    field: str
    claimed_value: str
    publisher_root: str
    source_id: str
    source_url: str
    city: str
    claimed_at: str | None
    observed_at: str
    predicted_at: str
    snapshot_sha256: str
    rights_scope: str

    def __post_init__(self):
        for name in ('claim_id', 'entity_id', 'publisher_root', 'source_id'):
            _identifier(getattr(self, name), name)
        if self.field not in FIELDS:
            raise ValueError('Unknown field')
        if not isinstance(self.claimed_value, str) or not (1 <= len(self.claimed_value) <= 500):
            raise ValueError('Claimed value is required, up to 500 characters')
        if not isinstance(self.city, str) or not self.city.strip() or len(self.city) > 100:
            raise ValueError('City is required')
        _https(self.source_url, 'source_url')
        if self.rights_scope != 'research_ingest':
            raise PermissionError('Approved research-use scope required')
        if not isinstance(self.snapshot_sha256, str) or not re.fullmatch(r'[0-9a-f]{64}', self.snapshot_sha256):
            raise ValueError('Snapshot SHA-256 is required')
        if aware(self.observed_at) > aware(self.predicted_at):
            raise ValueError('Source observation cannot be after the decision')
        if self.claimed_at is not None and aware(self.claimed_at) > aware(self.observed_at):
            raise ValueError('Source publication cannot be after observation')


@dataclass(frozen=True)
class ReviewBallot:
    claim_id: str
    snapshot_sha256: str
    reviewer_id: str
    outcome: str
    reviewed_at: str
    evidence_ref: str
    reason_code: str

    def __post_init__(self):
        _identifier(self.claim_id, 'claim_id')
        _identifier(self.reviewer_id, 'reviewer_id')
        if self.reviewer_id.casefold() in {'ai','model','simulator','unknown'}:
            raise ValueError('Human reviewer required')
        if not re.fullmatch(r'[0-9a-f]{64}', self.snapshot_sha256):
            raise ValueError('Snapshot SHA-256 required')
        if self.outcome not in OUTCOMES or self.reason_code not in REASONS:
            raise ValueError('Invalid review outcome or reason')
        valid_pairs = {
            'correct': {'primary_confirmation', 'independent_confirmation'},
            'incorrect': {'primary_contradiction'},
            'unknown': {'unresolved'},
            'superseded': {'historical_change'},
        }
        if self.reason_code not in valid_pairs[self.outcome]:
            raise ValueError('Review reason contradicts outcome')
        _https(self.evidence_ref, 'evidence_ref')
        aware(self.reviewed_at)
        if ((self.outcome == 'unknown') != (self.reason_code == 'unresolved')):
            raise ValueError('Unknown outcomes require unresolved reason and vice versa')
        if ((self.outcome == 'superseded') != (self.reason_code == 'historical_change')):
            raise ValueError('Superseded outcomes require historical_change reason and vice versa')


@dataclass(frozen=True)
class ReviewAdjudication:
    claim_id: str
    snapshot_sha256: str
    adjudicator_id: str
    outcome: str
    reviewed_at: str
    evidence_ref: str
    reason_code: str

    def __post_init__(self):
        ReviewBallot(self.claim_id, self.snapshot_sha256, self.adjudicator_id,
                     self.outcome, self.reviewed_at, self.evidence_ref, self.reason_code)


def _load_jsonl(path: str | Path, cls) -> list:
    records = []
    expected = set(cls.__dataclass_fields__)
    for index, line in enumerate(Path(path).read_text(encoding='utf-8').splitlines(), 1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
            if not isinstance(obj, dict) or set(obj) != expected:
                raise ValueError('Strict schema mismatch')
            records.append(cls(**obj))
        except (ValueError, TypeError, json.JSONDecodeError, PermissionError) as exc:
            raise ValueError(f'Invalid {cls.__name__} line {index}: {exc}') from exc
    return records


def load_intake(candidates: str | Path, ballots: str | Path,
                adjudications: str | Path | None = None) -> tuple[list, list, list]:
    return (_load_jsonl(candidates, ReviewCandidate),
            _load_jsonl(ballots, ReviewBallot),
            _load_jsonl(adjudications, ReviewAdjudication) if adjudications else [])


def resolve_reviews(candidates: list[ReviewCandidate], ballots: list[ReviewBallot],
                    adjudications: list[ReviewAdjudication], *, asof: str) -> dict:
    """Convert human ballots into ReviewedClaim only when review quorum is met.

    `asof` freezes available decisions. Future ballots/adjudications cannot
    leak into older calibration windows, and disagreement never uses a majority
    vote as a substitute for explicit third-party adjudication.
    """
    cutoff = aware(asof)
    candidate_by_id = {}
    seen_root_observation = set()
    for candidate in candidates:
        if not isinstance(candidate, ReviewCandidate):
            raise TypeError('ReviewCandidate expected')
        if candidate.claim_id in candidate_by_id:
            raise ValueError('Duplicate candidate claim_id')
        root_key = (candidate.entity_id, candidate.field, candidate.publisher_root, aware(candidate.predicted_at))
        if root_key in seen_root_observation:
            raise ValueError('Duplicate publisher-root claim observation')
        seen_root_observation.add(root_key)
        candidate_by_id[candidate.claim_id] = candidate
    ballot_by_claim: dict[str, list[ReviewBallot]] = defaultdict(list)
    ballot_keys = set()
    future_ballots = 0
    for ballot in ballots:
        if not isinstance(ballot, ReviewBallot):
            raise TypeError('ReviewBallot expected')
        if ballot.claim_id not in candidate_by_id:
            raise ValueError('Ballot references missing candidate')
        candidate = candidate_by_id[ballot.claim_id]
        if ballot.snapshot_sha256 != candidate.snapshot_sha256:
            raise ValueError('Ballot snapshot differs from candidate')
        if aware(ballot.reviewed_at) < aware(candidate.predicted_at):
            raise ValueError('Ballot predates claim decision')
        key = (ballot.claim_id, ballot.reviewer_id.casefold())
        if key in ballot_keys:
            raise ValueError('Same reviewer cannot vote twice on a claim')
        ballot_keys.add(key)
        if aware(ballot.reviewed_at) >= cutoff:
            future_ballots += 1
            continue
        ballot_by_claim[ballot.claim_id].append(ballot)
    adjudication_by_claim = {}
    future_adjudications = 0
    for adj in adjudications:
        if not isinstance(adj, ReviewAdjudication):
            raise TypeError('ReviewAdjudication expected')
        if adj.claim_id not in candidate_by_id:
            raise ValueError('Adjudication references missing candidate')
        candidate = candidate_by_id[adj.claim_id]
        if adj.snapshot_sha256 != candidate.snapshot_sha256:
            raise ValueError('Adjudication snapshot mismatch')
        if aware(adj.reviewed_at) < aware(candidate.predicted_at):
            raise ValueError('Adjudication predates claim decision')
        if adj.claim_id in adjudication_by_claim:
            raise ValueError('Only one final adjudication per claim is supported')
        if aware(adj.reviewed_at) >= cutoff:
            future_adjudications += 1
            continue
        adjudication_by_claim[adj.claim_id] = adj

    results: list[ReviewedClaim] = []
    audit = []
    statuses = Counter()
    for candidate in sorted(candidates, key=lambda c: c.claim_id):
        votes = sorted(ballot_by_claim[candidate.claim_id], key=lambda b: b.reviewer_id)
        adj = adjudication_by_claim.get(candidate.claim_id)
        minimum = 2 if candidate.field in CRITICAL_FIELDS else 1
        status = 'ready'
        chosen = None
        reviewer_identity = None
        evidence = None
        checked_at = None
        if aware(candidate.predicted_at) >= cutoff:
            status = 'not_yet_eligible'
        elif len(votes) < minimum:
            status = 'needs_second_review' if len(votes) == 1 and minimum == 2 else 'needs_review'
        elif len({v.outcome for v in votes}) > 1:
            if adj is None:
                status = 'needs_adjudication'
            elif adj.adjudicator_id.casefold() in {v.reviewer_id.casefold() for v in votes}:
                raise ValueError('Adjudicator cannot review own ballot')
            elif aware(adj.reviewed_at) < max(aware(v.reviewed_at) for v in votes):
                raise ValueError('Adjudication cannot predate reviewed ballots')
            else:
                chosen = adj.outcome
                reviewer_identity = f'adjudicated:{adj.adjudicator_id}'
                evidence = adj.evidence_ref
                checked_at = adj.reviewed_at
        else:
            if adj is not None:
                raise ValueError('Adjudication should only settle contradictory ballots')
            chosen = votes[0].outcome
            reviewer_identity = 'dual:' + '+'.join(v.reviewer_id for v in votes) if len(votes)>1 else votes[0].reviewer_id
            evidence = votes[0].evidence_ref
            checked_at = max(votes, key=lambda v: aware(v.reviewed_at)).reviewed_at
        statuses[status] += 1
        audit.append({
            'claim_id': candidate.claim_id, 'status': status,
            'field': candidate.field, 'required_reviews': minimum,
            'available_reviews': len(votes),
            'reviewer_ids': [v.reviewer_id for v in votes],
            'claimed_value_sha256': sha256(candidate.claimed_value.encode('utf-8')).hexdigest(),
            'adjudicated': status == 'ready' and adj is not None,
        })
        if status != 'ready':
            continue
        results.append(ReviewedClaim(
            claim_id=candidate.claim_id, entity_id=candidate.entity_id, field=candidate.field,
            publisher_root=candidate.publisher_root, source_id=candidate.source_id,
            city=candidate.city, claimed_at=candidate.claimed_at,
            observed_at=candidate.observed_at, predicted_at=candidate.predicted_at,
            checked_at=checked_at, snapshot_sha256=candidate.snapshot_sha256,
            rights_scope=candidate.rights_scope, outcome=chosen,
            reviewer_id=reviewer_identity, evidence_ref=evidence, origin='human_review',
        ))
    validated(results)
    return {
        'study': 'KEP-SCI-002B', 'asof': asof, 'research_only': True,
        'allow_auto_publish': False, 'requires_operator_rights_confirmation': True,
        'ready': len(results), 'candidate_count': len(candidates),
        'status_counts': dict(sorted(statuses.items())),
        'late_ballots_not_used': future_ballots,
        'late_adjudications_not_used': future_adjudications,
        'audit': audit,
        'reviews': [asdict(r) for r in results],
    }


def verify_research_snapshots(candidates: list[ReviewCandidate], snapshot_dir: str | Path,
                              *, registry: dict | None = None) -> dict:
    """Fail-closed export gate for source rights and pinned local snapshot bytes.

    Verifies integrity and approved research use, NOT whether a human judged
    factual accuracy correctly. Never fetches remote source/evidence URLs.
    """
    from .radar import load_sources

    sources = load_sources() if registry is None else registry
    base = Path(snapshot_dir).expanduser().resolve()
    if not base.is_dir():
        raise ValueError('Snapshot directory does not exist')
    checked = 0
    for candidate in candidates:
        source = sources.get(candidate.source_id)
        if source is None or not source.allows('research_ingest'):
            raise PermissionError(f'Unapproved research source: {candidate.source_id}')
        if candidate.city != source.city:
            raise ValueError('Candidate city differs from registered source')
        if urlsplit(candidate.source_url).hostname != urlsplit(source.url).hostname:
            raise ValueError('Candidate URL origin differs from registered source')
        snapshot = base / f'{candidate.snapshot_sha256}.snapshot'
        if snapshot.is_symlink() or not snapshot.is_file() or not snapshot.resolve().is_relative_to(base):
            raise ValueError('Missing or unsafe source snapshot')
        if snapshot.stat().st_size > source.max_response_bytes:
            raise ValueError('Source snapshot exceeds registered size limit')
        digest = sha256()
        with snapshot.open('rb') as handle:
            for chunk in iter(lambda: handle.read(65536), b''):
                digest.update(chunk)
        if digest.hexdigest() != candidate.snapshot_sha256:
            raise ValueError('Snapshot content hash mismatch')
        checked += 1
    return {'snapshots_checked': checked, 'rights_checked': checked,
            'verified_claim_truth': False, 'consumer_display_approved': False}
