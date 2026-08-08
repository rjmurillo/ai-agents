# Eval multi-provider transport (EVAL_PROVIDER Strategy)

The eval harness can run through OpenAI or GitHub Models when the
`ANTHROPIC_API_KEY` budget is exhausted. Provider selection is a Strategy behind
`EVAL_PROVIDER` (env) or `--provider` (flag). Anthropic stays the default on the
dependency-free urllib path, so no existing baseline moves.

**The GitHub Models half of that is gone.** GitHub retired the service on
2026-07-30, permanently and without grandfathering, after brownout rehearsals on
2026-07-16 and 2026-07-23. Probed on 2026-08-02,
`https://models.github.ai/inference` returns HTTP 410. The design below is still
an accurate description of the seam; only the reachability of the `github` and
`github-models` rows changed. PR #4422 resolved #4339 by removing the retirement
text from `_is_provider_outage`, so HTTP 410 now surfaces as an execution fault
with exit code 3. Issue #4002 also resolved the provider flag and quota-billed
cost gate defects.

## Design (Open/Closed)

- `scripts/eval/_providers.py` defines `EvalProvider` (a `Protocol`) with
  `complete(*, messages, system, model, max_tokens, temperature) -> str`.
- A new provider is a new class plus one row in `_REGISTRY`. No edit to
  `call_api`, the retry/categorization adapter, or any eval script.
- `call_api` (in `scripts/eval/_anthropic_api.py`) gains an optional `provider`
  param, falling back to `EVAL_PROVIDER`. `None` or `anthropic` keeps the urllib
  path byte-for-byte, so the zero-SDK default is preserved.

## Providers

- OpenAI and GitHub Models use the `openai` SDK. GitHub Models is
  OpenAI-compatible: same SDK, `base_url` = `GITHUB_MODELS_BASE_URL`
  (`https://models.github.ai/inference`), `GITHUB_TOKEN` as the bearer, model
  names prefixed `openai/...`. The Anthropic-style separate `system` arg is
  folded into a leading system-role message.
- `anthropic-sdk` is an optional provider via the `anthropic` SDK; the default
  `anthropic` provider stays on urllib.
- `copilot` and `copilot-cli` shell out to the installed Copilot CLI and need no
  API key.
- Providers normalize SDK errors to the exact message shapes
  `_anthropic_api.call_api` already emits (`<Provider> API returned HTTP
  <code>: ...`, `...timed out...`), so `_eval_api_adapter._categorize_error`
  classifies them unchanged.
- release-it: every SDK client sets `timeout=120.0` and `max_retries=0`. The
  adapter owns retries; an SDK retry layer would nest retries.

## Correctness constraint (do not violate)

A single eval invocation runs the baseline AND the variant through ONE provider.
Scores from different providers are NOT comparable; re-baseline per provider
(ADR-058 Experimental Design Symmetry). The help text and module docstring state
this. Do not compare a Sonnet-baseline score against an OpenAI-variant score.

## Credentials

The adapter transport factory is provider-aware and skips `load_api_key()`
(ANTHROPIC_API_KEY) for non-Anthropic providers, which self-load their own
credential (`OPENAI_API_KEY` or `GITHUB_TOKEN`).

## Dependencies

`anthropic` is already core. Only `openai>=1.40` is added, as an opt-in `eval`
extra (`pip install -e '.[eval]'`). The default eval needs no new dependency.

## Wiring

`--provider` is wired into `eval-agent-vs-baseline.py` and
`eval-prompt-change.py`. Select with `EVAL_PROVIDER=openai` or `--provider
copilot-cli` plus a matching model id. `EVAL_PROVIDER=github` and
`github-models` are wired the same way but are historical only: the rows
still exist in `_REGISTRY` and route correctly, but the endpoint they call
returns HTTP 410 (see the retirement note above). Do not select them.

## Evidence

- PR #2710 (merge 65d33d8b2980): multi-provider transport behind EVAL_PROVIDER.
- `scripts/eval/_providers.py` (`EvalProvider` Protocol, `_REGISTRY`,
  `GITHUB_MODELS_BASE_URL`), `scripts/eval/_anthropic_api.py` (`call_api`
  provider param).
- Tests: `tests/eval/test_providers.py` (26 offline tests, fake `openai` module
  injected; no network, no real SDK).
