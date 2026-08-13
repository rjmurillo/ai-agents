# Eval multiprovider transport

The eval harness can route baseline and variant calls through one provider selected by `EVAL_PROVIDER` or `--provider`. Default `anthropic` stays on `_anthropic_api.call_api` with urllib and `ANTHROPIC_API_KEY`; routed providers live in `scripts/eval/_providers.py`.

## Extension seam

`EvalProvider.complete(*, messages, system, model, max_tokens, temperature) -> str` is the provider contract. Add a provider class and one registry row. Do not edit `call_api`, the retry adapter, or individual eval scripts. OpenAI-compatible providers fold the separate `system` argument into a leading system-role message.

## Apply when

Use this memory when adding an eval provider or when the default Anthropic budget is exhausted. Do not assume the optional `anthropic` SDK is installed for custom eval scripts.

Provider names: `openai`, `codex`, `github`, `github-models`, `anthropic-sdk`, `copilot`, and `copilot-cli`. OpenAI and GitHub Models share the OpenAI-compatible provider. GitHub Models uses `https://models.github.ai/inference` and token lookup order `GITHUB_MODELS_TOKEN`, `GITHUB_TOKEN`, `GH_TOKEN`. The Copilot rows shell out to the installed Copilot CLI.

**`github` and `github-models` are dead as of 2026-07-30.** GitHub retired GitHub Models that day, permanently and without grandfathering. Both rows resolve to `https://models.github.ai/inference`, which returned HTTP 410 when probed on 2026-08-02. PR #4422 resolved #4339 by removing the retirement markers from `_is_provider_outage`, so the 410 now exits 3 as an execution fault instead of a neutral skip. Issue #4002 resolved the provider flag and quota-billed cost gate defects. Working routed rows are `openai`, `codex`, `anthropic-sdk`, `copilot`, and `copilot-cli`.

Credential loading mirrors `_anthropic_api.load_api_key`: check env vars first, then repo-root `.env`; reject symlinked module paths before resolving `__file__` so credential lookup cannot be redirected outside the repo.

Error contract: providers raise `RuntimeError` with the HTTP or timeout message shapes that `_eval_api_adapter._categorize_error` already understands. Non-text OpenAI-compatible response content fails loudly instead of returning an empty string.

Reasoning models in the OpenAI-compatible provider, `o*` and `gpt-5*`, use `max_completion_tokens` and omit custom `temperature`; non-reasoning models keep `max_tokens` and explicit temperature.

Evidence: PR #2710 branch `feat/eval-multiprovider-transport`, files `scripts/eval/_providers.py`, `scripts/eval/_eval_api_adapter.py`, `tests/eval/test_providers.py`, session log `.agents/sessions/2026-06-20-session-2597-eval-multiprovider-transport-openai-github.json`.
