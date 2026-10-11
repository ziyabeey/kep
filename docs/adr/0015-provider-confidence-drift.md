# ADR-0015: Provider confidence drift must not dominate field verification

**Status:** Accepted as offline research policy, pending CI and external field validation  
**Date:** 2026-10-11

## Context

KEP now has 4,650 real source records from Overture 2026-08-19.0 and 4,803 from 2026-09-23.1 for the same two limited Istanbul sample cells. A substantial majority of shared IDs change in supplier confidence while retaining all other minimized fields. A naïve Scout that fetches every changed-confidence record can exhaust its verification budget chasing calibration/model churn rather than user-relevant factual uncertainty.

## Decision

1. Compute mutually exclusive source-record-change categories. Separate schema-sensitive changes and confidence-only changes; never equate confidence with business truth.
2. Pre-register deterministic **targeted** human/Scout review lanes with an explicit fixed budget; do not claim it is an unbiased error-rate sample.
3. Keep the SCI-003 independent random audit completely separate and do not use targeted outcomes in its prevalence estimator.
4. Refuse any input that introduces personal contacts, live availability, verified business flags, unapproved geographic cells, nonfinite values, or duplicate IDs.
5. Store only anonymous **aggregate counts** in the public repository. Detailed review candidates remain in `.local` and are not consumer-facing.
6. Retain historical data source timestamps and hashes, note backwards acquisition order and provider-level provenance uncertainty. Missing listing/added listing are never closure/opening observations.

## Tests, failure cases and rollback

- Python `unittest` checks count identities, missing confidence, taxonomy-only drift, provenance order insensitivity, deterministic queues, strict privacy and bogus verified-status injection.
- Manual/offline replay requires pinned original August ZIP and verified September archive; CI never accesses the network.
- Revert KEP-DATA-011 files and CI smoke if needed; original Overture data, access rights and SCI-003 sampling are untouched.

## Unproven

No human correctness labels, model superiority, monetary savings or optimal active sampling strategy were measured in this release. Fixed triage quotas are an **engineering hypothesis** until true human-reviewed verification outcomes and controlled cost experiments become available.
