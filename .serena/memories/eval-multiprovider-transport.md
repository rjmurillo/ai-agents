# Eval Multi-Provider Transport (#2710)

## Contract

The eval harness can run against non-Anthropic providers when the `ANTHROPIC_API_KEY` budget is exhausted. Select via the `EVAL_PROVIDER` env var or a `--provider` flag. Anthropic stays the default on the existing dependency-free urllib path, so no existing baseline moves.

- Strategy seam: `scripts/eval/_providers.py` defines `EvalProvider.complete(*, messages, system, model, max_tokens, temperature) -> str`. A new provider is a new class + one registry row; no edit to `call_api`, the retry/categorization adapter, or any eval script (Open/Closed).
- **openai / github-models**: use the `openai` SDK. GitHub Models is OpenAI-compatible: same SDK, `base_url=https://models.github.ai/inference`, `GITHUB_TOKEN` as bearer, model names prefixed `openai/...`. The Anthropic-style separate `system` arg is folded into a leading system-role message. **GitHub Models is retired and this route is dead. Do not reach for it.** See the retirement note below.
- **anthropic-sdk**: optional provider via the `anthropic` SDK. The default `anthropic` provider stays on the urllib path (no SDK dependency).
- Providers normalize SDK errors to the exact message shapes `_anthropic_api.call_api` already emits (`<Provider> API returned HTTP <code>: ...`, `...timed out...`) so the existing `_eval_api_adapter` categorization keeps working.

## GitHub Models is retired (measured 2026-08-02)

GitHub retired GitHub Models on 2026-07-30: closed to new customers 2026-06-16, brownout rehearsals on 2026-07-16 and 2026-07-23, full shutdown 2026-07-30 with no grandfathering. Both the `github` and `github-models` provider rows resolve to `https://models.github.ai/inference`, so both are dead.

Probed directly on 2026-08-02:

```
POST https://models.github.ai/inference/chat/completions
HTTP 410
{"error":{"code":"github_models_retirement_brownout",
          "message":"GitHub Models is temporarily unavailable as part of a scheduled retirement brownout."}}
```

The body still says "temporarily." That is no longer true, and the stale wording has a consequence: `_is_provider_outage` in `scripts/eval/eval-prompt-change.py` matches on that text, so an eval routed through this provider now exits neutral rather than red. A gate wired this way reports success while grading nothing. Tracked in #4339.

So this memory's escape hatch below is only half available. `openai`, `codex`, and `anthropic-sdk` remain; `github` and `github-models` do not. #4002 additionally reports that `--provider` is a dead flag and that a plan-time USD gate blocks non-Anthropic models, so confirm reachability before depending on any of them.

## Apply when

Adding an eval provider, or when an eval defers with "ANTHROPIC_API_KEY budget exhausted" (the recurring blocker this fixed, e.g. on PR #2707). Do NOT `import anthropic` in a custom eval script expecting it to work by default; the SDK is only present for the optional providers.

Source: issue/PR #2710 (MERGED); `scripts/eval/_providers.py`.
