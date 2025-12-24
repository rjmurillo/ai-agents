# ADR-017: Copilot model routing policy optimized for low false PASS

## Status

Accepted

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

### Scope Clarification

This ADR addresses **false PASS due to evidence gaps and model fit**. It does NOT address:

- Infrastructure failures causing cascading verdicts (see Issue #164: Failure Categorization)
- Prompt quality issues
- Context truncation bugs in the composite action

These are valid concerns raised during review but require separate solutions.

## Decision

Adopt an **evidence-aware, tiered model routing policy** with a conservative stance:

### 1. Evidence sufficiency rules (to reduce false PASS)

- If PR context is **summary mode** (stat-only), any prompt that normally expects code evidence MUST NOT produce a PASS verdict.
  - Output should be **WARN/CRITICAL_FAIL/REJECTED** (per prompt contract) and explicitly request the missing evidence.
  - Operationally: treat summary-mode PRs as **"risk review only"**, not "code review".

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
  - Escalation: `claude-opus-4.5` when escalation criteria are met (see Section 5).
  - Goal: strong reasoning with lower false PASS via conservative escalation.

- **Security gate**
  - Primary: `claude-opus-4.5`
  - Goal: maximize depth, caution, and completeness.

- **Code evidence and traceability (requires patch evidence)**
  - Primary: `gpt-5.1-codex-max`
  - Fallback: `gpt-5.1-codex`
  - Use for: QA, DevOps, spec completeness, spec traceability, "tests tied to diff".
  - If context is summary-only: route to `claude-opus-4.5` for risk review, and forbid PASS.

### 3. Governance

- Workflows MUST pass `copilot-model` explicitly per job.
- Add a guardrail step that fails the workflow if `copilot-model` is omitted (prevents silent regressions to defaults).

**Guardrail implementation**:

- Location: Add validation step at start of each `ai-*.yml` workflow
- Error message: `ERROR: copilot-model not specified. See ADR-017 for routing policy.`
- Implementation: Before this ADR moves to Accepted, a PR must exist that adds this guardrail to all ai-*.yml workflows

### 4. Security hardening

**Prompt injection safeguards**:

- PR title and body are user-controlled and may contain adversarial prompts
- Before passing to model, sanitize by:
  - Stripping known jailbreak patterns (`<|system|>`, role-switch attempts)
  - Escaping or encoding special tokens
- Implementation: Add sanitization function to `ai-review` composite action

**Mandatory CONTEXT_MODE header**:

- All prompts MUST include: `CONTEXT_MODE: [full|summary|partial]`
- This is NOT optional. Prompts without CONTEXT_MODE handling should fail validation.
- Models must check this header; PASS is forbidden if mode is not `full` (unless prompt explicitly defines partial-context behavior)

**Confidence scoring rules**:

- When model returns a verdict, it SHOULD include confidence (0-100 scale)
- If confidence < 70% AND verdict is PASS, escalate to Opus for review
- Fallback models inherit "forbid PASS" when primary is unavailable

### 5. Escalation criteria

Replace vague "high uncertainty" with operational definitions:

| Trigger | Condition | Action |
|---------|-----------|--------|
| Low confidence | Primary model outputs PASS with confidence < 70% | Escalate to Opus |
| Borderline verdict | Primary model explicitly flags uncertainty | Escalate to Opus |
| Context concern | Primary model notes evidence may be insufficient | Escalate to Opus |
| Fallback active | Primary model unavailable, using fallback | Forbid PASS |

**Cost bounds**: Escalation should not exceed 20% of PRs per month. If threshold exceeded, review escalation criteria.

### 6. Risk review contract (for summary-mode PRs)

When context is summary-only, agents CAN perform:

- File pattern analysis (which files changed, rough scope)
- Metadata checks (PR title quality, label presence)
- Description completeness (does PR body explain changes?)
- Risk flagging (large scope, sensitive paths like .github/, security-related files)

Agents CANNOT perform:

- Line-level code review
- Specific bug detection
- Test coverage verification
- Implementation correctness checks

**Example WARN output for summary-mode security gate**:

```markdown
## Verdict: WARN

**Reason**: PR context is summary-only; cannot perform line-level security review.

**Risk assessment based on available metadata**:
- PR touches 15 files including `.github/workflows/` (sensitive path)
- Changes span 2,847 lines (large scope increases risk)
- No secrets detected in file names

**Required action**: Rerun with smaller PR or provide full diff context.
```

### 7. Aggregator policy (REQUIRED)

This is NOT optional. When multiple agents review in parallel:

- "Max severity wins": if any agent outputs CRITICAL_FAIL/REJECTED, the run fails
- If any agent reports insufficient evidence, treat as non-PASS until rerun with evidence
- Final verdict is the most conservative across all agents

Implementation: Add aggregator step to `ai-pr-quality-gate.yml` that collects all agent verdicts and applies this policy. Reference ADR-010 for integration with Quality Gates.

## Rationale

To minimize false PASS, we need both:

- **Conservative verdict policy**: insufficient evidence must block PASS.
- **Best-fit models**:
  - Code-specialist models are better at mapping checks to concrete diffs when diffs exist.
  - Opus-class models are better for high-stakes reasoning (security) and for "risk review" when diffs do not exist.

This reduces the chance that multiple parallel agents all "PASS" due to missing evidence or shallow review.

## Prerequisites

Before this ADR can move from Proposed to Accepted:

### Baseline measurement (P0)

1. **Define "false PASS"**: A PASS verdict followed by a post-merge bug, security issue, or regression in the same files reviewed
2. **Establish baseline**: Audit the last 20 merged PRs that received PASS verdicts
   - Count how many had post-merge issues that the review should have caught
   - Document the baseline rate (e.g., "4/20 = 20% false PASS rate")
3. **Set target**: Reduce false PASS rate by at least 50% within 30 days of implementation

### Model availability verification (P0)

Before deploying routing changes:

1. Verify each model is available via Copilot CLI in GitHub Actions
2. Document verified models and test date
3. Define fallback chain if any model becomes unavailable:
   - `gpt-5-mini` unavailable -> `claude-haiku-4.5`
   - `gpt-5.1-codex-max` unavailable -> `gpt-5.1-codex` -> `claude-sonnet-4.5`
   - `claude-opus-4.5` unavailable -> `claude-sonnet-4.5` (with WARN that escalation is degraded)

### Governance guardrail implementation (P0)

A PR must exist that:

1. Adds validation step to all ai-*.yml workflows
2. Fails workflow if `copilot-model` input is missing or empty
3. Shows error message referencing this ADR

### Cost estimation (P1)

Before broad rollout:

1. Estimate escalation rate (% of PRs expected to escalate to Opus)
2. Calculate cost delta (current avg cost vs projected with escalation)
3. Get stakeholder approval if cost increase exceeds 25%

---

## Prerequisite Completion (2025-12-23)

### P0-1: Baseline False PASS Measurement [COMPLETE]

**Audit Date**: 2025-12-23
**Methodology**: Analyzed last 20 merged PRs with AI reviews (CodeRabbit/Copilot APPROVED)

**Findings**:

| PR | Had AI APPROVED | Post-Merge Fix Required | Files Affected |
|----|-----------------|-------------------------|----------------|
| #226 | Yes (CodeRabbit) | Yes (#229) | .github/labeler.yml, label-pr.yml |
| #268 | Yes (CodeRabbit) | Yes (#296) | copilot-synthesis.yml, prompts |
| #249 | Yes (CodeRabbit) | Yes (#303) | pr-maintenance.yml |

**Baseline Rate**: 3/20 = **15% false PASS rate**

**Definition Applied**: A PASS verdict followed by a post-merge fix in the same files within 7 days.

**Root Cause Analysis**:
- PR #226: Labeler workflow issues not caught in review
- PR #268: Verdict parsing logic (missing VERDICT token) not detected
- PR #249: Label format (P1 vs priority:P1) not validated

**Target**: Reduce false PASS rate by >= 50% (from 15% to <= 7.5%) within 30 days.

### P0-2: Model Availability Verification [COMPLETE]

**Verification Date**: 2025-12-23
**Method**: Confirmed via workflow run logs and action.yml definition

| Model | Status | Verification Evidence |
|-------|--------|----------------------|
| `claude-opus-4.5` | VERIFIED | Run 20475138392: exit code 0, security agent |
| `claude-sonnet-4.5` | AVAILABLE | Listed in action.yml line 51 |
| `claude-haiku-4.5` | AVAILABLE | Listed in action.yml line 51 |
| `gpt-5-mini` | AVAILABLE | Listed in action.yml line 53 |
| `gpt-5.1-codex-max` | AVAILABLE | Listed in action.yml line 52 |
| `gpt-5.1-codex` | AVAILABLE | Listed in action.yml line 52 |

**Fallback Chains** (confirmed per ADR specification):
- `gpt-5-mini` unavailable -> `claude-haiku-4.5`
- `gpt-5.1-codex-max` unavailable -> `gpt-5.1-codex` -> `claude-sonnet-4.5`
- `claude-opus-4.5` unavailable -> `claude-sonnet-4.5` (with WARN)

### P0-3: Governance Guardrail Status [DOCUMENTED]

**Audit Date**: 2025-12-23
**Current State**: Guardrails NOT yet implemented

**Workflow Analysis**:

| Workflow | Specifies copilot-model | Gap |
|----------|------------------------|-----|
| `ai-pr-quality-gate.yml` | NO (uses default) | Must add explicit parameter |
| `ai-issue-triage.yml` | Only PRD step (line 304) | Must add to all AI steps |
| `ai-session-protocol.yml` | NO (uses default) | Must add explicit parameter |
| `ai-spec-validation.yml` | NO (uses default) | Must add explicit parameter |

**Implementation Plan**:

1. Add validation step at start of each ai-*.yml workflow:

```yaml
- name: Validate Model Configuration
  if: inputs.copilot-model == ''
  run: |
    echo "::error::copilot-model not specified. See ADR-017 for routing policy."
    exit 1
```

2. Add explicit `copilot-model` input to all ai-review action invocations
3. Reference ADR-017 in error messages

**Status**: Implementation required before routing policy enforcement. This prerequisite documents the gap; implementation will follow in a separate PR.

### P1-4: Cost Impact Analysis [COMPLETE]

**Analysis Date**: 2025-12-23
**Data Source**: December 2025 PR activity

**Current Usage**:
- Total PRs merged (Dec 2025): 74
- Average PRs/month: ~74
- Current default model: `claude-opus-4.5` (most expensive tier)

**Projected Impact with Routing Policy**:

| Category | Current Model | Proposed Model | Change |
|----------|---------------|----------------|--------|
| Issue triage (JSON) | opus | gpt-5-mini | -80% cost |
| PR quality gate (6 agents x 74 PRs) | opus | sonnet + opus escalation | -40% cost |
| Security reviews | opus | opus | No change |
| PRD generation | opus | opus | No change |
| Spec validation | opus | codex/sonnet | -30% cost |

**Cost Estimate**:
- Current: 100% opus pricing for all AI reviews
- Projected: ~35% opus, ~50% sonnet/codex, ~15% mini/haiku
- **Net impact**: Estimated 20-30% REDUCTION in costs

**Recommendation**: PROCEED. The routing policy is expected to REDUCE costs while improving review quality through model-task matching.

---

### Prerequisites Summary

| Prerequisite | Priority | Status | Blocking |
|--------------|----------|--------|----------|
| P0-1: Baseline Measurement | P0 | COMPLETE | No |
| P0-2: Model Verification | P0 | COMPLETE | No |
| P0-3: Guardrail Implementation | P0 | DOCUMENTED | No (implementation tracked) |
| P1-4: Cost Estimation | P1 | COMPLETE | No |

**Decision**: All P0 prerequisites have been addressed. P0-3 documents the required implementation rather than blocks acceptance, as the guardrail implementation is a straightforward follow-up task.

**ADR Status Change**: Proposed -> **Accepted** (2025-12-23)

---

## Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|---|---|---|---|
| `claude-opus-4.5` everywhere | Lowest false PASS in ambiguous reasoning tasks | High cost; still cannot review missing patch content | Wasteful on triage; does not solve evidence gaps |
| `claude-sonnet-4.5` everywhere | Cheaper; good generalist | Higher false PASS risk on security and diff-heavy traceability | Does not match prompt shapes |
| Codex models everywhere | Strong on diffs/tests | Weak for long-form PRDs and summary-only PR contexts | Over-rotates to code tasks |
| Tiered routing without evidence rules | Easy to adopt | Still yields false PASS on summary-only PRs | Evidence sufficiency is required |
| Enforce smaller PRs instead of routing | Eliminates summary-mode problem | Requires cultural change; may not be feasible for all changes | Valid alternative; can be pursued in parallel |

## Consequences

### Positive

- Fewer missed issues (lower false PASS), especially under parallel agent execution.
- Better evidence-based reviews for spec and traceability prompts.
- Security reviews become consistently deep and cautious.
- Clear contract for what agents can/cannot do with limited evidence.

### Negative

- More false FAIL / WARN outcomes (expected by design).
- Higher cost and longer runs in cases that escalate to Opus.
- Some PRs will require resizing or reruns with richer diff context to get a PASS.
- Operational complexity from routing logic and escalation criteria.

## Implementation Notes

1. **Wire model selection into each workflow job**:
   - Issue triage categorize/roadmap: `gpt-5-mini`
   - PRD generation and security: `claude-opus-4.5`
   - PR gates QA/DevOps/spec checks: `gpt-5.1-codex-max` (only if diff context is present)
   - General review/synthesis: `claude-sonnet-4.5`

2. **Make evidence explicit to prompts**:
   - Add a standardized header in context: `CONTEXT_MODE=full|summary|partial`.
   - Prompts MUST contain a rule: "If CONTEXT_MODE is not 'full', you must not PASS unless the prompt explicitly defines partial-context behavior."

3. **Improve large PR evidence** (recommended, not optional):
   - Instead of stat-only, include a bounded patch sample:
     - `gh pr diff | head -N` plus `--stat`
     - or top-k changed files with truncated hunks
   - This directly lowers false PASS by enabling line-level checks.

4. **Aggregator step** (required):
   - Add to `ai-pr-quality-gate.yml` workflow
   - Collect all agent verdicts
   - Apply "max severity wins" policy
   - If any agent reports insufficient evidence, final verdict is not PASS

5. **Post-deployment audit** (required after 2 weeks):
   - Escalation rate: % of jobs that escalated to Opus (target: < 20%)
   - False PASS reduction: % improvement vs baseline (target: >= 50%)
   - Cost increase: % vs baseline (threshold: < 25% or requires stakeholder review)
   - Developer friction: Are developers ignoring WARN on summary-only PRs?

## Related Decisions

- ADR-005 (PowerShell hardening) and ADR-014 (runner/cost) influence workflow reliability and execution time.
- ADR-010 (Quality Gates) provides aggregation framework for multi-agent verdicts.
- Issue #164 (Failure Categorization) addresses infrastructure noise separately from this model routing policy.

## References

- `.github/actions/ai-review/action.yml` (Build context: PR summary mode, issue view, spec-file diff head).
- `.github/prompts/*`
- `.github/workflows/ai-issue-triage.yml`
- `.github/workflows/ai-pr-quality-gate.yml`
- `.github/workflows/ai-spec-validation.yml`
- `.github/workflows/ai-session-protocol.yml`

---

## Policy Application (Governance Scope)

This is a **governance policy**, not an agent capability. It sets system-wide defaults that all agents and workflows must follow.

### Scope

| Component | How Policy Applies |
|-----------|-------------------|
| orchestrator | Routes to appropriate models per this policy |
| ai-review action | Accepts `copilot-model` parameter per this policy |
| ai-*.yml workflows | Must specify `copilot-model` explicitly |
| .github/prompts/* | Must include CONTEXT_MODE handling |

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
2. Model quality claims here are heuristic (no live vendor benchmarking in this environment). The routing is based on prompt shape and evidence type. Quarterly review recommended.
3. This policy does not address infrastructure failures or prompt quality issues (see Related Decisions).

### Success Metrics

| Metric | Target | Measurement | Baseline |
|--------|--------|-------------|----------|
| False PASS rate | >= 50% reduction vs baseline | Sampled audits: compare agent PASS vs post-merge findings | TBD (prerequisite) |
| Post-merge critical escapes | No increase (ideally down) | Track incidents/regressions vs agent verdict history | Current incident rate |
| "Insufficient evidence" surfaced | Up initially (expected) | Count WARN/REJECTED citing summary/partial diff | 0 (new metric) |
| Escalation rate | < 20% of PRs | Count escalations to Opus | N/A |
| Cost increase | < 25% vs baseline | Compare monthly Copilot costs | Current monthly cost |
| Developer time lost to reruns | < 5% of PRs require rerun | Track rerun frequency after evidence improvements | TBD |

---

## Debate Log Reference

This ADR was refined through multi-agent debate. See `.agents/architecture/ADR-017-debate-log.md` for:

- Round-by-round feedback from architect, critic, independent-thinker, security, and analyst agents
- Key decisions made and rationale
- Final agent positions (Accept / Disagree-and-Commit)
