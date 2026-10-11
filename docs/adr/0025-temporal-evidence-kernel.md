# ADR-0025: Synthetic first, time-aware KEP decision integration

Date 2026-10-11. Research-only decision. Related PR #36. Status: accepted only upon green offline CI.

## Context

Earlier real-source work established Istanbul Overture archives, changelog scope/metadata hazards and a privately frozen but still unlabeled blind field study. The user explicitly directed this workstream to STOP searching for better data: our eventual proprietary data will come later. We need the reusable KEP decision core and robust simulated failures now.

The existing Core already owns rights, location, opening hours, price, consent and user-hard-condition gates. Evidence Lab already demonstrates independence by publisher root and value of information; model_boundary already rejects unsupported proposals. A new model or source downloader would duplicate work without improving these contracts.

## Decision

1. Add a SMALL optional synthetic/research-only temporal pipeline that invokes existing Core eligibility first, then a deterministic as-of root-evidence snapshot, then the existing structured model context generator. Never modify the default Core behavior or override a hard gate.
2. Separate source observation time from *when the application can access the observation*. Future availability, future observation, expired TTL, source-rights failure and unknown publisher roots are not fresh evidence. A retry is idempotent, a conflicting reused event ID is rejected, and input list order cannot change an assessment.
3. Collapse syndicated observations by publisher root: most recent observed timestamp is authoritative within a root; tied opposite claims or between-root contradictions block. Require two positive independent roots for categorical lab corroboration. Negative evidence requires review, never inferred physical closure.
4. Output LAB_ONLY and consumer_publish=false always, with no numerical calibrated business-truth probability. Context supplied to a hypothetical model contains only Core-and-evidence allowed candidates; model API is not called.
5. Preregister a deterministic, paired and completely synthetic scenario generator with **one isolated hidden truth label per case**, which is outside the policy input type. Compare new method against Core-only, raw-message counting, one-root acceptance and always-abstain controls on the same 3,000 cases, five regimes and fixed assumptions. Include source degradation and latency stress, not just favorable cases.
6. Keep standard-library-only tests and CI on Python 3.11/3.13. Publish aggregate-only benchmark metrics; make clear that paired resampling intervals are conditional on the hand-authored simulator and do not establish Istanbul, KEP, Laya, MiMo or competitor accuracy.
7. NO data acquisition, live browser, registry indexing, HTTP, customer integration, Web Push, field label synthesis, business-event label or production deployment. Existing FIELD-001 remains a separate human process without fabricated reviews.

## Review gates

Tests require two independent roots, no echo double-counting, absence of future leakage, inclusive age cutoff, conflict/negative abstention, blocked rights, no price hallucination, snapshot order invariance, and rejection of unauthorized model candidates. Benchmark success is **reproducible measurement**, not a mandate that the new method wins every utility/coverage metric. Report disadvantages and shifts.

## Rollback

Remove only the optional temporal source pipeline, synthetic generator/benchmark and tests, pinned simulation config/results and offline replay CI addition plus this ADR and study note. Preserve all old Core decisions, real archived Places/GERS evidence and private field materials. No schema migration or consumer rollback.

Details: labs/core/docs/TEMPORAL_SYNTHETIC_KERNEL.md.
