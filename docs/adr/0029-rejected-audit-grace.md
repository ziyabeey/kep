# ADR-0029: Reject outage grace without demonstrated incremental decision value

Date: 2026-10-12. Status: **rejected candidate / accepted NO-GO evidence**.

## Decision

Do not add the proposed 48-hour historical-audit grace policy from experimental PR #41 to the KEP Core. The policy was committed and evaluated on six new preregistered fully synthetic conditions (1,080 cases total), on both Python 3.11 and 3.13, but it failed the main frozen value gate. An increase of at least +0.025 utility/case over existing conservative CORE-003 on the stable outage condition was required; the observed increase was precisely **0.000**.

The original existing conservative policy and the proposed fallback each missed **53** true synthetic cases in the new 180-case outage stress, proposed the same 70 source checks, and scored **0.344167** normalized utility/case. Fixed CORE-002 VOI proposed 111 checks, missed 17, and scored 0.517972 in that condition. Nothing here proves the fixed strategy is universally superior: degraded sources can make overconfident checking dangerous, and the other two preregistered adverse regimes remain relevant.

## Why rejection is the success criterion

QA-001 changed KEP development from test-count accumulation to evidence of real incremental protection. This experiment operationalizes that decision: it does NOT convert 13 passing new unit tests into product value, and it does NOT retune timeouts or confidence thresholds against its exposed holdout. Only the preregistration and negative measurement, not the unused policy code or test workbench, may enter main.

No source discovery, new real data download, human truth, Laya/MiMo call, external probe or consumer permission occurred. All existing Core behavior, real research archives and private audit files remain unchanged. Additional designs must declare **new holdouts and explicit adverse-case metrics BEFORE implementation**.

## Evidence

- Original preregistration: `labs/core/benchmarks/outage_value_protocol.json`, created at commit `8edf6cc2469b5d7fff3ad142c341affca4b06c4c`.
- First untouched holdout: [GitHub Actions run 38180120019](https://github.com/ziyabeey/kep/actions/runs/38180120019), Python 3.11/3.13 SUCCESS, identical complete result canonical SHA-256 `f00c4d2da46f35ad63f1da671171db3b69dfb67abf85ad1318d8207e1b337a46`.
- Anonymous results: `labs/core/reports/KEP_CORE_004A_NO_GO.json`.
- Full explanation: `labs/core/docs/CORE_004A_NO_GO.md`.

## Rollback

Remove only documentation, preregistration and results from this rejected experiment. No runtime code changes were admitted.
