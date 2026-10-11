# KEP-CORE-002 | Budgeted, time-aware optional research proposals

**Research-only and 100% synthetic.** No web search, new Overture data, site crawl, paid API, external model, production, customer notification, human review material or live source request. Reuses CORE-001 temporal source snapshots, existing Core hard gates and Evidence Lab mathematical primitives. See ADR-0026.

## Why

CORE-001's strict two-independent-root source support policy avoids some false claims but abstains frequently. This experiment asks: **If one root already asserts a place exists, when is it worthwhile to propose exactly one independent verification, taking error assumptions, cost, budget and decision deadline into account?** The experiment measures decision tradeoffs under deliberately fictional source error rates. The chosen check never executes a request.

## Frozen deterministic decision sequence

1. Existing factual Core decides the user's candidate eligibility first. Unknown required price/opening-hours, wrong city, wrong rights or other hard vetoes cannot be overridden by source evidence.
2. CORE-001's source state considers only observations available by the decision clock. Echoes from the same root count once; stale/future/unapproved evidence is not independent.
3. Already supported by two positive roots: no check. Contradictory or negative reports: human review proposed, no automatic closure. Zero valid roots: no check (one more could not meet the two-root requirement). The current policy is intentionally restricted to **one existing positive root**.
4. For that one-root case, the original root must have an explicitly declared assumed error model. Unknown reliability fails closed. An option is considered only if its publisher root is new, it has permission for **hypothetical research**, its cost is within the remaining budget and its estimated response latency is at or below the fixed wait deadline.
5. Bayesian assumed current probability p comes from the existing Evidence Lab fuse_roots primitive. For a candidate check with sensitivity s and specificity t:
   - probability of a positive reply q = p*s + (1-p)*(1-t)
   - modeled probability after positive comes from bayes_update
   - the actual CORE-001 gate corroborates after a positive independent second root, **without** another posterior threshold. Its hypothetical gross payoff is p*s*reward - (1-p)*(1-t)*false_penalty.
   - net gain = gross payoff - proposed check cost. The frozen utility is reward=1 and false-assertion penalty=4. False positive outcomes are charged even when the modeled posterior would be low. If no net-positive independent affordable/timely check exists, VOI abstains.
6. The planner only returns PROPOSE_CHECK (or a reason for declining) with authorized_to_fetch=false, consumer_publish=false, model_used=false and accuracy fields null. The subsequent synthetic executor alone reveals the chosen pre-generated response. It charges the normalized cost and re-runs CORE-001 at the **same deadline for every competing policy**.

The assumed probabilities are not calibrated against real Turkish businesses; this is a policy design lab, not physical proof. Two apparently independent sources can agree on an incorrect assertion.

## Fixed paired synthetic experiment

Config: benchmarks/budgeted_core_protocol.json, seed 20261013, **six regimes, 400 cases each = 2,400 synthetic trials**, 300 paired bootstrap draws, max one check per case, reward=1, penalty false=4, five candidate strategies. No model is trained.

| Regime | Fault/constraint |
| --- | --- |
| matched | Declared channel quality matches generated answers |
| tight_budget | Only the inexpensive source can be checked |
| short_deadline | Only short-latency checks can return on time |
| quality_degradation | True source quality drops, while planner's assumptions remain optimistic |
| echo_storm | A publisher republishes 25 copies; no additional independence |
| rights_and_disputes | Hard source rights exclusions, contradictory same-root observations |

Every method sees the same initial source records, same allowed check options and same *pre-generated potential outcomes*. Hidden trial truth and possible probe answers reside in Trial, while **the planning function receives only View**, which has neither. Real outcomes cannot leak into the decision before a check is selected.

| Compared policy | Frozen behavior |
| --- | --- |
| never | Never check, use existing source state |
| cheapest | Cheapest allowed independent check |
| max_information | Largest modeled Shannon information gain |
| always_strong | Strongest assumed affordable and timely source |
| voi | Highest positive modeled decision gain after check cost, else no check |

Metrics: coverage, correct/false synthetic assertions, false fraction conditional on an assertion, missed true opportunities, number and cost of checks, human-review proposals, normalized realized utility and synthetic conditional paired-resampling bands. The VOI method is **not guaranteed to win** and the analysis must show failures under degraded sources, budget limits and latency.

## Offline reproduction

From labs/core, with only Python standard library:

    python -m unittest tests.test_budgeted_verify tests.test_budgeted_core_eval -v
    python -m benchmarks.budgeted_core_eval
    python -m unittest discover -s tests -v

GitHub Actions runs both Python 3.11 and 3.13, using no network, credentials, external dependencies or new source observations. The aggregated report is downloadable from CI and should be locked by an exact SHA-256 only after initial comparison.

## Boundaries and rollback

This is not a provider benchmark, model score, actual monetary saving, real-world opening/closure detection or probability of a real venue being open. The response deadline is a synthetic constraint and the cost is normalized utility, NOT TRY/USD or token pricing. Probe approval here means only allowlisted *simulated research*, not permission to fetch or publish.

Rollback: revert only CORE-002 new module, benchmark/config, tests, aggregate checks, documentation/ADR and offline CI. Leave CORE-001 and all historic real archive and privately frozen FIELD-001 materials unchanged.


## First frozen empirical SIMULATION result, October 11, 2026

The following are **synthetic** outcomes from exactly 400 pre-generated scenarios per regime. Python 3.11 and 3.13 JSON reports matched exactly after using deterministic Decimal arithmetic for check costs, realized utility and paired-resample rounding. The initial unpinned run exposed last-digit binary floating differences, which were fixed in code and regression-tested before freezing. Complete canonical-result SHA-256:

    9303794055e45a668abc4d194b64c1b86ce6fb9c9c48e70fdbcac3c5c578d6cc

Research replay:

    python scripts/replay_budgeted_core.py --check

| Simulated regime | Never: assertions / false | VOI: assertions / false | VOI checks | Never utility / case | VOI utility / case |
| --- | ---: | ---: | ---: | ---: | ---: |
| matched | 30 / 3 | 232 / 4 | 239 | .037500 | .461288 |
| tight_budget | 30 / 1 | 206 / 10 | 246 | .062500 | .377700 |
| short_deadline | 39 / 0 | 215 / 6 | 249 | .097500 | .450050 |
| quality_degradation | 22 / 1 | 130 / 21 | 195 | .042500 | **.006438** |
| echo_storm | 34 / 0 | 229 / 1 | 226 | .085000 | .495025 |
| rights_and_disputes | 21 / 1 | 145 / 2 | 147 | .040000 | .295238 |

The utility is an **invented decision score**, not economic return or real model quality. Positive source agreement means LAB support, not actual existence. This report does not verify any physical shop opening or closure.

### Negative and null findings retained

1. Under source-quality degradation, **VOI loses to NEVER** (.006438 vs .042500) and also loses to CHEAPEST (.052750). The simulated assumed source error rates stayed optimistic while actual generated accuracy declined; more data made incorrect assertions. There were 21 false claims among VOI's 130 synthetic assertions.
2. In these SIX predeclared regimes VOI happened to choose the **same allowed probes** as MAX_INFORMATION and ALWAYS_STRONG. Their assertions, costs and utility are identical in this design. Thus the experiment does **NOT** demonstrate an efficiency improvement unique to the VOI optimization over those two strategies.
3. When tight budget or short deadline permits only one sensor, all checking strategies are naturally identical, but check-vs-never remains a useful value comparison.
4. A separate synthetic low-prior test proves the VOI planner can refuse an expensive low-value check that CHEAPEST would still propose. It is a **contract test**, not a preregistered population-level lift estimate. We did not add a new regime after viewing results to manufacture a favorable benchmark.
5. Paired bootstrap intervals are conditional on these same fictional events and utility parameters. They do not authorize a real consumer/competitor or commercial inference.

The useful engineering milestone is **deterministic one-step budget/time/root-bound planning**, not evidence that a probabilistic router is calibrated or optimal. The next core-only experiment should stress prior misspecification, uncertain root independence, and smarter deferral, preregistered separately instead of changing this frozen result.
