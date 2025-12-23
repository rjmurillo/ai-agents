# ADR-017: Copilot model routing policy optimized for low false PASS

## Status

Proposed

## Date

2025-12-23

## Context

This repo invokes GitHub Copilot CLI via the composite action `.github/actions/ai-review/action.yml`.

The action builds context in ways that materially affect review quality:

- **PR (`context-type: pr-diff`)**
  - Runs `gh pr diff`.
  - If the diff exceeds `MAX_DIFF_LINES`, it switches to **summary mode** and provides only `gh pr diff --stat`, prefixed with a banner noting the PR is large.
  - It prepends the **PR title + body** via `gh pr view --json body,title`.
  - Net: for large PRs, the model often receives **no patch content**, only description + file stats.

- **Issue (`context-type: issue`)**
  - Provides **title, body, labels**.

- **Session logs (`context-type: session-log`)**
  - Loads file contents from `context-path`.

- **Spec files (`context-type: spec-file`)**
  - Provides full spec contents.
  - If a PR number is present, appends up to **500 lines** of `gh pr diff` (first 500 lines only).

Prompts under `.github/prompts/` span several shapes:

1. Strict format extraction (JSON-only issue triage).
2. Long-form writing (PRD generation and synthesis).
3. Diff-heavy code review (PR quality gates).
4. Evidence and traceability (REQ-* tracing, completeness vs implementation).

**Decision driver**: optimize for **lowest false PASS** (missing issues). Missed issues compound when agents run in parallel. This is more important than cost and latency.

This creates two core forces:

- **Evidence availability**: when PR context is summary-only, no model can do line-level code review.
- **Model fit**: code-evidence prompts need code-specialist behavior when patch evidence exists. Writing/security prompts need deep reasoning.

## Decision

Adopt an **evidence-aware, tiered model routing policy** with a conservative stance:

### 1. Evidence sufficiency rules (to reduce false PASS)

- If PR context is **summary mode** (stat-only), any prompt that normally expects code evidence MUST NOT produce a PASS verdict.
  - Output should be **WARN/CRITICAL_FAIL/REJECTED** (per prompt contract) and explicitly request the missing evidence.
  - Operationally: treat summary-mode PRs as **“risk review only”**, not “code review”.

- If the context includes only a **partial diff** (for example spec-file with 500-line head), the agent must:
  - Mark confidence as limited.
  - Prefer **WARN** over **PASS** unless every required check can be backed by evidence in the provided context.

### 2. Model routing matrix

Choose models by prompt shape and evidence availability:

- **Strict JSON / extraction (issue triage)**
  - Primary: `gpt-5-mini`
  - Fallback: `claude-haiku-4.5`
  - Goal: strict adherence to JSON schema and label taxonomy.

- **General review and synthesis (non-security)**
  - Primary: `claude-sonnet-4.5`
  - Escalation: `claude-opus-4.5` when uncertainty is high or the output is borderline PASS/WARN.
  - Goal: strong reasoning with lower false PASS via conservative escalation.

- **Security gate**
  - Primary: `claude-opus-4.5`
  - Goal: maximize depth, caution, and completeness.

- **Code evidence and traceability (requires patch evidence)**
  - Primary: `gpt-5.1-codex-max`
  - Fallback: `gpt-5.1-codex`
  - Use for: QA, DevOps, spec completeness, spec traceability, “tests tied to diff”.
  - If context is summary-only: route to `claude-opus-4.5` for risk review, and forbid PASS.

### 3. Governance

- Workflows MUST pass `copilot-model` explicitly per job.
- Add a guardrail step that fails the workflow if `copilot-model` is omitted (prevents silent regressions to defaults).

## Rationale

To minimize false PASS, we need both:

- **Conservative verdict policy**: insufficient evidence must block PASS.
- **Best-fit models**:
  - Code-specialist models are better at mapping checks to concrete diffs when diffs exist.
  - Opus-class models are better for high-stakes reasoning (security) and for “risk review” when diffs do not exist.

This reduces the chance that multiple parallel agents all “PASS” due to missing evidence or shallow review.

## Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|---|---|---|---|
| `claude-opus-4.5` everywhere | Lowest false PASS in ambiguous reasoning tasks | High cost; still cannot review missing patch content | Wasteful on triage; does not solve evidence gaps |
| `claude-sonnet-4.5` everywhere | Cheaper; good generalist | Higher false PASS risk on security and diff-heavy traceability | Does not match prompt shapes |
| Codex models everywhere | Strong on diffs/tests | Weak for long-form PRDs and summary-only PR contexts | Over-rotates to code tasks |
| Tiered routing without evidence rules | Easy to adopt | Still yields false PASS on summary-only PRs | Evidence sufficiency is required |

## Consequences

### Positive

- Fewer missed issues (lower false PASS), especially under parallel agent execution.
- Better evidence-based reviews for spec and traceability prompts.
- Security reviews become consistently deep and cautious.

### Negative

- More false FAIL / WARN outcomes (expected by design).
- Higher cost and longer runs in cases that escalate to Opus.
- Some PRs will require resizing or reruns with richer diff context to get a PASS.

## Implementation Notes

1. **Wire model selection into each workflow job**:
   - Issue triage categorize/roadmap: `gpt-5-mini`
   - PRD generation and security: `claude-opus-4.5`
   - PR gates QA/DevOps/spec checks: `gpt-5.1-codex-max` (only if diff context is present)
   - General review/synthesis: `claude-sonnet-4.5`

2. **Make evidence explicit to prompts**:
   - Add a standardized header in context: `CONTEXT_MODE=full|summary`.
   - Prompts should contain a rule: “If CONTEXT_MODE=summary, you must not PASS.”

3. **Optional but high leverage**: improve large PR evidence
   - Instead of stat-only, include a bounded patch sample:
     - `gh pr diff | head -N` plus `--stat`
     - or top-k changed files with truncated hunks
   - This directly lowers false PASS by enabling line-level checks.

4. **Aggregator policy** (if/when you add a final step):
   - “Max severity wins”: if any agent outputs CRITICAL_FAIL/REJECTED, the run fails.
   - If any agent reports insufficient evidence, treat as non-PASS until rerun with evidence.

## Related Decisions

- ADR-005 (PowerShell hardening) and ADR-014 (runner/cost) influence workflow reliability and execution time.

## References

- `.github/actions/ai-review/action.yml` (Build context: PR summary mode, issue view, spec-file diff head).
- `.github/prompts/*`
- `.github/workflows/ai-issue-triage.yml`
- `.github/workflows/ai-pr-quality-gate.yml`
- `.github/workflows/ai-spec-validation.yml`
- `.github/workflows/ai-session-protocol.yml`

---

## Agent-Specific Fields (Required for Agent ADRs)

### Agent Name

Model Routing Policy (Copilot CLI via `ai-review` composite action)

### Overlap Analysis

| Existing Agent | Capability Overlap | Overlap % | Differentiation |
|---|---:|---:|---|
| orchestrator | Routes work across capabilities | 35% | This routes *models* and sets conservative pass criteria |
| analyst | Produces structured assessments | 10% | This does not assess code; it governs execution defaults |

### Entry Criteria

| Scenario | Priority | Confidence |
|---|---:|---:|
| Security gate and PRD generation | P0 | Med |
| Summary-only PR context with code review prompts | P0 | High |
| Spec traceability and completeness with patch context | P0 | Med |
| PR quality gates with full diff | P1 | Med |
| Issue triage JSON classification | P1 | High |

### Explicit Limitations

1. If PR context is summary-only, line-level review is impossible. The policy forbids PASS in this case.
2. Model quality claims here are heuristic (no live vendor benchmarking in this environment). The routing is based on prompt shape and evidence type.

### Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| False PASS rate | Down materially vs baseline | Sampled audits: compare agent PASS vs post-merge findings |
| Post-merge critical escapes | No increase (ideally down) | Track incidents/regressions vs agent verdict history |
| “Insufficient evidence” surfaced | Up initially (expected) | Count WARN/REJECTED citing summary/partial diff |
| Developer time lost to reruns | Bounded | Track rerun frequency after evidence improvements |
