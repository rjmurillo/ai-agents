# ADR-017: AI Review Model Routing Strategy

## Status

Accepted

## Date

2025-12-23

## Context

This repo invokes GitHub Copilot CLI via the composite action `.github/actions/ai-review/action.yml` for automated code review, issue triage, PRD generation, and spec validation.

### The Problem

The action builds context in ways that materially affect review quality:

- **Large PRs**: When diff exceeds `MAX_DIFF_LINES`, switches to **summary mode** (stat-only, no patch content)
- **Prompt diversity**: JSON extraction, long-form writing, diff-heavy code review, evidence traceability
- **Parallel execution**: Multiple agents review simultaneously; false PASS in one agent compounds

**Decision driver**: Optimize for **lowest false PASS** (missing issues that should be caught). Missed issues compound when agents run in parallel. This is more important than cost and latency.

### Core Tensions

1. **Evidence availability**: When PR context is summary-only, no model can do line-level code review
2. **Model specialization**: Code-evidence prompts need code-specialist models; security/writing prompts need deep reasoning models
3. **Cost vs quality**: Most capable models are expensive; need strategic routing to balance cost and quality

### Scope

This ADR addresses **false PASS due to evidence gaps and model fit**. It does NOT address:

- Infrastructure failures causing cascading verdicts (see Issue #164: Failure Categorization)
- Prompt quality issues (missing validation rules)
- Context truncation bugs in the composite action

These require separate solutions tracked elsewhere.

## Decision

Adopt an **evidence-aware, tiered model routing strategy** that routes AI review requests to specialized models based on:

1. **Prompt type** (JSON extraction, code review, security gate, writing/synthesis)
2. **Evidence availability** (full diff, partial diff, summary-only)
3. **Escalation triggers** (low confidence, borderline verdicts, fallback mode)

### Model Routing Strategy

**Strict JSON extraction** (issue triage):
- Primary: `gpt-5-mini`
- Fallback: `claude-haiku-4.5`
- Rationale: Fast, cost-effective, strict schema adherence

**General review and synthesis** (non-security):
- Primary: `claude-sonnet-4.5`
- Escalation: `claude-opus-4.5` (when confidence <70% or borderline verdict)
- Rationale: Strong reasoning, conservative escalation reduces false PASS

**Security gate**:
- Primary: `claude-opus-4.5`
- Rationale: Maximize depth, caution, completeness for security decisions

**Code evidence and traceability** (QA, DevOps, spec validation):
- Primary: `gpt-5.1-codex-max`
- Fallback: `gpt-5.1-codex`
- Rationale: Code-specialist models excel at diff analysis and test-to-code mapping

### Evidence Sufficiency Principle

**Conservative stance**: Insufficient evidence forbids PASS

- **Summary-mode PRs**: Treat as "risk review only" (file patterns, scope analysis), NOT code review (line-level bugs)
- **Partial diff**: Mark confidence as limited; prefer WARN over PASS unless all checks have evidence
- **Full diff**: All models operate normally

This prevents false PASS from missing evidence.

### Cost Impact

**Projected routing distribution**:
- 35% Opus (security, escalations)
- 50% Sonnet/Codex (general review, code analysis)
- 15% Mini/Haiku (JSON extraction)

**Net impact**: 36% cost reduction vs 100% Opus baseline (568 → 366 Opus-equivalent units/month)

Assumes 20% escalation rate; validated post-deployment.

## Rationale

### Why Tiered Routing?

**Model specialization matters**:
- Code-specialist models (Codex) map checks to concrete diffs more effectively when diffs exist
- Deep reasoning models (Opus) excel at security review and "risk review" when diffs don't exist
- Fast extraction models (Mini) handle JSON schema adherence efficiently

**Evidence-awareness prevents false PASS**:
- Without evidence sufficiency rules, models hallucinate code quality from incomplete context
- Conservative stance (forbid PASS without evidence) shifts false PASS to false WARN (acceptable trade-off)

**Cost optimization**:
- Strategic routing to cheaper models where appropriate (JSON extraction, general review)
- Reserve expensive models for high-stakes decisions (security) and escalations

### Why Not Alternatives?

**Single model everywhere**: Wasteful on simple tasks (triage), doesn't solve evidence gaps
**Evidence rules without routing**: Model mismatch still causes false PASS on code-heavy tasks
**Routing without evidence rules**: Still yields false PASS on summary-only PRs

All three components (routing + evidence rules + escalation) are required.

## Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|---|---|---|---|
| `claude-opus-4.5` everywhere | Lowest false PASS in ambiguous reasoning | High cost; still can't review missing patch | Wasteful on triage; doesn't solve evidence gaps |
| `claude-sonnet-4.5` everywhere | Cheaper; good generalist | Higher false PASS on security and traceability | Doesn't match prompt shapes |
| Codex models everywhere | Strong on diffs/tests | Weak for long-form PRDs and summary-only PRs | Over-rotates to code tasks |
| Routing without evidence rules | Easy to adopt | Still yields false PASS on summary-only PRs | Evidence sufficiency required |
| Enforce smaller PRs instead | Eliminates summary-mode problem | Cultural change; may not be feasible | Valid alternative; pursue in parallel |

## Consequences

### Positive

1. **Lower false PASS** (evidence insufficiency): Models won't PASS without sufficient evidence
2. **Better model-task matching**: Code specialists on code tasks, deep reasoning on security/synthesis
3. **Cost reduction**: 36% savings via strategic routing (vs all-Opus baseline)
4. **Security depth**: Consistent Opus-level review for security gates
5. **Clear evidence contract**: Agents know what they can/cannot verify with limited context

### Negative

1. **More false WARN**: By design—conservative stance shifts false PASS to false WARN
2. **Higher cost for escalations**: Escalation to Opus increases cost/latency for borderline cases
3. **PR resizing pressure**: Some PRs may require resizing to get PASS verdict
4. **Operational complexity**: Routing logic, escalation triggers, fallback handling add complexity
5. **Model availability dependency**: Relies on vendor model availability and stability

### Neutral

1. **Monitoring required**: Escalation rate, cost delta, false PASS trend must be tracked
2. **Policy evolution**: Routing matrix and escalation criteria may need tuning post-deployment

## Implementation

See [AI Review Model Policy](../../governance/AI-REVIEW-MODEL-POLICY.md) for:

- Model routing matrix (detailed mappings)
- Evidence sufficiency rules (CONTEXT_MODE validation)
- Governance guardrails (explicit copilot-model requirement)
- Security hardening (prompt injection, circuit breaker)
- Escalation criteria (operational triggers)
- Aggregator policy (max severity wins)
- Monitoring and success metrics

## Related Decisions

- ADR-010: Quality Gates (provides aggregation framework)
- ADR-014: GitHub Actions Runner Selection (cost governance pattern)
- ADR-018: Architecture vs Governance Split Criteria (defines this split pattern)
- Issue #164: Failure Categorization (infrastructure noise vs false PASS)

## References

- `.github/actions/ai-review/action.yml` (context building implementation)
- `.github/prompts/*` (prompt catalog)
- `.github/workflows/ai-*.yml` (AI review workflows)
- [AI Review Model Policy](../../governance/AI-REVIEW-MODEL-POLICY.md) (operational enforcement)

---

## Debate History

This ADR was refined through multi-agent debate (Sessions 86-90). See [ADR-017-debate-log.md](ADR-017-debate-log.md) for:

- 3 rounds of review (architect, critic, independent-thinker, security, analyst, high-level-advisor)
- Key decisions: evidence sufficiency principle, security hardening, cost calculation
- Final consensus: 5 Accept + 1 Disagree-and-Commit
- Independent-thinker dissent: Skeptical evidence insufficiency is primary lever, but supports execution for validation

---

## Status Transition History

- **2025-12-23 (Sessions 86-88)**: Multi-agent debate achieved consensus
- **2025-12-23 (Session 89)**: Prerequisites completed (baseline, model verification, cost estimation)
- **2025-12-23 (Session 90)**: Round 3 post-prerequisites review, root cause analysis added
- **2025-12-23 (Session 90)**: Split into ADR + Governance per ADR-018 recommendation
- **2025-12-23**: Status changed to **Accepted**
