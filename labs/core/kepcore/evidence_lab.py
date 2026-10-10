"""Research-only evidence router: one-step expected value of information.

Important: probabilities here are GIVEN, not learned or validated for KEP sources.
The router must NEVER be used as a production verification/publishing gate.
It cannot override rights, date, price, event-state, or user-consent checks.

Mathematical model: binary proposition; independent *publisher roots*; declared
source sensitivity/specificity; fixed decision utility; one potential check.
These assumptions can be wrong. See benchmarks/evidence_value.py for stress tests.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from math import isfinite, log, exp, log2
from typing import Iterable


def _prob(x: float) -> float:
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not isfinite(x) or not 0 < x < 1:
        raise ValueError('Probability must be a finite number strictly between 0 and 1')
    return float(x)


@dataclass(frozen=True)
class EvidenceChannel:
    id: str
    publisher_root: str
    sensitivity: float  # P(says true | actually true)
    specificity: float  # P(says false | actually false)
    cost: float         # normalized research *utility* cost, NOT USD/API tokens
    approved: bool = False  # explicit research access only; never a display license
    origin_primary: bool = False  # reviewed source of record for this root, NOT syndication

    def __post_init__(self) -> None:
        if not self.id or not self.publisher_root:
            raise ValueError('Evidence channels need stable ID and publisher root')
        _prob(self.sensitivity)
        _prob(self.specificity)
        if isinstance(self.cost, bool) or not isinstance(self.cost, (int, float)) or not isfinite(self.cost) or self.cost < 0:
            raise ValueError('Invalid acquisition cost')


@dataclass(frozen=True)
class Observation:
    channel_id: str
    publisher_root: str
    supports: bool

    def __post_init__(self) -> None:
        if not self.channel_id or not self.publisher_root or not isinstance(self.supports, bool):
            raise ValueError('Invalid evidence observation')


@dataclass(frozen=True)
class Belief:
    probability: float | None
    independent_roots: tuple[str, ...]
    status: str  # modeled / disputed
    caveat: str = 'HYPOTHETICAL_UNCALIBRATED_NOT_PRODUCTION_PROOF'


@dataclass(frozen=True)
class ProbeValue:
    channel_id: str
    publisher_root: str
    expected_sample_information: float  # bits, diagnostic only
    expected_decision_gain: float       # expected utility gain, BEFORE probe cost
    cost: float
    net_gain: float


@dataclass(frozen=True)
class ResearchRoute:
    action: str  # VERIFY / LAB_ACCEPT / LAB_DEFER / HUMAN_REVIEW
    belief: Belief
    selected_probe: str | None
    expected_net_gain: float
    evaluated: tuple[ProbeValue, ...]
    explanation: str
    laboratory_only: bool = True
    # Never publish or notify users based on this outcome.


def _logit(p: float) -> float:
    return log(p / (1 - p))


def _logistic(x: float) -> float:
    if x >= 0:
        z = exp(-x)
        return 1 / (1 + z)
    z = exp(x)
    return z / (1 + z)


def bayes_update(p: float, channel: EvidenceChannel, supports: bool) -> float:
    """Bayes rule under assumed, possibly miscalibrated channel error rates."""
    _prob(p)
    if not isinstance(supports, bool):
        raise ValueError('Binary observation required')
    if supports:
        lr = channel.sensitivity / (1 - channel.specificity)
    else:
        lr = (1 - channel.sensitivity) / channel.specificity
    return max(1e-12, min(1 - 1e-12, _logistic(_logit(p) + log(lr))))


def fuse_roots(prior: float, observations: Iterable[Observation],
               channels: Iterable[EvidenceChannel]) -> Belief:
    """Only one piece of evidence per root; contradictions get human review."""
    p = _prob(prior)
    channels = tuple(channels)
    by_id = {c.id: c for c in channels}
    if len(by_id) != len(channels):
        raise ValueError('Duplicate channel identifiers')
    # Stable snapshot of claims: the order and duplication of copied posts
    # must not alter a posterior.
    by_root: dict[str, list[Observation]] = {}
    for obs in observations:
        channel = by_id.get(obs.channel_id)
        if channel is None or channel.publisher_root != obs.publisher_root:
            raise ValueError('Unregistered or mismatched source provenance')
        if not channel.approved:
            raise PermissionError('Evidence origin not approved for research use')
        by_root.setdefault(obs.publisher_root, []).append(obs)
    for root, hits in by_root.items():
        if len({hit.supports for hit in hits}) > 1:
            return Belief(None, tuple(sorted(by_root)), 'disputed')
    for root in sorted(by_root):
        # A root is counted once. A copied post MUST NOT displace the original
        # simply because it claims a higher reliability. Choose the reviewed
        # primary sensor when present, or conservatively the weakest sensor.
        hits=by_root[root]
        primary=[h for h in hits if by_id[h.channel_id].origin_primary]
        pool=primary if primary else hits
        hit = sorted(pool, key=lambda h:(_channel_strength(by_id[h.channel_id]), h.channel_id))[0]
        p = bayes_update(p, by_id[hit.channel_id], hit.supports)
    return Belief(p, tuple(sorted(by_root)), 'modeled')


def _channel_strength(c: EvidenceChannel) -> float:
    return c.sensitivity + c.specificity - 1.0


def _entropy(p: float) -> float:
    return 0 if p <= 0 or p >= 1 else -p * log2(p) - (1-p) * log2(1-p)


def expected_information_gain(p: float, channel: EvidenceChannel) -> float:
    """Expected Shannon entropy reduction, bits; not the decision objective."""
    yes = p * channel.sensitivity + (1-p) * (1-channel.specificity)
    p_yes = bayes_update(p, channel, True)
    p_no = bayes_update(p, channel, False)
    return max(0.0, _entropy(p) - yes * _entropy(p_yes) - (1-yes) * _entropy(p_no))


def action_utility(p: float, *, reward_true: float = 1.0,
                   penalty_false: float = 4.0, min_probability: float = .8) -> tuple[str, float]:
    """Myopic accept/abstain decision. All numbers are experimental utility units."""
    _prob(p)
    if (not isfinite(reward_true) or not isfinite(penalty_false) or reward_true <= 0 or penalty_false <= 0):
        raise ValueError('Invalid utility')
    _prob(min_probability)
    gain = p * reward_true - (1-p) * penalty_false
    if p >= min_probability and gain > 0:
        return 'LAB_ACCEPT', gain
    return 'LAB_DEFER', 0.0


def expected_value_of_sample(p: float, channel: EvidenceChannel, **utility) -> ProbeValue:
    """Expected value of a ONE-STEP observation before looking at its answer."""
    yes = p*channel.sensitivity+(1-p)*(1-channel.specificity)
    posterior_yes = bayes_update(p, channel, True)
    posterior_no = bayes_update(p, channel, False)
    before = action_utility(p, **utility)[1]
    after = yes * action_utility(posterior_yes, **utility)[1] + (1-yes)*action_utility(posterior_no, **utility)[1]
    delta = max(0., after-before)
    return ProbeValue(channel.id, channel.publisher_root, expected_information_gain(p,channel),
                      delta, channel.cost, delta-channel.cost)


def route_research(prior: float, observations: Iterable[Observation],
                   channels: Iterable[EvidenceChannel], *, budget: float = .15,
                   utility: dict | None = None, mode: str = 'voi') -> ResearchRoute:
    """Choose optional independent evidence or finish LAB-only decision.

    Policies for benchmark: voi, max_information, cheapest, never. Only
    'voi' declines a check with nonpositive net value; other policies are
    controls, not recommended production settings.
    """
    if mode not in {'voi','max_information','cheapest','never'}:
        raise ValueError('Unknown research policy')
    if isinstance(budget, bool) or not isinstance(budget, (float, int)) or not isfinite(budget) or budget < 0:
        raise ValueError('Invalid research budget')
    channels = tuple(channels)
    if len({c.id for c in channels}) != len(channels):
        raise ValueError('Duplicate channel identifiers')
    assumptions = utility or {}
    belief = fuse_roots(prior, observations, channels)
    if belief.status == 'disputed':
        return ResearchRoute('HUMAN_REVIEW',belief,None,0.,(),'Conflicting claims from the same origin.')
    used = set(belief.independent_roots)
    choices = [expected_value_of_sample(belief.probability,c,**assumptions)
               for c in channels if c.approved and c.publisher_root not in used and c.cost <= budget]
    ordered = sorted(choices,key=lambda x:(-x.net_gain,x.channel_id))
    if choices and mode != 'never':
        if mode == 'voi':
            best = ordered[0]
            if best.net_gain > 1e-12:
                return ResearchRoute('VERIFY',belief,best.channel_id,best.net_gain,tuple(ordered),
                                     'Expected decision gain exceeds check cost under lab assumptions.')
        elif mode == 'max_information':
            best = sorted(choices,key=lambda x:(-x.expected_sample_information,x.channel_id))[0]
            return ResearchRoute('VERIFY',belief,best.channel_id,best.net_gain,tuple(ordered),
                                 'Benchmark: maximize Shannon information gain, ignoring cost.')
        elif mode == 'cheapest':
            best = sorted(choices,key=lambda x:(x.cost,x.channel_id))[0]
            return ResearchRoute('VERIFY',belief,best.channel_id,best.net_gain,tuple(ordered),
                                 'Benchmark: always check cheapest available channel.')
    action,_=action_utility(belief.probability,**assumptions)
    return ResearchRoute(action,belief,None,0.,tuple(ordered),
                         'No affordable positive-net information request; lab answer or defer.')


@dataclass(frozen=True)
class FieldResearchTask:
    record_id: str
    field: str
    reason: str
    priority: int
    status: str = 'PROPOSE_ONLY_REQUIRES_AUTHORIZED_SOURCE'


# Deterministic linkage to the factual KEP Core. These are MISSING FACTS,
# never guesses that missing information is probably true.
FIELD_GAPS = {
    'DISPUTED_EVIDENCE': ('conflicting_claim', 100),
    'SOURCE_FRESHNESS_UNVERIFIED': ('source_status', 95),
    'SESSION_TIMES_UNKNOWN': ('session_times', 90),
    'VENUE_UNRESOLVED': ('venue', 90),
    'PRICE_FRESHNESS_UNVERIFIED': ('price', 85),
    'PRICE_UNKNOWN': ('price', 85),
    'PRICE_INVALID': ('price', 85),
    'OPENING_HOURS_UNKNOWN': ('opening_hours', 85),
    'DAILY_OPENING_HOURS_UNKNOWN': ('opening_hours', 85),
    'COORDINATES_UNKNOWN': ('coordinates', 80),
    'DURATION_UNKNOWN': ('end_time', 75),
    'CROWD_FRESHNESS_UNVERIFIED': ('crowd', 50),
    'CROWD_UNKNOWN': ('crowd', 50),
    'CURRENCY_CONVERSION_REQUIRED': ('currency_conversion', 45),
}


def field_research_tasks(decision, max_tasks: int = 12) -> list[FieldResearchTask]:
    """Read-only triage for Core REFRESH/CLARIFY. Never launch a fetch.

    An approved source with real error-rate calibration is still necessary
    before a task can be evaluated by Bayesian value of information.
    """
    if not isinstance(max_tasks, int) or isinstance(max_tasks,bool) or max_tasks<1:
        raise ValueError('Positive task limit required')
    if decision.action not in {'REFRESH','CLARIFY'}:
        return []
    tasks=[]
    for record_id,reasons in decision.blocked.items():
        for reason in reasons:
            if reason in FIELD_GAPS:
                field, priority = FIELD_GAPS[reason]
                tasks.append(FieldResearchTask(record_id,field,reason,priority))
    # Multiple reasons on one field require only one research task.
    by_key={}
    for task in sorted(tasks,key=lambda t:(-t.priority,t.record_id,t.field,t.reason)):
        by_key.setdefault((task.record_id,task.field),task)
    return list(by_key.values())[:max_tasks]
