# ADR-0003 · Haiku 5.5 read-only Browser Scout pilot

**State:** Proposed, research only  
**Date:** 2026-10-11  
**Issue:** KEP-EVAL-002  
**Depends on:** ADR-0002 rights-gated source registry

## Decision

The Scout is an **optional** escalation for rights-approved, JS-heavy sources. Use JSON-LD / RSS / API extraction first, and call the browser agent only when static methods miss required fields. Any browser output is a **candidate** for source/field validation, not proof and not customer-ready data.

To avoid rebuilding browser automation plumbing, the optional paid experiment uses the `browser_use.integrations.toolsets_for_claude.BrowserUse` driver and Anthropic's `client.beta.messages.tool_runner`, targeting `claude-haiku-5-5` with `browser_toolset_20260801`. No SDK dependency or API key is required for offline CI.

## Explicit limits

- Read-only actions: `navigate`, `read_page`, `get_page_text`, `find`, `wait`.
- All click, type, tab creation, file access, JavaScript, network introspection, and Bash actions are disabled.
- Navigate only to the reviewed source's exact registered URL. All other actions require a same-origin tab URL.
- A real browser has **not been hardened** by these callback checks. Redirects and subresource network requests bypass SDK navigation policy; **isolate the browser and enforce network-level egress** before any live run.
- Only registry `approved` + `research_ingest` + `website_review_required` sources qualify. No website source is currently approved in registry: live pilot fails closed.
- `--live` and `--network-sandbox-confirmed` are explicit. One model run at most six iterations, with a post-response token guard. This is not a prepaid spending limit; the response already incurred usage. Set external API billing limits.
- The model can return only research candidates. Its `source_quote` is **not** verified against DOM by this paid adapter. Human review or independent source validation is required for Core publication.
- No authenticated sessions or private user accounts. No automatic publishing, commenting, subscriptions, checkouts, or messages.

## Comparison protocol

`benchmarks/scout_eval.py` compares three variants on identical hand-authored HTML fixtures:

1. **Script:** JSON-LD extraction without browser/model.
2. **Manual browser replay:** Manually authored candidate proposals with literal HTML-text evidence checks, **not actual Haiku output**.
3. **Hybrid:** Script first, only use replay when script returns no candidate.

This is a **contract test**, not a model benchmark. Real model-versus-script performance needs allowed real pages, independently labeled event occurrences, repeated trials, and measured token costs. The next phase must compare precision/recall, stale data, date/venue errors, attempted forbidden actions, latency, and verified-candidate cost.

## Why not replace Radar?

Source URLs, fetch cadence, rights, structured extraction, and cache/dedup are already deterministic. A browser Scout adds value only for authorized hard layouts; making it the default raises costs and audit burden without demonstrated quality benefit.

## Rollback

Remove the optional runner and this benchmark. No schema migration, service, key or external deployment is introduced.

## Official references

- https://platform.claude.com/docs/en/agents-and-tools/tool-use/browser-use-sdk
- https://platform.claude.com/docs/en/agents-and-tools/tool-use/browser-use-tool
- https://www.anthropic.com/claude-haiku-5-5
- https://docs.browser-use.com/open-source/customize/integrations/toolsets-for-claude
