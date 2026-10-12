# ADR-0030: Observe source disagreement before any outage fallback module

Date 2026-10-12. Status: research GO, product rollout NOT approved.

## Context

CORE-004A's preregistered 48-hour audit-grace fallback failed NO-GO, showing no incremental decisions on 1,080 fictional cases. QA-001 requires each new code feature or test to have measurable incremental decision value. Separately, a review pipeline's completion age cannot establish whether source observations themselves are reliable.

## Choice and evidence

Before implementing the feature, freeze an observable-only telemetry test with a new seed (KEP-OBS-001): completed-independent-review timestamps versus those timestamps plus unlabelled inter-publisher disagreement over 12 hours, at least 18 distinct previous background entities and a fixed 0.35 threshold. Current test truth, future sensor outputs, and future audit labels are inaccessible to the policy.

The first 960-case paired synthetic run passed 8/8 predeclared GO-for-research requirements, correctly preserving conservative action under authored degradation and fixed checking during a stable audit outage. But it did NOT discover hidden correlation: three false assertions remained under shared rumor and no alarms were triggered. The main stable outage signal policy is identical to audit-age-only, so any claimed unique information gain belongs to degradation scenarios only. The abrupt improvement relative to conservative is small and its conditional bootstrap includes zero.

## Decision

Accept the importance of the *observable source disagreement hypothesis* for one further independently designed synthetic experiment; do not merge a new runtime decision selector, its experimental tests or recurring workload. Retain only protocol and aggregate evidence on main. The original study evaluator is pinned in research commit e25ce70c14a644a73fcd299e51e8e8b28a658578 for limited historical replay. No new real-world data are fetched or accepted, and no calibrated reliability or physical venue proof is asserted.

The second experiment must vary raw claim delivery failures and upstream root correlation while charging observation overhead. If a different generator invalidates the observed advantage, record NO-GO without overfitting. Even a second success would remain a synthetic research outcome and would not lift Core rights, publication, model or consent limits.

## Rollback

Delete OBS-001 research protocol/report/doc/ADR. CORE-001/002/003 decision modules, FIELD-001 private files, all pinned source archives and the normal full CI remain unchanged.
