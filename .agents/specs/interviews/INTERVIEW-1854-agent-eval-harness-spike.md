# Interview: Issue #1854: Agent Eval Harness Spike + ADR

**Date**: 2026-05-03
**Issue**: [#1854](https://github.com/rjmurillo/ai-agents/issues/1854), `spike: prove the eval-harness shape with one agent + write the ADR`
**Mode**: auto, recommendations applied unless user overrides

## Problem (one sentence)

Each agent in `templates/agents/` is treated as a specialized worker, but the project has no mechanism that proves a given agent's context recipe produces measurably better outputs than the same model with a generic prompt; the issue scopes a spike (one agent, ~10 fixtures, deterministic scoring, baseline comparison) plus an ADR that documents corpus structure, scoring discipline, baseline definition, threshold-setting methodology, and re-baseline cadence.

## Codebase-derived answers (no user question needed)

| Question | Answer | Source |
|---|---|---|
| Is there existing eval scaffolding to reuse? | Yes, `scripts/eval/_anthropic_api.py`, `_eval_common.py`, `eval-prompt-change.py`, `eval-agents.py`. Add a new runner; do not overload existing ones. | `scripts/eval/` |
| Are there existing scenarios for the security agent? | Yes, `tests/evals/security-scenarios.json` with `IDENTIFY/OK/ESCALATE` verdicts and `expected_reason_contains` regex (CWE strings). | `tests/evals/security-scenarios.json` |
| What's the ADR location convention? | `.agents/architecture/ADR-NNN-*.md`. Issue body says `docs/adr/` but that path doesn't exist in this repo. | `.agents/architecture/` (79 ADRs, none under `docs/adr/`) |
| Does ADR-057 already cover this? | No, ADR-057 covers prompt-change before/after on the same prompt. This issue asks agent-vs-baseline efficacy (different question, same model, different prompts). | `.agents/architecture/ADR-057-prompt-behavioral-evaluation.md:46-56` |
| What's the security-related agent name? | `security` (template at `templates/agents/security.shared.md`, agent at `.claude/agents/security.md`). Issue uses "security-reviewer" loosely. | `templates/agents/`, `.claude/agents/` |
| Where do existing fixture-based corpora live? | `.agents/security/benchmarks/` (CWE-22, CWE-77, agent-review-quality) and `tests/evals/`. Top-level `evals/` does not exist. | `find . -type d -name evals` |

## Branches walked (decisions with recommendations)

### B1. User stories: `CONFIRMED`

US-1. As an agent maintainer, when I propose a change to `templates/agents/security.shared.md`, I run a deterministic eval that compares the agent prompt's output distribution against the same model with a generic prompt on a held-out corpus, so I get a numeric delta and pass/fail signal that survives reruns.

US-2. As an architect, when the spike completes, I read the ADR at `.agents/architecture/ADR-NNN-agent-eval-discipline.md` and decide whether to graduate the eval to CI for a small set of agents, keep it as an offline audit, or scrap it.

US-3. As a future agent author, when I introduce a new agent template, I apply the methodology in the ADR (corpus structure, scoring, baseline, per-agent threshold, cadence) without re-deriving the approach.

### B2. Data model: `CONFIRMED`

Three entities, all immutable once committed:

- **Fixture**. `id` (e.g., `F001`), `input` (string), `provenance` (`synthetic` | `public-cve` | `paraphrased-from-public`), `assertions[]` (each with `kind` ∈ {`regex`, `verdict`, `ast`} and `pattern`/`value`), `tags[]` (CWE, OWASP). Stored at `evals/security-spike/fixtures/F###.json`. Append-only.
- **Run**. One model call against one `(fixture, variant, run_index)`. Persists `model_id`, `variant` (`agent` | `baseline`), `prompt_sha`, `prompt_text` (or pointer + sha), `fixture_sha`, `temperature`, `seed_if_supported`, raw `response`, parsed `assertions[]` with pass/fail per assertion, `tokens_in/out`, `latency_ms`, `outcome` (`ok` | `error`), `attempt`. JSONL under `evals/security-spike/runs/<RUN_ID>/runs.jsonl`. Same `(fixture, variant, run_index)` is replayed-not-duplicated on retry.
- **Report**. Aggregated comparison: per-variant recall, per-fixture pass-rate distribution across N runs, paired-bootstrap CI on the recall delta, total tokens / cost / wall-clock, recommendation. Markdown at `evals/security-spike/reports/<RUN_ID>/REPORT.md` + `report.json` sidecar.

Every persisted record includes `schemaVersion: 1`. Reads against unknown major versions fail closed.

### B3. Integrations: `CONFIRMED`

- **Anthropic API** via `scripts/eval/_anthropic_api.py`. Failure surfaces: 408, 429, 5xx, timeout, content policy, tokenization. Retries: max 3 with exponential backoff (base=1s, max=30s) and jitter on 408 / 429 / 5xx / timeout. Any other 4xx (400, 401, 403, 404, 409, etc.) records `outcome=error` immediately with `error_category` set; no retry.
- **Filesystem**. Writes are write-temp-then-rename. Run directories are timestamped + UUID; collisions impossible by construction.
- **GitHub**. No real-time integration during the spike; results cited in PR body.

### B4. Failure modes: `CONFIRMED`

- **Retries**: per-run, max 3, exponential backoff with jitter, only on transient categories.
- **Idempotency**: `(fixture_id, variant, run_index)` is the key. Replay overwrites a still-pending row but rejects (`AC-9`) on a completed row in the same RUN_ID.
- **Partial failure**: errors above 10% of fixtures fail the spike with a typed message. Report computes `recall_with_errors` (errors counted as fail) and `recall_excluding_errors` (errors dropped) separately so the headline does not silently shift on transient outage.
- **Replay determinism**: `temperature=0.0` for the spike. Multi-run (N=3 default) anyway because temp 0 does not eliminate variance. Distribution is reported, not averaged.
- **Schema evolution**: `schemaVersion` on every record; new fields optional; removal is two-step.

### B5. Security: `CONFIRMED`

- Anthropic API key from environment (`ANTHROPIC_API_KEY`), never logged. Reuse `_anthropic_api.load_api_key()`.
- Fixtures must declare `provenance`; real customer data, real credentials, and real third-party secrets are rejected at ingestion.
- Token counts logged; response bodies stored on disk (in run directory) but redacted from stderr structured logs.
- Cite: `.claude/rules/security.md`, `.agents/governance/SECURITY-REVIEW-PROTOCOL.md`. Spike does not modify any security gate; eval is offline.

### B6. Observability: `CONFIRMED`

- Structured JSON logs to stderr, one record per run: `fixture_id`, `variant`, `model_id`, `attempt`, `outcome`, `latency_ms`, `tokens_in/out`, error category if applicable.
- Aggregated report metrics: per-variant recall and (where negative cases are present) precision; per-fixture pass-rate distribution across N runs; paired-bootstrap CI on the recall delta; total tokens, total wall-clock, total cost estimate; `flakiness=true` if any fixture has non-zero pass-rate variance across N runs on the same `(prompt_sha, fixture_set_sha)`.
- No alerts; spike is offline. ADR proposes how alerts would attach if the eval graduates to CI.

### B7. Scope boundaries: `CONFIRMED`

- **Out of scope**: multi-agent coverage, hard-coded delta thresholds, CI gate, LLM-as-judge as the gated signal (allowed only as a sidecar), cost-budget enforcement at runtime, conflation with ADR-057's prompt-change validation.
- **Deferred**: promotion to CI for multiple agents (owner: architect; trigger: ADR + at least one additional agent eval); cross-model variance study (owner: qa; trigger: meaningful delta on the spike); held-out corpus expansion to 50+ fixtures (owner: security; trigger: graduate-to-CI decision).

## Open questions resolved by recommendation

| OQ | Question | Recommendation | Status |
|---|---|---|---|
| OQ-1 | Which agent for the spike? | `security`, only template with a crisp deterministic-scorable signal (CWE/OWASP/STRIDE strings) and existing scenario JSON to bootstrap from. | `CONFIRMED-BY-DEFAULT` |
| OQ-2 | Where do fixtures and reports live? | `evals/security-spike/` at repo root per issue body. Add `evals/README.md` cross-referencing `tests/evals/` (ADR-057) so the two are not confused. | `CONFIRMED-BY-DEFAULT` |
| OQ-3 | What does "held-out" mean? | Held-out = public-source paraphrased or synthetic, with `provenance` recorded; corpus purity beyond that is a follow-up the ADR addresses. | `CONFIRMED-BY-DEFAULT` |
| OQ-4 | Single model or matrix? | Single model (`claude-sonnet-4-6`). Matrix is deferred. | `CONFIRMED-BY-DEFAULT` |
| OQ-5 | Generic baseline prompt text? | `"Review the following input. Respond with one word: IDENTIFY, OK, or ESCALATE. Then explain in <=80 words."` **Deliberately naive**: no domain vocabulary ("security", "CWE", "vulnerability", "threat"), no role assignment. Same response shape so scoring is symmetric. SHA = SHA-256(UTF-8, no trailing newline). Lock the SHA in the report. **REVISED per decision-critic BLOCKER #3**: original baseline was too close to the agent prompt. | `CONFIRMED-BY-DEFAULT` |
| OQ-6 | ADR location? | `.agents/architecture/ADR-NNN-agent-eval-discipline.md`. Issue body's `docs/adr/` path is a typo. | `CONFIRMED-BY-DEFAULT` |
| OQ-7 | Commit/PR shape? | Three commits: (a) spike scaffolding (fixtures + runner), (b) report, (c) ADR. Each ≤5 files per `AGENTS.md`. | `CONFIRMED-BY-DEFAULT` |

## Verification

- [x] Every branch has a recorded decision.
- [x] Every requirement is testable as pass/fail (see acceptance criteria below).
- [x] Every "we will figure it out later" is explicitly Deferred or Out-of-scope.
- [x] User has authorization-by-auto-mode to override any `CONFIRMED-BY-DEFAULT` answer.
