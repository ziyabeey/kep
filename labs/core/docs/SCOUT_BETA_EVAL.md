# KEP Scout Lab · Offline benchmark and optional Haiku 5.5 research pilot

## What's actually tested?

`python -m benchmarks.scout_eval` uses six **hand-authored artificial pages**. It demonstrates that scripts can parse JSON-LD, manual browser observations can preserve literal excerpts, and the hybrid runs the fallback only when needed. It does **not** measure Haiku quality. The `manual_replay` records were written by a developer, not produced by a model. Every candidate retains `review_required=true`.

```bash
cd labs/core
python -m unittest discover -s tests -v
python -m benchmarks.scout_eval
python scripts/haiku_browser_scout.py --source zorlu_psm_events
```

The last command uses no network and returns `OFFLINE_BY_DEFAULT`. In current registry, any `--live` for Istanbul returns `SOURCE_RIGHTS_NOT_APPROVED` before importing Anthropic.

## What does live pilot require?

1. Verify and record permission for the exact page and the **research_ingest** purpose in `sources/registry.json`. Obtain explicit consent where applicable.
2. Use an isolated throwaway container/VM. Establish DNS/redirect/subresource egress restrictions outside SDK; SDK `url_policy` and `confirm` are insufficient by themselves. Never point to an authenticated or privileged browser.
3. Install compatible Anthropic and Browser Use Python SDKs separately, *not in CI*:

```bash
python -m pip install 'browser-use>=0.13.11' 'anthropic>=1,<2'
python -c 'from anthropic.tools.browser import LocalFilePolicy; from browser_use.integrations.toolsets_for_claude import BrowserUse; print("SDK ready")'
```

Install Chromium using Browser Use's documented setup for the chosen OS. Provide `ANTHROPIC_API_KEY` via a local secrets manager, never GitHub source or logs.

4. After all controls, intentionally run:

```bash
python scripts/haiku_browser_scout.py --source YOUR_APPROVED_ID --live --network-sandbox-confirmed
```

Never call `--live` from GitHub Actions. Set provider spending limits outside the runner. API token guard stops only **after** a response, not before it has been billed. Re-evaluate the beta SDK interface before every paid test.

## How shall we evaluate later?

Use the same approved URL snapshots and an independent gold table. Compare: valid new event occurrences, field-level precision/recall, missing/incorrect dates, cancelled items, deduplication, browser actions, model calls, measured input/output/cache tokens, wall-clock and cost per verified occurrence. Hold out sources for source-transfer tests. Publish no rankings for real models until actual calls have been made.

The user-facing KEP is native/mobile-only; Scout stays server-side, never inside the mobile app.
