# Eval multiprovider transport

The eval harness can route baseline and variant calls through one provider selected by `EVAL_PROVIDER` or `--provider`. Default `anthropic` stays on `_anthropic_api.call_api` with urllib and `ANTHROPIC_API_KEY`; routed providers live in `scripts/eval/_providers.py`.

Provider names: `openai`, `codex`, `github`, `github-models`, and `anthropic-sdk`. OpenAI and GitHub Models share the OpenAI-compatible provider. GitHub Models uses `https://models.github.ai/inference` and token lookup order `GITHUB_MODELS_TOKEN`, `GITHUB_TOKEN`, `GH_TOKEN`.

Credential loading mirrors `_anthropic_api.load_api_key`: check env vars first, then repo-root `.env`; reject symlinked module paths before resolving `__file__` so credential lookup cannot be redirected outside the repo.

Error contract: providers raise `RuntimeError` with the HTTP or timeout message shapes that `_eval_api_adapter._categorize_error` already understands. Non-text OpenAI-compatible response content fails loudly instead of returning an empty string.

Reasoning models in the OpenAI-compatible provider, `o*` and `gpt-5*`, use `max_completion_tokens` and omit custom `temperature`; non-reasoning models keep `max_tokens` and explicit temperature.

Evidence: PR #2710 branch `feat/eval-multiprovider-transport`, files `scripts/eval/_providers.py`, `scripts/eval/_eval_api_adapter.py`, `tests/eval/test_providers.py`, session log `.agents/sessions/2026-06-20-session-2597-eval-multiprovider-transport-openai-github.json`.
