# KEP-DATA-002 · Istanbul Overture POI existence audit

**Research-only. No real Overture Istanbul POI has been acquired or human-validated by this change.**

## 1. What is being measured?

Only whether an Overture-listed **point POI is a real, publicly observable place**. Do not interpret a successful existence vote as confirmation of the brand name, precise position, venue hours, current operating status, live prices, event availability or walking distance. Overture itself distinguishes existence confidence from `operating_status`, and its confidence is not reliably calibrated across data providers.

Source documentation: https://docs.overturemaps.org/guides/places/  
Current pinned release: `2026-09-23.1` (October 11, 2026).  
See: https://docs.overturemaps.org/release-calendar/ and https://docs.overturemaps.org/attribution/ .

## 2. Start with the existing manual-only GitHub Actions job

Use **Actions → Overture Istanbul Places Research (manual) → Run workflow**; enter `RESEARCH_ONLY` and `2026-09-23.1`. This job uses Overture's free public CLI, bounded Beşiktaş and Karaköy **sampling boxes**, not neighborhood polygons. It checks the STAC pin before and after downloading, uses an exact Python client version, then validates the minimized output. A failure **must not** upload a partial artifact.

**This job has not been dispatched by this PR.** There is no unattended crawling and the regular CI has no external I/O.

## 3. Validate the downloaded artifact offline

After downloading the GitHub Actions artifact and extracting it to a **new, private** folder:

```bash
cd labs/core
python scripts/verify_overture_pilot.py --directory .local/overture-manual-artifact --require-live
```

This detects inconsistent data/manifest content. A manifest's claimed raw source hashes are *not* independent S3 authentication because the private raw download bytes are not inside the downloadable artifact. Preserve the run link and private raw data when appropriate; do not forge a truth label from a SHA-256 alone.

For the **deterministic synthetic test only**, run:

```bash
python -m benchmarks.overture_audit_eval
python -m unittest tests.test_overture_audit -v
```

## 4. Freeze an existence-audit sample before looking up outcomes

Create a 16+ character secret sampling seed **outside the repository** (the following command uses a local ignored path). Never pass the seed as a CLI argument or paste it into a public issue:

```bash
mkdir -p .local
python -c 'import secrets,pathlib; pathlib.Path(".local/overture.audit-seed").write_text(secrets.token_urlsafe(32))'
python scripts/verify_overture_pilot.py \
  --directory .local/overture-manual-artifact --require-live \
  --audit-seed-file .local/overture.audit-seed \
  --audit-budget 60 \
  --audit-plan-output .local/poi-existence-audit-plan.json
```

The program **does not overwrite** an existing plan. Each selected GERS-like identifier carries a `cell`, a preregistered `confidence_band` and an inclusion probability. The plan stores a hash commitment to the seed, never the seed itself. Securely retain both the plan and the seed. A sample budget below the number of nonempty strata is rejected instead of omitting groups silently. If fewer than 60 POIs are available, choose a feasible smaller budget deliberately.

## 5. Human assessment is indispensable

Have two separate humans check each sampled POI and independently record whether the **physical place exists** (`exists`, `does_not_exist`, `unknown`) with HTTPS citation and timestamp. This is NOT the same as checking if a restaurant is open or whether a name has been spelled correctly. For uncertain cases or disagreements, keep `unknown` and do not publish a population-wide statistic. Real reviewer independence must be operationally verified; pseudonymous IDs alone prove nothing.

The research-only function `estimate_existence_error` takes a frozen dataset and plan, the original private seed, two time-stamped votes per selected POI, and an `evaluation_asof` timestamp. It reproduces the original sample draw, rejects tampering and extra targeted reviews, and only yields a weighted frame error diagnostic if **every selected item** has two agreeing, timely, correctly linked votes.

The interval reflects sampling uncertainty under strong assumptions; no threshold may automatically publish events or mark a POI as verified. Future releases, missing inventory and nonresponders are not covered.

## 6. Evidence levels to keep distinct

1. **Source metadata seen:** Overture STAC says `2026-09-23.1` is current as of October 11, 2026.
2. **Manual acquisition reported:** a successful GitHub run's metadata says two cells were downloaded; the artifact manifest reports local checksums.
3. **Local integrity checked:** a verifier confirms a frozen minimized artifact is internally self-consistent.
4. **Existence assessed:** real independent reviewers assess actual physical existence for a random audit sample, not all POIs.
5. **Consumer-ready location:** requires separate operational checks and rights/accuracy acceptance. Steps 1–4 do **not** confer this automatically.
