# AI Review Model Routing Policy

## Overview

This policy operationalizes [ADR-021: AI Review Model Routing Strategy](../architecture/ADR-021-model-routing-strategy.md) with compliance requirements, security hardening, and operational procedures.

**Policy objective**: Minimize false PASS in AI reviews by routing requests to specialized models based on prompt type and evidence availability.

**Effective date**: 2025-12-23
**Status**: Accepted

## Model Routing Matrix (REQUIRED)

All AI review workflows MUST use the model specified for each prompt type:

| Prompt Type | Primary Model | Fallback Model | Use Cases |
|-------------|---------------|----------------|-----------|
| **Strict JSON extraction** | `gpt-5-mini` | `claude-haiku-4.5` | Issue triage, label classification |
| **General review/synthesis** | `claude-sonnet-4.5` | `claude-opus-4.5` (escalation) | PR quality gate, spec validation |
| **Security gate** | `claude-opus-4.5` | None | Security reviews, threat analysis |
| **Code evidence/traceability** | `gpt-5.1-codex-max` | `gpt-5.1-codex` | QA, DevOps, spec completeness, test-to-code mapping |

### Model Selection Rules

1. **Workflows MUST pass `copilot-model` explicitly** per job (no silent defaults)
2. **If context is summary-only** (no diff content), route code-evidence prompts to `claude-opus-4.5` for risk review (NOT code review)
3. **If primary model unavailable**, use fallback model with "forbid PASS" policy (see Circuit Breaker section)

## Evidence Sufficiency Rules (REQUIRED)

### Summary-Mode PRs (Stat-Only Context)

**PASS is forbidden** when context is summary-only. Agents MUST output `WARN`, `CRITICAL_FAIL`, or `REJECTED` and explicitly request missing evidence.

**Risk review contract** (what agents CAN do):
- File pattern analysis (which files changed, rough scope)
- Metadata checks (PR title quality, label presence, description completeness)
- Risk flagging (large scope, sensitive paths like `.github/`, security-related files)

**Code review contract** (what agents CANNOT do):
- Line-level code review
- Specific bug detection
- Test coverage verification
- Implementation correctness checks

**Example WARN output**:

```markdown
## Verdict: WARN

**Reason**: PR context is summary-only; cannot perform line-level security review.

**Risk assessment based on available metadata**:
- PR touches 15 files including `.github/workflows/` (sensitive path)
- Changes span 2,847 lines (large scope increases risk)
- No secrets detected in file names

**Required action**: Rerun with smaller PR or provide full diff context.
```

### Partial-Diff PRs (Limited Context)

When context includes only partial diff (e.g., spec-file with 500-line head):

1. Mark confidence as limited
2. Prefer `WARN` over `PASS` unless EVERY required check can be backed by evidence in provided context
3. Note in output: "Limited context: only first 500 lines reviewed"

### Full-Diff PRs (Complete Context)

All models operate normally. PASS is permitted if all checks succeed.

## Governance Guardrails (REQUIRED)

### Explicit Model Parameter

**Policy**: Workflows MUST pass `copilot-model` explicitly per job.

**Compliance**:

```yaml
jobs:
  my-ai-review:
    steps:
      - uses: ./.github/actions/ai-review
        with:
          copilot-model: claude-sonnet-4.5  # REQUIRED per AI-REVIEW-MODEL-POLICY
          prompt-file: .github/prompts/my-prompt.md
```

**Guardrail**: Add validation step at start of each `ai-*.yml` workflow:

```yaml
- name: Validate Model Configuration
  if: inputs.copilot-model == ''
  run: |
    echo "::error::copilot-model not specified. See ADR-021 and AI-REVIEW-MODEL-POLICY for routing policy."
    exit 1
```

**Implementation status**: P0 prerequisite documented; implementation tracked separately.

### CONTEXT_MODE Header (REQUIRED)

**Policy**: All prompts MUST include: `CONTEXT_MODE: [full|summary|partial]`

**Validation**: The `ai-review` action MUST validate that CONTEXT_MODE matches actual context:

1. Compute token count or line count of context
2. If context exceeds `MAX_DIFF_LINES`, verify `CONTEXT_MODE=summary`
3. If context is full diff, verify `CONTEXT_MODE=full`
4. If mismatch detected, fail workflow with error: `CONTEXT_MODE validation failed: claimed {mode} but actual context is {actual_mode}`

**Rationale**: Prevents manipulation attacks where adversary crafts PR to trick mode detection.

**Prompt requirement**: Models must check CONTEXT_MODE header; PASS is forbidden if mode is not `full` (unless prompt explicitly defines partial-context behavior).

## Security Hardening (REQUIRED)

### Prompt Injection Safeguards

PR title and body are user-controlled and may contain adversarial prompts.

**Policy**: Before passing to model, sanitize using **whitelist approach**:

1. Parse PR title/body into structured schema (JSON with fields: title, body, max lengths)
2. Validate that title/body contain only:
   - Alphanumeric characters
   - Spaces
   - Common punctuation: `.`, `,`, `-`, `_`, `(`, `)`, `'`, `"`
3. Reject input that doesn't conform to schema or contains unexpected characters
4. Log rejected inputs for security monitoring

**Why whitelist**: Blacklist approaches (stripping patterns like `<|system|>`) are insufficient—attackers find new patterns. Whitelist/schema validation is security-hardened.

**Implementation**: Add schema validation function to `ai-review` composite action before model invocation.

### Confidence Scoring Rules

**Policy**:

- When model returns verdict, it SHOULD include confidence (0-100 scale)
- If confidence < 70% AND verdict is PASS, escalate to Opus for review
- Fallback models inherit "forbid PASS" when primary is unavailable

### Circuit Breaker (DoS Mitigation)

**Risk**: Attacker can DoS primary model (rate limiting, API outage), forcing all reviews into fallback mode where PASS is forbidden, blocking all merges indefinitely.

**Policy**: Circuit breaker prevents indefinite DoS while maintaining security posture:

1. If fallback model produces **5 consecutive non-PASS verdicts** due to "forbid PASS" rule (NOT due to actual code issues), escalate to **manual approval**
2. Manual approval requires:
   - Verification that primary model is unavailable
   - Human review of PR
   - Documented justification for merge
3. After circuit breaker triggers, alert oncall: `Primary model {model_name} unavailable for >5 PRs, fallback blocking all merges`

**Rationale**: Balances security (fallback forbids PASS) with availability (manual override prevents DoS).

## Escalation Criteria (REQUIRED)

Replace vague "high uncertainty" with operational definitions:

| Trigger | Condition | Action |
|---------|-----------|--------|
| **Low confidence** | Primary model outputs PASS with confidence < 70% | Escalate to `claude-opus-4.5` |
| **Borderline verdict** | Primary model explicitly flags uncertainty | Escalate to `claude-opus-4.5` |
| **Context concern** | Primary model notes evidence may be insufficient | Escalate to `claude-opus-4.5` |
| **Fallback active** | Primary model unavailable, using fallback | Forbid PASS |

**Cost bounds**: Escalation should not exceed 20% of PRs per month. If threshold exceeded, review escalation criteria.

## Aggregator Policy (REQUIRED)

When multiple agents review in parallel (e.g., QA + DevOps + Security):

**Policy**: "Max severity wins"

1. If ANY agent outputs `CRITICAL_FAIL` or `REJECTED`, the run fails
2. If ANY agent reports insufficient evidence, treat as non-PASS until rerun with evidence
3. Final verdict is the most conservative across all agents

**Implementation**:

1. Add aggregator step to `ai-pr-quality-gate.yml` that collects all agent verdicts and applies this policy
2. **Enforcement**: Configure branch protection rule requiring status check `AI Review Aggregator` to pass before merge
3. This prevents bypass—developers cannot manually merge without aggregator approval
4. Reference ADR-010 for integration with Quality Gates

**Security note**: Without branch protection enforcement, the aggregator is advisory, not enforced. The branch protection rule is REQUIRED for this policy to be effective.

## Fallback Chains (REQUIRED)

If primary model becomes unavailable, use fallback models:

| Primary Model | Fallback Chain |
|---------------|----------------|
| `gpt-5-mini` | `claude-haiku-4.5` |
| `gpt-5.1-codex-max` | `gpt-5.1-codex` → `claude-sonnet-4.5` |
| `claude-opus-4.5` | `claude-sonnet-4.5` (with WARN that escalation is degraded) |

**Fallback policy**: All fallback models inherit "forbid PASS" policy (see Circuit Breaker for DoS mitigation).

## Implementation Checklist

### Phase 1: Guardrail Implementation (P0)

- [ ] Add `copilot-model` validation step to all `ai-*.yml` workflows
- [ ] Update all workflows to pass `copilot-model` explicitly per job
- [ ] Add CONTEXT_MODE validation to `ai-review` action
- [ ] Add prompt injection schema validation to `ai-review` action

### Phase 2: Prompt Updates (P0)

- [ ] Add CONTEXT_MODE header to all prompts in `.github/prompts/`
- [ ] Add CONTEXT_MODE handling rules to all prompts (forbid PASS if not `full`)
- [ ] Add confidence scoring to prompt outputs

### Phase 3: Aggregator Implementation (P0)

- [ ] Add aggregator step to `ai-pr-quality-gate.yml`
- [ ] Configure branch protection rule requiring `AI Review Aggregator` status check
- [ ] Integrate with ADR-010 Quality Gates framework

### Phase 4: Evidence Improvement (Recommended)

- [ ] Update `ai-review` action to include bounded patch sample for large PRs (`gh pr diff | head -500`)
- [ ] Add `--stat` output to summary-mode context
- [ ] Validate N=500 balances context completeness with token limits

### Phase 5: Circuit Breaker (P0)

- [ ] Implement 5-consecutive-blocks detection in aggregator
- [ ] Add manual approval workflow triggered by circuit breaker
- [ ] Configure oncall alerts for circuit breaker triggers

## Exception Process

### Requesting Deviations from Policy

When policy compliance is not feasible:

1. **Document the reason** in workflow with comment:

   ```yaml
   # AI-REVIEW-MODEL-POLICY Exception: [specific reason]
   # Tracking: [link to issue or justification]
   ```

2. **Link to evidence**:
   - Model unavailability (vendor outage)
   - Prompt type not covered by routing matrix
   - Test results showing model performs poorly on this task type

3. **Create tracking issue** if temporary deviation

4. **Re-evaluate quarterly** to return to compliance when possible

### Approval Requirements

- **Model deviations**: Document justification; no pre-approval required (audit quarterly)
- **Evidence rule deviations** (allowing PASS without full context): **Requires architecture review** (violates core safety principle)
- **Aggregator bypass**: **Forbidden** (cannot be excepted)

## Monitoring and Success Metrics

### Metrics Tracked

| Metric | Target | Measurement | Baseline |
|--------|--------|-------------|----------|
| **False PASS rate (all causes)** | Monitor trend | Sampled audits: compare agent PASS vs post-merge findings | 15% (P0-1 complete) |
| **False PASS rate (evidence insufficiency)** | >= 50% reduction vs baseline | Count WARN/REJECTED on summary-mode PRs that later have issues | TBD (new metric) |
| **Post-merge critical escapes** | No increase (ideally down) | Track incidents/regressions vs agent verdict history | Current incident rate |
| **"Insufficient evidence" surfaced** | Up initially (expected) | Count WARN/REJECTED citing summary/partial diff | 0 (new metric) |
| **Escalation rate** | < 20% of PRs | Count escalations to Opus | N/A |
| **Cost increase** | < 25% vs baseline | Compare monthly Copilot costs | Current (36% reduction projected) |
| **Developer time lost to reruns** | < 5% of PRs require rerun | Track rerun frequency after evidence improvements | TBD |

### Review Cadence

- **Weekly**: Monitor escalation rate, cost delta
- **Bi-weekly**: Post-deployment audit (first 2 weeks after implementation)
  - Escalation rate vs target (<20%)
  - False PASS reduction vs baseline (target: >=50%)
  - Cost increase vs baseline (threshold: <25%)
  - Developer friction (WARN ignore rate)
- **Monthly**: Review false PASS trend, adjust routing if needed
- **Quarterly**: Review model quality, update routing matrix if vendor models improve/degrade

## Baseline Data (Prerequisites Completed)

### P0-1: False PASS Baseline (2025-12-23)

**Audit Date**: 2025-12-23
**Methodology**: Analyzed last 20 merged PRs with AI reviews (CodeRabbit/Copilot APPROVED). For each PR, checked GitHub for post-merge fix PRs within 7 days that touched the same files. Validation confirmed no post-merge fixes in 17 PRs; 3 PRs had documented fixes.

**Findings**:

| PR | Had AI APPROVED | Post-Merge Fix Required | Files Affected |
|----|-----------------|-------------------------|----------------|
| #226 | Yes (CodeRabbit) | Yes (#229) | .github/labeler.yml, label-pr.yml |
| #268 | Yes (CodeRabbit) | Yes (#296) | copilot-synthesis.yml, prompts |
| #249 | Yes (CodeRabbit) | Yes (#303) | pr-maintenance.yml |

**Baseline Rate**: 3/20 = **15% false PASS rate**

**Definition**: A PASS verdict followed by a post-merge fix in the same files within 7 days.

**Note**: 7-day window is a lower bound; delayed regressions (>7 days) are not captured. Actual false PASS rate may be higher.

#### Root Cause Analysis

For each of the 3 false PASS cases, we analyzed whether full diff context and correct model routing (per this policy) would have caught the issue:

- **PR #226 (Labeler workflow issues)**: Runtime workflow logic bug requiring execution to detect. Full diff would NOT reveal this—requires integration testing. **NOT addressed by this policy**.

- **PR #268 (Missing VERDICT token)**: Prompt quality issue—prompt should validate that VERDICT token is emitted. Full diff would NOT help—requires prompt improvement. **NOT addressed by this policy**.

- **PR #249 (Label format P1 vs priority:P1)**: Validation gap—prompt should check label naming conventions. Full diff would NOT help—requires validation rules in prompt. **NOT addressed by this policy**.

**Conclusion**: The 3 baseline cases were caused by prompt quality and validation gaps, NOT by evidence insufficiency or model mismatch. This policy does not directly address these 3 cases.

**Scope**: This policy targets **FUTURE false PASS cases caused by summary-only context**, which is a documented risk (MAX_DIFF_LINES threshold) even though it has not yet manifested in the measured baseline.

**Separated Metrics**:

- **Baseline false PASS rate (all causes)**: 15% (3/20 PRs, from P0-1)
- **Target false PASS rate (evidence insufficiency)**: TBD—new metric for large-PR summary-mode risk

This policy is **preventive** (stop future risks) not **remedial** (fix current baseline).

### P0-2: Model Availability Verification (2025-12-23)

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

**Fallback Chains** (confirmed per policy specification):

- `gpt-5-mini` unavailable → `claude-haiku-4.5`
- `gpt-5.1-codex-max` unavailable → `gpt-5.1-codex` → `claude-sonnet-4.5`
- `claude-opus-4.5` unavailable → `claude-sonnet-4.5` (with WARN)

### P1-4: Cost Impact Analysis (2025-12-23)

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

**Calculation**:

- Current usage: 74 PRs/month × 6 agents/PR = 444 Opus jobs/month (100% Opus baseline)
- Projected routing:
  - Issue triage (not PR-based): ~20 jobs/month → gpt-5-mini (Opus → Mini = -80% cost)
  - PR quality gate: 74 PRs × 6 agents = 444 jobs
    - 80% use Sonnet as primary, 20% escalate to Opus per escalation criteria
    - = 355 Sonnet + 89 Opus jobs
  - Security reviews: 74 PRs × 1 security agent = 74 Opus jobs (no change)
  - Spec validation: ~30 jobs/month → Codex (-30% vs Opus)

**Assuming** Sonnet = 50% of Opus cost, Codex = 70%, Mini = 20%:

- Current cost (normalized): 444 Opus + 20 Opus triage + 74 Opus security + 30 Opus spec = 568 Opus-equivalent units
- Projected cost: 355 Sonnet (=178 Opus-eq) + 89 Opus + 20 Mini (=4 Opus-eq) + 74 Opus + 30 Codex (=21 Opus-eq) = 366 Opus-equivalent units
- **Net impact**: 366/568 = 64% of baseline = **36% REDUCTION**

**Caveat**: Assumes escalation rate stays at 20%. If escalation exceeds 30%, cost savings diminish. Post-deployment audit will validate.

**Recommendation**: PROCEED. The routing policy is expected to REDUCE costs while improving review quality through model-task matching.

## Policy Scope

This is a **governance policy**, not an agent capability. It sets system-wide defaults that all agents and workflows must follow.

| Component | How Policy Applies |
|-----------|-------------------|
| orchestrator | Routes to appropriate models per this policy |
| ai-review action | Accepts `copilot-model` parameter per this policy |
| ai-*.yml workflows | Must specify `copilot-model` explicitly |
| .github/prompts/* | Must include CONTEXT_MODE handling |

### Explicit Limitations

1. If PR context is summary-only, line-level review is impossible. The policy forbids PASS in this case.
2. Model quality claims here are heuristic (no live vendor benchmarking in this environment). The routing is based on prompt shape and evidence type. Quarterly review recommended.
3. This policy does not address infrastructure failures or prompt quality issues (see Related Decisions).

## Related Policies and Decisions

- [ADR-021: AI Review Model Routing Strategy](../architecture/ADR-021-model-routing-strategy.md) - Architectural decision and rationale
- [ADR-010: Quality Gates](../architecture/ADR-010-quality-gates.md) - Aggregation framework
- [ADR-024: GitHub Actions Runner Selection](../architecture/ADR-024-github-actions-runner-selection.md) - Cost governance pattern
- [ADR-022: Architecture vs Governance Split Criteria](../architecture/ADR-022-architecture-governance-split-criteria.md) - Defines this split pattern
- [COST-GOVERNANCE.md](COST-GOVERNANCE.md) - Runner selection policy (similar enforcement pattern)
- Issue #164: Failure Categorization (infrastructure noise vs false PASS)

## References

- `.github/actions/ai-review/action.yml` - Context building implementation
- `.github/prompts/*` - Prompt catalog
- `.github/workflows/ai-*.yml` - AI review workflows
- [ADR-021 Debate Log](../critique/ADR-021-debate-log.md) - Multi-agent debate history
