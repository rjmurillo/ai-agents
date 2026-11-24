# SPEC: Harness-Agnostic Model Fallback for Comment Actionability

Status: Draft. Owner: Richard Murillo. Written 2026-11-23 at `84c395f822`.

Owner ruling (2026-11-23): the Haiku fallback cannot work as the general pattern.
Spec the open-ended version. This document is a spec only. It changes no code.

## Step 0 First Principles

### Q1 Demand Reality

`scripts/update_reviewer_signal_stats.py` scores PR review comments as actionable or not.
The reviewer signal table in `.serena/memories/pr-review/pr-comment-responder-skills.md` comes from it.
The `pr-comment-responder` skill reads that table to rank reviewers.
A wrong score there misranks reviewers for every agent that triages PR comments.

### Q2 Status Quo

The heuristic scores each comment. Scores from 0.4 to 0.6 go to
`scripts/llm_classification/classifier.py`. That module calls the Anthropic SDK with a
hard-coded Haiku model and `ANTHROPIC_API_KEY`.

The only runtime is the daily cron in `.github/workflows/update-reviewer-stats.yml`.
That workflow passes no `ANTHROPIC_API_KEY` (lines 77 to 79, read 2026-11-23).
`LLMFallbackConfig.from_env()` then sets `enabled=False` (`config.py:53-61`).
So the fallback has never run in production. The heuristic alone decides every comment.

### Q3 Desperate Specificity

The person hurt is the agent or maintainer who trusts the reviewer signal table.
On 2026-11-13 (`637b60d749`) it showed `devin-ai-integration` at 348 of 349 actionable
and `coderabbitai` at 265 of 270. Those rates are likely inflated (INFERRED, see Q5).

### Q4 Narrowest Wedge

First, measure. Build a labeled corpus and score the heuristic against it.
Only then decide whether any model fallback earns its place.
If it does, add one transport-neutral call contract with one CI transport.

### Q5 Observation

`get_actionability_score` starts every score at 0.5 (`update_reviewer_signal_stats.py:274`).
A comment that matches no regex stays at 0.5. That is inside the fallback band.
`is_actionable` is `score >= 0.5`, so a comment with no evidence counts as actionable.
This likely explains the 98 to 100 percent signal rates (INFERRED, not measured).
The share of comments that land in the band is unknown. Eval step 1 measures it.

The model prompt sends only the comment body (`classifier.py:96-101`).
The heuristic also reads thread replies. So the model sees less than the heuristic it overrides.

### Q6 Future-fit

At ten times the comments, a per-comment paid call with an in-process cache does not scale.
The cache dies with the process, so every daily run pays again.
The design must cache across runs and cap calls per run.

## Prior Art / Constraints

| Source | What it says | Effect on this spec |
|---|---|---|
| ADR-111 (accepted) | Default to the harness-inherited model. No versioned id in skills. | The model comes from the host or config. No hard-coded model id. |
| `.claude/rules/plugin-self-containment.md` MUST 4 | A shipped script stays stdlib-only at import time. | Library code imports no vendor SDK. |
| `pyproject.toml` import-linter contract `shipped-lib-no-runtime-dependencies` | Shipped lib packages may not import `anthropic`. | Same as above, enforced by a linter. |
| ADR-006 | Workflow logic lives in testable modules. | Transport choice lives in Python, not YAML. |
| ADR-021 (accepted 2025-12-23) | Names `claude-haiku-4.5` as a JSON-extraction fallback for CI review. | Governs CI review routing, not this utility. It predates ADR-111. Not binding here. |
| `scripts/eval/_providers.py:104` `EvalProvider` | One `complete(messages, system, model, max_tokens, ...) -> str` protocol. Seven provider cells across Claude, Codex, Copilot, API and subscription billing. | The repo already owns a transport seam. Reuse it, do not write a second one. |
| `scripts/eval/_claude_cli.py:85-94` | Strips `ANTHROPIC_API_KEY` and related vars from the child env. | Subscription transports must not silently bill a metered key. |
| claude-mem (`github.com/thedotmack/claude-mem`, Apache-2.0) | Observer model runs in a background worker. `CLAUDE_MEM_PROVIDER` picks the vendor, `CLAUDE_MEM_MODEL` picks the model, 180 s timeout. | Pattern borrowed: provider and model are config, never code. No code copied. Apache-2.0 places no duty on a borrowed pattern. |

## Problem statement

The fallback is bound to one vendor SDK, one model id, and one API key.
Where any of the three is missing, it returns `None` without a word.
It cannot run inside Codex, Copilot CLI, Cursor, Muse, or Hermes.
And its one consumer never turns it on, so nobody knows if it helps.

## Recon summary (2026-11-23, `84c395f822`)

### Consumers of `scripts/llm_classification`

| Consumer | File and lines | Runtime |
|---|---|---|
| `update_reviewer_signal_stats.py` | Import at 53. Classifier built at 750 to 765. Called from `get_actionability_score` at 331. | GitHub Actions cron, `update-reviewer-stats.yml:82` and `:91`, daily 06:00 UTC |
| Tests | `tests/llm_classification/` (4 files) | pytest |

No hook, skill, or lefthook job imports it. Search: `git grep -n -E "llm_classification|LLMClassifier|get_default_classifier|LLM_FALLBACK"`.

### Other direct model calls

| Code | Mechanism | Runtime |
|---|---|---|
| `scripts/ci/invoke_claude_review.py` | Anthropic SDK | CI, through `.github/actions/ai-review/action.yml` |
| `packages/semantic-hooks/src/semantic_hooks/embedder.py` | OpenAI embeddings SDK | Opt-in local Claude Code hook package |
| `scripts/eval/_http_providers.py`, `_claude_cli.py`, `_codex_cli.py`, `_copilot_cli.py` | SDK, HTTP, and CLI subprocess | Local eval runs |
| `llm-council`, `benchmark-models` skills | `claude -p`, `codex exec`, `copilot -p` | Local, from skill prose |

### Model access per harness

Evidence is repo code and tests only. A vendor-doc check failed on 2026-11-23 (search API returned HTTP 401).

| Harness | One-shot mechanism | Tools off? | Model choice | Evidence |
|---|---|---|---|---|
| Claude Code | `claude --print --output-format json --model M --setting-sources "" --strict-mcp-config --disallowed-tools ... --no-session-persistence` | Yes | `--model` | `scripts/eval/_claude_cli.py:159-177` |
| Codex | `codex exec --model M --sandbox read-only --ephemeral --ignore-user-config --output-last-message F` | Read-only sandbox | `--model` | `scripts/eval/_codex_cli.py:165-177` |
| Copilot CLI | `copilot --acp --model M --available-tools= --no-custom-instructions --disable-builtin-mcps` over JSON-RPC | Yes | `--model` | `scripts/eval/_copilot_cli.py:395-415` |
| Cursor | `cursor-agent --trust --force -p` | No evidence. `--force` allows shell. | None found | `tests/e2e/test_cursor_plugin_smoke.py:190-205` |
| Muse | `muse exec --json --trust-workspace --disable-web-tools` | Web tools only | None found | `tests/e2e/test_muse_agents_load.py:89` |
| Hermes | None found | n/a | n/a | Searched `hermes (chat\|-z\|-q\|run)` and `tests/e2e/hermes_runtime.py` |

Not found in the repo: a host-agent handback convention, MCP sampling, prompt-type hooks,
and any CLIProxyAPI reference. `OPENAI_BASE_URL` is an operator-set endpoint (`_providers.py:150`).

## User stories

1. As the reviewer-stats cron, I classify an ambiguous comment with whatever model the operator configured, so the stats do not depend on one vendor.
2. As a maintainer running the script on a laptop under any harness, I get the same verdict shape from my own login, with no API key.
3. As the owner, I see in the run summary how many comments used the fallback and how many fell back to the heuristic, so a silent no-op cannot hide.

## Call contract

### Input

| Field | Type | Notes |
|---|---|---|
| `comment_body` | `str` | Untrusted text. Truncate to 4,000 characters. |
| `thread_replies` | `list[str]` | New. Up to 3 replies, each truncated to 500 characters. Closes the gap in Q5. |
| `heuristic_score` | `float` | Logged only. Not sent to the model, so it cannot anchor the answer. |

### Output

Keep the current verdict shape, parsed from model text as JSON:

```json
{"is_actionable": true, "confidence": 0.82, "reason": "Reports a null dereference"}
```

- `is_actionable`: bool. Required. A missing or non-bool value is a parse failure, not `False`.
- `confidence`: float, clamped to 0 to 1. Missing means parse failure.
- `reason`: string, truncated to 100 characters.

Today `classifier.py:108-109` defaults a missing `is_actionable` to `False` and `confidence` to 0.5.
That turns a malformed reply into a verdict. The new contract rejects it instead.

The caller keeps its current rule: apply the verdict only when `confidence >= 0.7`
(`update_reviewer_signal_stats.py:339`).

### Budgets

| Bound | Value | Why |
|---|---|---|
| Output tokens | 100 | Current value. The JSON fits in about 40. |
| Input tokens | about 1,500 | 4,000-character body plus replies plus a 250-token system prompt |
| Per-call timeout | 60 s | A CLI cold start dominates. Eval transports default to 900 s, too long for a cron. |
| Retries | 1 on a transient error only | Current code retries twice. Auth, missing binary, and parse failures do not retry. |
| Calls per run | `LLM_FALLBACK_MAX_CALLS`, default 200 | Hard cap. Past it, the heuristic stands and the summary says so. |
| Wall time per run | 15 min | Matches the `timeout-minutes: 15` already on the sibling step. |

### Caching

- Key: SHA-256 of the normalized comment plus replies (keep `cache.py` normalization), plus prompt version, plus provider and model.
- A prompt or model change invalidates the cache by key, with no manual purge.
- Store: a JSON file under the runner cache in CI (`actions/cache`, keyed on prompt version) and under `.project-toolkit/cache/` locally. The in-memory LRU stays as the first tier.
- A cached verdict never expires on time. A comment body does not change its meaning.

## Transport options, ranked

Rank depends on the runtime. The only consumer today runs in CI, which has no host agent.

### In CI (the only runtime today)

| Rank | Transport | Failure mode |
|---|---|---|
| 1 | Operator-configured OpenAI-compatible HTTP endpoint (`OPENAI_BASE_URL` plus key from a secret). Stdlib `urllib`. Covers CLIProxyAPI, Azure OpenAI, and any gateway. | Secret missing: transport reports `unconfigured`. Endpoint down: `unavailable`. |
| 2 | `anthropic` cell of `EvalProvider` (stdlib urllib path, not the SDK) | Same as above with `ANTHROPIC_API_KEY`. |
| 3 | A vendor CLI on the runner | Not viable. CI has no subscription login. Listed to rule it out. |

### Inside a harness (local runs)

| Rank | Transport | Failure mode |
|---|---|---|
| 1 | The CLI of the harness the user is in, through the matching `EvalProvider` cell: `claude-cli`, `codex-cli`, or `copilot-cli` | Binary missing or not logged in: `unavailable`. Must run with tools off and metered env stripped, as the eval cells already do. |
| 2 | The HTTP endpoint from CI rank 1, if configured | As above. |
| Excluded | Cursor, Muse | No evidence of a tool-less one-shot mode. The comment text is untrusted, so a mode with shell access is a prompt-injection path. Re-admit when a probe proves tools are off. |
| Excluded | Hermes | No one-shot mechanism found. |
| Rejected | Hand the prompt back to the host agent | No repo convention, and the only consumer has no agent in the loop. |

### Selection

`LLM_FALLBACK_PROVIDER` names a cell (`openai`, `anthropic`, `claude-cli`, `codex-cli`, `copilot-cli`, `none`).
With no value, auto-detect in this order: configured HTTP endpoint, then the CLI of the
detected harness (`CLAUDECODE`, `CODEX_*`, `COPILOT_*` env markers), then `none`.

### When no model is reachable

Keep today's outcome: the heuristic result stands. Change how it is reported.

- Each run counts `fallback_used`, `fallback_cached`, `fallback_unavailable`, and `fallback_capped`.
- The counts go to the step summary that `_write_step_summary` already writes.
- If `LLM_FALLBACK_PROVIDER` is set and the transport is unreachable, exit 3 (external error, ADR-035).
  An operator who asked for a model and got none should see red.
- If nothing is configured, exit 0 and print `fallback: unconfigured, N comments in band`.

Why keep the heuristic as the floor: the stats job is a report, not a gate.
Failing the whole report because a tiebreaker is down loses all the data to protect a small slice.

## Harness agnosticism

- `scripts/llm_classification` imports no vendor SDK. It depends on a `Transport` protocol:
  `complete(system: str, user: str, model: str | None, max_tokens: int, timeout: float) -> str`.
- The model id comes from `LLM_FALLBACK_MODEL` or the transport default. Code holds no model id.
  `None` means "the CLI's own default", which inherits the harness model per ADR-111.
- Transports reuse the `EvalProvider` cells. Their argv, env stripping, and billing guards already exist and are tested.
- The `anthropic` package leaves this module's import graph. A test asserts the module imports with `anthropic` blocked.

## Config surface

| Variable | Today | Proposed |
|---|---|---|
| `LLM_FALLBACK_ENABLED` | Defaults to "API key present" | Keep. Default becomes "a transport resolved". |
| `LLM_FALLBACK_MIN`, `LLM_FALLBACK_MAX` | 0.4, 0.6 | Keep. |
| `LLM_FALLBACK_MODEL` | Defaults to `claude-haiku-4-5-20251001` | Keep the name. Default becomes unset (transport default). |
| `LLM_FALLBACK_CACHE_SIZE` | 100 | Keep for the in-memory tier. |
| `LLM_FALLBACK_PROVIDER` | n/a | New. Names the transport cell. |
| `LLM_FALLBACK_MAX_CALLS` | n/a | New. Default 200. |
| `LLM_FALLBACK_TIMEOUT` | n/a | New. Default 60 s. |
| `ANTHROPIC_API_KEY` | Sole enable signal | Read only by the `anthropic` cell. |

Migration: one consumer, one workflow. Today nothing sets any of these in CI.
So the migration is additive. An old local setup with only `ANTHROPIC_API_KEY` set
auto-detects the `anthropic` cell and keeps working. An old `LLM_FALLBACK_MODEL` value still passes through.

## Cost and latency per call

Rates from `scripts/eval/_eval_common.py` (read 2026-11-23). About 1,500 input and 60 output tokens per call.

| Model class | Input rate per 1K | Output rate per 1K | Cost per call |
|---|---|---|---|
| Haiku 4.5 | $0.001 | $0.005 | about $0.0018 |
| Haiku 5.5 | $0.0001 | $0.0005 | about $0.0002 |
| Sonnet 5 | $0.002 | $0.010 | about $0.0036 |

At the 200-call cap, one run costs at most about $0.72 on Sonnet 5 and $0.36 on Haiku 4.5.
The cross-run cache drops repeat runs to near zero, since most comments in a 90-day window repeat daily.
A subscription CLI cell has no per-call charge but counts against the login's quota.

Latency: no single-classification latency is measured in this repo.
HTTP calls to a small model are expected under 3 s. CLI calls add process start, expected 5 to 20 s (INFERRED).
Eval step 2 measures both. Bound: 60 s per call, 15 min per run.

## Eval method (before anyone builds)

1. **Measure the band.** Run the heuristic over the 90-day comment set. Record the count and share at 0.4 to 0.6, and the share at exactly 0.5 with no matched pattern. No model needed.
2. **Build a labeled corpus.** Sample 200 comments, stratified: 100 from the band, 100 outside it, across every reviewer in the signal table.
   Label each actionable or not by hand, from the comment and the diff it points at.
   Labels must not come from thread replies. The heuristic already reads replies, so reply-derived labels make it grade itself.
   Store as JSONL under `evals/comment-actionability/` with the label rubric.
3. **Score three arms** on the band items, then on all items:
   - A: heuristic as shipped (`>= 0.5` is actionable).
   - B: heuristic with the tie broken the other way (`> 0.5`). A deterministic baseline with no model.
   - C: heuristic plus model fallback, per transport and model tried.
4. **Report** accuracy, precision, and recall for each arm, with a paired bootstrap 95 percent CI on the C minus best-of(A, B) accuracy difference over band items.
5. **Reuse first.** `scripts/eval/eval-prompt-change.py` already runs scenario files with an `expected_verdict`. Check whether it scores this corpus with no new code before writing a runner.

Pass bar: C beats the better of A and B on band items by at least 10 points of accuracy, CI lower bound above 0.

## Kill criteria

Drop the model fallback, and delete `scripts/llm_classification`, if any holds:

1. Fewer than 5 percent of comments land in the band (eval step 1). The fallback would move nothing.
2. Arm C fails the pass bar against arm B. A one-character tie-break rule would then do the job.
3. The signal table's reviewer ranking does not change between A and C. Nobody downstream would act differently.
4. No transport is reachable in CI without a new paid secret, and the owner declines to add one.
5. Measured p95 per-call latency over 60 s on the chosen CI transport.

## Acceptance criteria

1. `scripts/llm_classification` imports with `anthropic` blocked from `sys.modules`. A test proves it.
2. No string matching `claude-|gpt-|gemini-` appears as a default in `scripts/llm_classification`. A test greps the module.
3. A malformed model reply (missing `is_actionable`) yields `None` and increments `fallback_unavailable`, never a verdict.
4. With `LLM_FALLBACK_PROVIDER` set and the transport down, `main` returns 3. With nothing configured, `main` returns 0 and the summary prints the band count.
5. A second run over the same comments makes 0 model calls (cross-run cache hit).
6. Calls per run never exceed `LLM_FALLBACK_MAX_CALLS`. Comments past the cap keep the heuristic verdict and count as `fallback_capped`.
7. Each CLI transport runs with tools disabled and metered-billing env vars stripped, inherited from the `EvalProvider` cell.
8. The eval report from the method above is committed before AC 1 to 7 are built.

## Security

- Comment text is untrusted. It goes in the user message only, never the system prompt.
- No transport may run with tools, shell, or file write enabled. This is why Cursor and Muse are excluded today.
- The reply is parsed as JSON into three typed fields. Nothing in it is executed or used as a path.
- Secrets stay in env vars and CI secrets. The cache file stores verdicts and hashes, never keys or raw comment text.

## Out of scope

- Fixing the heuristic's 0.5 tie-break (Q5). The eval arm B measures it. The fix is its own change and the owner's call.
- The other direct model calls in the recon table. They have their own runtimes and owners.
- Adding Cursor, Muse, or Hermes transports. Each needs a probe that proves a tool-less mode first.

## Open questions

1. **Where does the transport seam live?** `EvalProvider` loads its siblings with bare imports (`from _claude_cli import`, `_providers.py:20-28`). So `scripts.llm_classification` cannot import it without putting `scripts/eval` on `sys.path`. Options:
   - A. Promote `_providers.py` and its cells to a package such as `scripts/model_transport/`, and repoint `scripts/eval`. One seam for both. Wider change, touches eval tests.
   - B. Have `llm_classification` add `scripts/eval` to `sys.path` and import `resolve_provider`. Smallest diff, couples a CI utility to private eval modules.
   - C. Write a thin stdlib HTTP transport inside `llm_classification` and skip CLI cells. Smallest scope, gives up local-harness support.
   Recommendation: A, if the eval passes. It is an architecture change, so it needs an ADR and the owner's decision.
2. Is a CI secret for an OpenAI-compatible endpoint acceptable for this job? Kill criterion 4 depends on it.
3. Should the summary table publish the fallback counts per reviewer, or only per run?

## Requirement-to-section map

| Required answer | Section |
|---|---|
| Call contract | Call contract |
| Transport options and no-model behavior | Transport options, ranked; When no model is reachable |
| Harness agnosticism | Harness agnosticism |
| Config surface and migration | Config surface |
| Cost and latency | Cost and latency per call |
| Eval method | Eval method |
| Kill criteria | Kill criteria |
