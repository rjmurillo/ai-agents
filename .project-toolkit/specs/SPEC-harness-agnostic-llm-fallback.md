# SPEC: Harness-Agnostic Model Fallback for Comment Actionability

Status: Draft. Owner: Richard Murillo. Written 2026-11-23 at `84c395f822`.

Owner ruling (2026-11-23): the Haiku fallback cannot work as the general pattern.
Spec the open-ended version. This document is a spec only. It changes no code.

## Step 0 First Principles

### Q1 Demand Reality

`scripts/update_reviewer_signal_stats.py` scores PR review comments as actionable or not.
It writes the reviewer signal table in `.serena/memories/pr-review/pr-comment-responder-skills.md`.
The `pr-comment-responder` skill reads that table to rank reviewers.
A wrong score there misranks reviewers for every agent that triages PR comments.

### Q2 Status Quo

The heuristic scores each comment. Scores from 0.4 to 0.6 go to
`scripts/llm_classification/classifier.py`. That module calls the Anthropic SDK with a
hard-coded Haiku model id and `ANTHROPIC_API_KEY`.

The only runtime was the daily cron in `.github/workflows/update-reviewer-stats.yml`. The owner deleted that workflow on 2026-11-25, so nothing runs the classifier on a schedule now.
That workflow passed no `ANTHROPIC_API_KEY` (lines 77 to 79, read 2026-11-23).
No commit ever added it there (`git log -S ANTHROPIC_API_KEY` on that file, empty on 2026-11-23).
`LLMFallbackConfig.from_env()` then sets `enabled=False` (`config.py:53-61`).
So the fallback never ran in that workflow, as its history shows.

The job ran under `environment: agent-claude` from `d73c0cf0fe` (2026-11-05) until the workflow was deleted on 2026-11-25.
That environment holds `ANTHROPIC_API_KEY` and `CLAUDE_CODE_OAUTH_TOKEN` (secret names listed by `gh api`, 2026-11-24).
The secrets are optional: a fork, a `gh act` run, or another repository has none. The step never mapped them in.
The heuristic alone decides every comment.

### Q3 Desperate Specificity

The person hurt is the agent or maintainer who trusts the reviewer signal table.
On 2026-11-13 (`637b60d749`) it showed `devin-ai-integration` at 348 of 349 actionable
and `coderabbitai` at 265 of 270. Those rates look inflated (INFERRED, see Q5).

### Q4 Narrowest Wedge

First, measure. Build a labeled corpus and score the heuristic against it.
Only then decide whether any model fallback earns its place.
If it does, add one transport-neutral call contract with one CI transport.

### Q5 Observation

`get_actionability_score` starts every score at 0.5 (`update_reviewer_signal_stats.py:274`).
A comment that matches no regex stays at 0.5. That is inside the fallback band.
`is_actionable` is `score >= 0.5`, so a comment with no evidence counts as actionable.
This may explain the 98 to 100 percent signal rates (INFERRED, not measured).
The share of comments in the band is unknown. Eval step 1 measures it.

The model prompt sends only the comment body (`classifier.py:96-101`).
The heuristic also reads thread replies. So the model sees less than the heuristic it overrides.

### Q6 Future-fit

At ten times the comments, a per-comment paid call with an in-process cache does not scale.
The cache dies with the process, so every daily run pays again.
The design must cache across runs and cap calls and wall time per run.

## Prior Art / Constraints

### Direct prior art from memory

- ADR-111 ("Skill Model Pins Project Per Harness", accepted): default to the harness-inherited model; no versioned id in skills. Relevance: the fallback must not hard-code a model id. Decision: honor.
- ADR-006 ("Thin workflows, testable modules"): logic lives in Python, not YAML. Relevance: transport choice and cache keys live in the module. Decision: honor.
- ADR-035 ("Exit code standardization"): 0 ok, 1 logic, 2 config, 3 external, 4 auth (lines 54 to 58). Relevance: the Secret presence truth table maps its cases to 2, 3, and 4. Decision: honor.
- ADR-021 ("AI Review Model Routing Strategy", accepted 2025-12-23): names `claude-haiku-4.5` as a JSON-extraction fallback for CI review. Relevance: covers CI review routing, not this utility, and predates ADR-111. Decision: not binding here.
- `.claude/rules/plugin-self-containment.md` MUST 4: a shipped plugin script stays stdlib-only at import time. Relevance: applies if this module ever ships in a plugin. Decision: honor by design.
- `pyproject.toml` import-linter contract `shipped-lib-no-runtime-dependencies`: forbids `anthropic` in `scripts.hook_utilities`, `scripts.github_core`, `scripts.ai_review_common`, `scripts.failure_classifier`. Relevance: it does not cover `scripts.llm_classification` today. The "no vendor SDK" rule here comes from the owner ruling, not this contract. Decision: adapt (a new test enforces it, AC 1).
- `scripts/eval/_providers.py:104` `EvalProvider`: one `complete(messages, system, model, max_tokens, ...) -> str` protocol over six billing-matrix cells (`_billing_matrix.py:122-244`, read 2026-11-23): Claude, Codex, and Copilot, each with API and subscription billing. Relevance: the repo already owns a transport seam. Decision: adapt (see Open question 1).
- (chestertons-fence recommendation: REPLACE `classifier.py` transport, PRESERVE the band, the 0.7 apply threshold, the JSON verdict shape, and the cache normalization in `cache.py`.)

### Connected context from prior-art search

- Connected entity: `scripts/eval/_claude_cli.py`, transport. Adjudication: in-scope. Note: strips `ANTHROPIC_API_KEY` and five related vars from the child env (lines 85 to 94), so a subscription call cannot bill a metered key.
- Connected entity: `scripts/eval/_http_providers.py`, transport. Adjudication: blast-radius. Note: the OpenAI-compatible cell imports the `openai` SDK lazily (line 318) and the SDK Anthropic cell imports `anthropic` (line 446). Only `scripts/eval/_anthropic_api.py` is stdlib `urllib` (lines 16 to 17).
- Connected entity: `.github/workflows/update-reviewer-stats.yml`, workflow. Adjudication: in-scope. Note: the sole runtime until the owner deleted it on 2026-11-25; no workflow runs the script now.
- Linked project: claude-mem (`github.com/thedotmack/claude-mem`, `LICENSE` is Apache-2.0, checked through the GitHub license API on 2026-11-23). Why it matters: its observer model runs in a background worker; `CLAUDE_MEM_PROVIDER` picks the vendor and `CLAUDE_MEM_MODEL` the model; `DEFAULT_LLM_TIMEOUT_MS = 180_000` (line 138 of `SettingsDefaultsManager.ts` in the claude-mem repository). Pattern borrowed: provider and model are config, never code. No code copied. Apache-2.0 places no duty on a borrowed design pattern.
- (Search depth: medium, matched to Tier 3.)

### Coverage notes

- Topic `llm_classification` consumers: searched module, class, factory, and env names with `git grep`; results: 1 runtime consumer, 4 test files (2026-11-23). Confidence: high.
- Topic per-harness model access: searched repo code, tests, and skill prose. Vendor docs not checked: the web search API returned HTTP 401 on 2026-11-23. Confidence: low for Cursor, Muse, and Hermes.
- Topic host-agent handback or MCP sampling: searched `host agent`, `agent-in-the-loop`, `return the prompt`, `sampling/createMessage`; results: 0. Confidence: high.

## Problem statement

The fallback is bound to one vendor SDK, one model id, and one API key.
Where any of the three is missing, it returns `None` without a word.
It cannot run inside Codex, Copilot CLI, Cursor, Muse, or Hermes.
And its one consumer never turns it on, so nobody knows if it helps.

## Recon summary (2026-11-23, `84c395f822`)

### Consumers of `scripts/llm_classification`

| Consumer | File and lines | Runtime |
|---|---|---|
| `update_reviewer_signal_stats.py` | Import at 53. Classifier built at 750 to 765. Called from `get_actionability_score` at 331. | None since 2026-11-25. Before that: GitHub Actions cron, `update-reviewer-stats.yml:82` and `:91`, daily 06:00 UTC <!-- citation-freshness: ignore -- anchors here are command strings from another column; cited lines re-read 2026-11-24 --> |
| Tests | `tests/llm_classification/` | pytest |

No hook, skill, or lefthook job imports it. Search: `git grep -n -E "llm_classification|LLMClassifier|get_default_classifier|LLM_FALLBACK"`.

### Other direct model calls

| Code | Mechanism | Runtime |
|---|---|---|
| `scripts/ci/invoke_claude_review.py` | Anthropic SDK | CI, through `.github/actions/ai-review/action.yml` |
| `packages/semantic-hooks/src/semantic_hooks/embedder.py` | OpenAI embeddings SDK | Opt-in local Claude Code hook package |
| `scripts/eval/_http_providers.py`, `_claude_cli.py`, `_codex_cli.py`, `_copilot_cli.py` | SDK, HTTP, and CLI subprocess | Local eval runs |
| `llm-council`, `benchmark-models` skills | `claude -p`, `codex exec`, `copilot -p` | Local, from skill prose |

### Model access per harness

Evidence is repo code and tests only (vendor docs unavailable, see Coverage notes).

| Harness | One-shot mechanism | Tools off? | Model choice | Evidence |
|---|---|---|---|---|
| Claude Code | `claude --print --output-format json --model M --setting-sources "" --strict-mcp-config --tools "" --disallowed-tools ... --no-session-persistence` | Yes | `--model` | `scripts/eval/_claude_cli.py:202-224` <!-- citation-freshness: ignore -- anchors here are command strings from another column; cited lines re-read 2026-11-25 --> |
| Codex | `codex exec --model M --sandbox read-only --ephemeral --ignore-user-config --output-last-message F` | Read-only sandbox | `--model` | `scripts/eval/_codex_cli.py:165-177`. Its docstring says no live run yet (lines 21 to 24). <!-- citation-freshness: ignore -- anchors here are command strings from another column; cited lines re-read 2026-11-24 --> |
| Copilot CLI | `copilot --acp --model M --available-tools= --no-custom-instructions --disable-builtin-mcps` over JSON-RPC | Yes | `--model` | `scripts/eval/_copilot_cli.py:399-418` <!-- citation-freshness: ignore -- anchors here are command strings from another column; cited lines re-read 2026-11-24 --> |
| Cursor | `cursor-agent --trust --force -p` | No evidence. `--force` allows shell. | None found | `tests/e2e/test_cursor_plugin_smoke.py:190-205` <!-- citation-freshness: ignore -- anchors here are command strings from another column; cited lines re-read 2026-11-24 --> |
| Muse | `muse exec --json --trust-workspace --disable-web-tools` | Web tools only | None found | `tests/e2e/test_muse_agents_load.py:89` <!-- citation-freshness: ignore -- anchors here are command strings from another column; cited lines re-read 2026-11-24 --> |
| Hermes | None found | n/a | n/a | Searched `hermes (chat\|-z\|-q\|run)` and `tests/e2e/hermes_runtime.py` |

Not found in the repo: a host-agent handback convention, MCP sampling, prompt-type hooks,
and any CLIProxyAPI reference. `OPENAI_BASE_URL` is an operator-set endpoint (`_providers.py:150`).

## User stories

1. As the reviewer-stats cron, I classify an ambiguous comment with whatever model the operator configured, so the stats do not depend on one vendor.
2. As a maintainer running the script on a laptop under any harness, I opt in to my own CLI login and get the same verdict shape, with no API key.
3. As the owner, I see in the run summary how many comments used the fallback and how many kept the heuristic, so a silent no-op cannot hide.

## Call contract

### Input

| Field | Type | Notes |
|---|---|---|
| `comment_body` | `str` | Untrusted text. Truncate to 4,000 characters. |
| `thread_replies` | `list[str]` | New. Up to 3 replies, each truncated to 500 characters. Closes the gap in Q5. |
| `heuristic_score` | `float` | In the contract and logged per call. Deliberately not sent to the model, so it cannot anchor the answer. |

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
| Per-call timeout | 30 s | Small-model HTTP calls return in seconds. A slow call is a failed call here. |
| Retries | 1, on a transient error only | Current code retries twice. Auth, missing binary, and parse failures do not retry. |
| Calls per run | `LLM_FALLBACK_MAX_CALLS`, default 200 | Hard cap. |
| Fallback wall time per run | `LLM_FALLBACK_BUDGET_SECONDS`, default 600 | Checked before each call. Once spent, no new call starts. |

A comment skipped by either cap keeps its heuristic verdict and counts as `fallback_capped`.
Worst case per run: the wall budget plus one in-flight call, about 11 minutes.
That fits inside the 15-minute step budget the sibling step used in the update-reviewer-stats workflow, which was deleted on 2026-11-25.

### Caching

- Key: SHA-256 of the normalized comment plus replies (keep `cache.py` normalization), plus prompt version, provider, and model.
- A verdict stored under a key never expires on time. A new reply, prompt, or model makes a new key, and so one new call.
- In-memory LRU stays as the first tier. A JSON file is the second tier.
- Local: the file lives under `.project-toolkit/cache/`.
- CI: `actions/cache` entries are immutable per key, so save under `llm-fallback-v<prompt_version>-<run_id>` and restore with the prefix `llm-fallback-v<prompt_version>-`. Each run restores the newest file and saves a new one.
- The file stores keys and verdicts only, never raw comment text or secrets.

## Transport options, ranked

Rank depends on the runtime. The only consumer today runs in CI, which has no host agent.

### In CI (the only runtime today)

| Rank | Transport | Failure mode |
|---|---|---|
| 1 | Anthropic Messages API through the stdlib path in `scripts/eval/_anthropic_api.py`, keyed by the `agent-claude` environment's `ANTHROPIC_API_KEY` | No new secret needed. Secret empty: `unconfigured`. Endpoint down or 5xx: `unavailable`. 401 or 403: `auth`. |
| 2 | Operator-configured OpenAI-compatible HTTP endpoint (non-empty `OPENAI_BASE_URL` plus `OPENAI_API_KEY`). Covers CLIProxyAPI, Azure OpenAI, and any gateway. | Same states. Needs a new secret. |
| Deferred | `claude-cli` cell with the environment's `CLAUDE_CODE_OAUTH_TOKEN` | The token exists, but the runner would need the `claude` binary and the nested-session question (Open question 4) answered. |

The existing OpenAI-compatible cell imports the `openai` SDK (`_http_providers.py:318`).
Rank 1 needs a stdlib `urllib` client to meet the no-vendor-SDK rule. See Open question 1.

### Inside a harness (local runs)

| Rank | Transport | Failure mode |
|---|---|---|
| 1 | Either HTTP transport above, when configured | As above. |
| 2 | The user's CLI, by explicit opt-in only: `claude-cli`, `codex-cli`, or `copilot-cli` cell | Binary missing or not logged in: `unavailable`. Runs with tools off and metered env stripped, as the `claude-cli` and `copilot-cli` cells already do. `codex-cli` 0.172.0 has no flag that turns tools off, and `--sandbox read-only` still allows file reads. So `codex-cli` is refused until such a flag exists. Spends the login's quota. |
| Excluded | Cursor, Muse | No evidence of a tool-less one-shot mode. Comment text is untrusted, so a mode with shell access is a prompt-injection path. Re-admit when a probe proves tools are off. |
| Excluded | Hermes | No one-shot mechanism found. |
| Rejected | Hand the prompt back to the host agent | No repo convention, and the only consumer has no agent in the loop. |

CLI transports are opt-in for two reasons. They spend the user's subscription quota.
And a `claude --print` child started from inside a Claude Code session is a nested session.
Whether it re-fires the parent's hooks is untested (Open question 4).

### Selection

`LLM_FALLBACK_PROVIDER` names a cell: `openai`, `anthropic`, `claude-cli`, `codex-cli`, `copilot-cli`, or `none`.
With no value, auto-detect HTTP only, in this order:

1. `ANTHROPIC_API_KEY` set: `anthropic`.
2. `OPENAI_BASE_URL` and `OPENAI_API_KEY` both set: `openai`.
3. Otherwise `none`.

"Set" means non-empty after stripping whitespace. An unmapped GitHub secret renders as an empty string, so an empty value is the same as absent.
This matters for `OPENAI_BASE_URL`: the eval cell treats set-but-empty as "use the default OpenAI endpoint" (`scripts/eval/_providers.py:150-158`). The fallback must not inherit that, or an empty variable silently routes comments to a third-party endpoint.

Auto-detect never picks a CLI cell. Harness detection is Open question 3.

### Secret presence: no false positives, no false negatives

The CI secrets are optional. Two errors to rule out:

- **False negative (silent pass):** the fallback was meant to run, did not, and the run looks the same as a run where it worked. This is today's state: the key is never mapped, `enabled` goes `False`, and nothing says so.
- **False positive (false alarm):** the run goes red, or warns, when nothing is wrong. A fork, a `gh act` run, or another repository has no secret by design. Failing them is noise that trains people to ignore the signal.

The rule: absence of a key is never an error, but it is never silent. A key that is present and does not work is always an error.

| Case | Inputs | Fallback status | Exit | Signal |
|---|---|---|---|---|
| 1 | `LLM_FALLBACK_ENABLED=false` | `disabled` | 0 | Summary line `fallback: disabled`. No annotation. |
| 2 | No provider named, no key (empty or unset) | `unconfigured` | 0 | Summary line `fallback: unconfigured, N comments in band kept the heuristic` and one `::notice::` annotation. |
| 3 | No provider named, key present, calls succeed | `active` | 0 | Summary counters. |
| 4 | Provider named, its key empty | `misconfigured` | 2 | Stats written first. `::error::` names the missing variable, never its value. |
| 5 | Key present, a call returns 401 or 403 | `auth_failed` | 4 | Stats written first. Stop calling after the first refusal. |
| 6 | Key present, more than half of attempted calls fail (network, 5xx, timeout, bad reply) | `degraded` | 3 | Stats written first. `::error::` with the failure counts. |
| 7 | Key present, some calls fail, at most half | `partial` | 0 | `::warning::` with `fallback_unavailable` and attempted counts. |
| 8 | Key present, band empty | `active` | 0 | Summary shows 0 calls, so a zero is distinguishable from "never ran". |
| 9 | `OPENAI_BASE_URL` empty, `OPENAI_API_KEY` present, no Anthropic key | `unconfigured` | 0 | As case 2. The empty URL never selects the default endpoint. |

Why these exits: ADR-035 assigns 2 to configuration, 3 to external failure, 4 to auth. Case 4 is a config error only when someone named a provider on purpose, so the workflow must never set `LLM_FALLBACK_PROVIDER`. It maps the key only, and auto-detect picks it up. A fork then lands in case 2, not case 4.

The 50 percent line in cases 6 and 7 is `LLM_FALLBACK_MAX_FAILURE_RATE`, default 0.5. It needs at least 5 attempted calls before it can fire, so one flaky call on a small band cannot turn a run red.

Every case writes the stats table before it exits. The heuristic stays the floor, because the stats job is a report, not a gate.

Each run also counts `fallback_used`, `fallback_cached`, `fallback_unavailable`, `fallback_capped`, and `band_total`.
They go to the step summary that `_write_step_summary` already writes (`update_reviewer_signal_stats.py:575`), with the status from the table.

Logging never prints a key, a key prefix, or a key length. It prints only `present` or `absent`.

## Harness agnosticism

- `scripts/llm_classification` imports no vendor SDK. It depends on a `Transport` protocol:
  `complete(system: str, user: str, model: str | None, max_tokens: int, timeout: float) -> str`.
- The model id comes from `LLM_FALLBACK_MODEL` or the transport default. Code holds no model id.
  `None` means "the CLI's own default", which inherits the harness model per ADR-111.
- CLI transports reuse the `EvalProvider` cells for argv, env stripping, and billing guards.
  The Claude and Copilot cells are code-verified. The Codex cell has no live run yet.
- The `anthropic` package leaves this module's import graph. A test asserts the module imports with `anthropic` and `openai` blocked.

## Config surface

| Variable | Today | Proposed |
|---|---|---|
| `LLM_FALLBACK_ENABLED` | Defaults to "API key present" | Keep. Default becomes "a transport resolved". |
| `LLM_FALLBACK_MIN`, `LLM_FALLBACK_MAX` | 0.4, 0.6 | Keep. |
| `LLM_FALLBACK_MODEL` | Defaults to `claude-haiku-4-5-20251001` | Keep the name. Default becomes unset (transport default). |
| `LLM_FALLBACK_CACHE_SIZE` | 100 | Keep for the in-memory tier. |
| `LLM_FALLBACK_PROVIDER` | n/a | New. Names the transport cell. |
| `LLM_FALLBACK_MAX_CALLS` | n/a | New. Default 200. |
| `LLM_FALLBACK_BUDGET_SECONDS` | n/a | New. Default 600. |
| `LLM_FALLBACK_TIMEOUT` | n/a | New. Default 30. |
| `LLM_FALLBACK_MAX_FAILURE_RATE` | n/a | New. Default 0.5, with at least 5 attempted calls. Above it the run is `degraded` and exits 3. |
| `ANTHROPIC_API_KEY` | Sole enable signal | Read only by the `anthropic` transport and auto-detect step 2. |

Migration: one consumer, one workflow, and nothing sets these in CI today.
So the change is additive. A local setup with only `ANTHROPIC_API_KEY` set
auto-detects the `anthropic` transport and keeps working. An old `LLM_FALLBACK_MODEL` value still passes through.
The plan to turn the fallback on in CI was to map the existing `agent-claude` secret `ANTHROPIC_API_KEY` into the `Run statistics aggregation` step of `update-reviewer-stats.yml`, with no new secret and no `LLM_FALLBACK_PROVIDER` line. That workflow was deleted on 2026-11-25, so the mapping has no target until the owner picks a new runtime.

## Cost and latency per call

Rates from `scripts/eval/_eval_common.py` (read 2026-11-23). About 1,500 input and 60 output tokens per call.

| Model class | Input rate per 1K | Output rate per 1K | Cost per call |
|---|---|---|---|
| Haiku 4.5 | $0.001 | $0.005 | about $0.0018 |
| Haiku 5.5 | $0.0001 | $0.0005 | about $0.0002 |
| Sonnet 5 | $0.002 | $0.010 | about $0.0036 |

At the 200-call cap, one run costs at most about $0.72 on Sonnet 5 and $0.36 on Haiku 4.5.
The cross-run cache drops repeat runs toward zero, since a 90-day window repeats most comments daily.
A subscription CLI cell has no per-call charge but counts against the login's quota.

Latency: this repo has no measured single-classification latency.
Expected: under 3 s per HTTP call to a small model, 5 to 20 s per CLI call (INFERRED, eval step 4 measures it).
Bounds: 30 s per call, 600 s of fallback time per run.

## Eval method (before anyone builds)

1. **Measure the band.** Run the heuristic over the 90-day comment set. Record the count and share at 0.4 to 0.6, and the share at exactly 0.5 with no matched pattern. No model needed.
   - Unit: production scores every comment node in a thread, replies included (`update_reviewer_signal_stats.py:212-245`). Report the band share split into thread openers and replies.
   - Window: the fetch filters on PR `updatedAt`, not comment time (`scripts/github_core/api.py:1343`). State this in the result.
   - Loss: `reviewThreads(first: 100)` and `comments(first: 50)` request no `pageInfo` (`api.py:1341-1345`). Count PRs and threads that hit either limit and report the loss. Do not present a partial read as the full set.
2. **Build a labeled corpus.** Sample 200 comments, stratified: 100 from the band, 100 outside it, across every reviewer in the signal table.
   - Unit: the eval scores the same unit production scores, with thread position recorded per row.
   - Labelers (owner decision, 2026-11-24): a council of 3 non-Anthropic models. Arm C runs on Anthropic, so no labeler shares its vendor. The label is the majority vote. The council sees only the blinded sheet, never arm output.
   - Agreement floor: all three models must agree on at least 70 percent of items. Below that, the labels are too noisy to decide anything, and the eval stops before scoring.
   - The owner spot-checks 20 items, drawn at random with a recorded seed. The report states the council's agreement rate and the spot-check match rate.
   - Labelers see the comment, its file path, and the diff hunk it points at. The current fetch has no hunk, so the corpus builder fetches it separately. They do not see thread replies, heuristic scores, or any arm's output.
   - Hold out 40 band items as a dev split for prompt work. Freeze the prompt, provider, and model, and commit them, before the other 160 items are scored.
   - Labels must not come from thread replies. The heuristic already reads replies, so reply-derived labels make it grade itself.
   - Store as JSONL under `evals/comment-actionability/` with the label rubric.
3. **Score three arms** on band items, then on all items:
   - A: heuristic as shipped (`>= 0.5` is actionable).
   - B: heuristic with the tie broken the other way (`> 0.5`). A deterministic baseline with no model.
   - C: heuristic plus model fallback, per transport and model tried.
4. **Report** accuracy, precision, and recall per arm, per-call p50 and p95 latency for arm C, and a paired bootstrap 95 percent CI on the accuracy gap between C and the better of A and B, over band items.
5. **Reuse first.** `scripts/eval/eval-prompt-change.py` already runs scenario files with an `expected_verdict`. Check whether it scores this corpus with no new code before writing a runner.

6. **Run arm C on an HTTP transport** with the model CI would use. CLI-cell results count for accuracy only, since CLI spawn time does not transfer to CI latency.

Verdict rule (owner decision, 2026-11-24). The gap is C minus the better of A and B, on held-out band items.

- **Pass:** the gap is at least 10 points, and the CI lower bound is above 0.
- **Fail:** the CI upper bound is under 10 points. Only this is evidence that the gain is below the bar.
- **Inconclusive:** anything else. A small sample cannot fail the fallback by itself.

Why: at 60 held-out items the smallest gap the eval can detect is about 11 to 20 points, depending on how often C and the baseline disagree. Under the old rule, noise alone could fire kill criterion 2.

On a look-1 inconclusive, label 100 more band items once, then score all held-out band items together (look 2).
Both looks use a 97.5 percent interval, which splits the 5 percent error budget over the two looks.
The bootstrap resamples whole PRs, not single comments, because comments on one PR are correlated.
A look-2 inconclusive is final. Kill criterion 2 does not fire, and the owner decides.

## Kill criteria

Drop the model fallback, and delete `scripts/llm_classification`, if any holds:

1. Fewer than 5 percent of comments land in the band (eval step 1). The fallback would move nothing.
2. The verdict is fail: the CI upper bound on the gap is under 10 points. A one-character tie-break rule would then do the job.
3. The signal table's reviewer ranking is the same under A and C. Nobody downstream would act differently.
4. The `agent-claude` environment's `ANTHROPIC_API_KEY` cannot reach a model from the CI runner, and no other transport is configured. (Owner, 2026-11-24: a CI secret is acceptable if the eval passes. The secret already exists.)
5. At steady state, the chosen CI transport still caps out: `fallback_capped` above 10 percent of `band_total` under the 600 s budget at measured p95. The projection also adds failed-call wall time (`n_call_error`, `call_error_s_total`), since timeouts spend the budget too. Steady state starts after `band_total / min(LLM_FALLBACK_MAX_CALLS, 600 / p50)` daily runs, or after one backfill run with the caps raised. The M1 decision record projects that run count.

## Failure modes

| Failure | Effect | Handling |
|---|---|---|
| Transport unconfigured, disabled, misconfigured, refused, degraded, or partial | Some or no calls | See the Secret presence truth table. Stats always written first. |
| Malformed or non-JSON reply | One comment unclassified | `None`, counted `fallback_unavailable`, heuristic stands. |
| Call or wall budget spent | Rest of band unclassified | Counted `fallback_capped`, heuristic stands. |
| Prompt injection in comment text | Model returns a forced verdict | Tools are off and output is three typed fields, so the blast radius is one wrong label. Eval arm C measures label quality. |
| Cache file corrupt or unreadable | Cold cache | Log a warning, start empty, overwrite on save. |

## Observability

- Step summary: `band_total`, `fallback_used`, `fallback_cached`, `fallback_unavailable`, `fallback_capped`, provider, model, total fallback seconds.
- Log line per call at DEBUG: cache key prefix, heuristic score, verdict, confidence, latency. Never the comment text.
- The reviewer table gains no new column (Open question 2).

## Security

- Comment text is untrusted. It goes in the user message only, never the system prompt.
- No transport may run with tools, shell, or file write enabled. This is why Cursor and Muse are excluded today.
- The reply is parsed as JSON into three typed fields. Nothing in it is executed or used as a path.
- Secrets stay in env vars and CI secrets. The cache stores verdicts and hashes, never keys or raw text.

## Buy-vs-build decision

Reuse, do not buy. The repo owns `EvalProvider` and three CLI cells with billing guards.
claude-mem solves a different problem (a long-lived observer worker) and is a TypeScript service.
Build only the stdlib HTTP client and the cross-run cache, and only after the eval passes.

## Complexity classification

Tier 3. One consumer, but the transport seam is shared with `scripts/eval`.
Promoting it (Open question 1, option A) is an architecture change and needs an ADR.

## Acceptance criteria

1. `scripts/llm_classification` shall import with `anthropic` and `openai` blocked in `sys.modules`. A test proves it.
2. `scripts/llm_classification` shall hold no default model id. A test fails on a `claude-`, `gpt-`, or `gemini-` literal in the module.
3. When a model reply lacks a bool `is_actionable`, the classifier shall return `None` and count `fallback_unavailable`, never a verdict.
4. For each of the nine cases in the Secret presence truth table, a test shall drive `main(argv)` with an env built for that case, with inherited model keys stripped, and assert the exit code, the status line, and that the stats table was written. A key value placed in the env shall not appear in captured stdout, stderr, or the summary file.
5. When the same comments are scored a second time with the cache file present, the run shall make 0 model calls.
6. Calls per run shall not exceed `LLM_FALLBACK_MAX_CALLS`, and no call shall start after `LLM_FALLBACK_BUDGET_SECONDS`. Skipped comments keep the heuristic verdict and count as `fallback_capped`.
7. Each CLI transport shall run with tools disabled and metered-billing env vars stripped, inherited from its `EvalProvider` cell.
8. The eval report from the Eval method section shall be committed before work on AC 1 to 7 starts.

## Plan

1. Eval steps 1 to 4. No library code. Decide against the kill criteria.
2. If the eval passes: owner decides Open question 1. Write the ADR if option A.
3. Build the transport, the contract, the cache, and the counters, with tests for AC 1 to 7.
4. Blocked since 2026-11-25: `update-reviewer-stats.yml` was deleted, so this step has no target until the owner picks a new runtime. The step was: map the `agent-claude` environment's `ANTHROPIC_API_KEY` into the stats step, set no `LLM_FALLBACK_PROVIDER` there, and watch one run's summary.

## Out of scope

- Fixing the heuristic's 0.5 tie-break (Q5). Eval arm B measures it. The fix is its own change and the owner's call.
- The other direct model calls in the recon table. They have their own runtimes and owners.
- Adding Cursor, Muse, or Hermes transports. Each needs a probe that proves a tool-less mode first.
- Updating `.project-toolkit/specs/STATUS.md`, last updated 2026-01-21.

## Open questions

1. **Where does the transport seam live?** `EvalProvider` loads its cells with bare sibling imports (`from _claude_cli import`, `_providers.py:59-67`). `scripts.llm_classification` cannot import it without putting `scripts/eval` on `sys.path`. Its OpenAI-compatible cell also imports the `openai` SDK. Options:
   - A. Promote the protocol and cells to a package such as `scripts/model_transport/`, add a stdlib OpenAI-compatible client, and repoint `scripts/eval`. One seam for both. Wider change, touches eval tests.
   - B. Add `scripts/eval` to `sys.path` in `llm_classification` and call `resolve_provider`. Smallest diff. Couples a CI utility to private eval modules, and pulls in the `openai` SDK.
   - C. Write a small stdlib HTTP transport inside `llm_classification` and skip CLI cells. Smallest scope. Gives up local CLI support.
   Recommendation: A, if the eval passes. It is an architecture change, so it needs an ADR and the owner's decision.
2. Should the summary publish fallback counts per reviewer, or only per run?
3. Should auto-detect pick the user's harness CLI? The only harness marker with repo evidence is `CLAUDECODE` (`scripts/validation/run_workflow_local_test.py:130`). No Codex or Copilot marker is evidenced. Current answer: no, CLI is opt-in.
4. Does a `claude --print` child started inside a Claude Code session re-fire the parent's hooks? The eval cell passes `--setting-sources ""` to avoid loading settings, but no test proves hooks stay quiet.
5. Answered 2026-11-24: a CI secret is acceptable if the eval passes. The `agent-claude` environment already holds `ANTHROPIC_API_KEY`, so no new secret is needed for CI rank 1.

## Noticed, outside this spec

- `update_reviewer_signal_stats.py:11-14` documents exit 2 for an external error. ADR-035 assigns 3. Recorded for the owner's decision.
- `.project-toolkit/specs/STATUS.md` was last updated 2026-01-21. It lists 1 of the 10 `SPEC-*.md` files present on 2026-11-23.

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
