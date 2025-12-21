---
number: 153
title: "Add pre-invocation infrastructure health check for agent workflows"
state: OPEN
created_at: 12/20/2025 10:03:15
author: rjmurillo-bot
labels: ["enhancement", "area-workflows", "priority:P1", "automation"]
assignees: []
milestone: null
url: https://github.com/rjmurillo/ai-agents/issues/153
---

# Add pre-invocation infrastructure health check for agent workflows

## Problem

Agent workflows can fail due to infrastructure issues (Copilot CLI access, MCP server availability), but failures are indistinguishable from code quality findings. This leads to wasted debugging effort and false PR blocks.

**Example**: Session 38 - Architect agent failed with exit code 1 due to Copilot CLI access issue. No pre-invocation check was performed, resulting in effort spent debugging code when the issue was environment configuration.

## Current Behavior

- Agents are invoked without infrastructure validation
- Exit code 1 + no output → unclear if environment or quality issue
- PR workflows may fail due to environment, not code

## Proposed Solution

Add GitHub Actions composite action for infrastructure health checks:

1. **Pre-invocation checks**:
   - `command -v gh` (GitHub CLI availability)
   - `gh copilot --version` (Copilot CLI access)
   - MCP server connectivity (if applicable)
   - API token validity

2. **Diagnostic output**:
   - Log which checks passed/failed
   - Differentiate "agent skipped" from "agent found issues"
   - Store check results as workflow output

3. **Graceful degradation**:
   - If infrastructure unavailable → skip agent, don't fail workflow
   - Log warning with actionable fix (e.g., "Configure COPILOT_GITHUB_TOKEN")
   - Continue workflow without blocking PR

## Implementation Sketch

\`\`\`yaml
# .github/actions/check-agent-infrastructure/action.yml
name: Check Agent Infrastructure
description: Validate infrastructure before invoking agents
outputs:
  copilot-available:
    description: Whether Copilot CLI is available
    value: \${{ steps.check.outputs.copilot-available }}
  github-cli-available:
    description: Whether GitHub CLI is available
    value: \${{ steps.check.outputs.github-cli-available }}

runs:
  using: composite
  steps:
    - name: Check Infrastructure
      id: check
      shell: bash
      run: |
        COPILOT_AVAILABLE=false
        GITHUB_CLI_AVAILABLE=false
        
        if command -v gh >/dev/null 2>&1; then
          GITHUB_CLI_AVAILABLE=true
          echo "::notice::GitHub CLI available"
        else
          echo "::warning::GitHub CLI not available"
        fi
        
        if gh copilot --version >/dev/null 2>&1; then
          COPILOT_AVAILABLE=true
          echo "::notice::Copilot CLI authenticated"
        else
          echo "::warning::Copilot CLI not available or not authenticated"
        fi
        
        echo "copilot-available=\$COPILOT_AVAILABLE" >> \$GITHUB_OUTPUT
        echo "github-cli-available=\$GITHUB_CLI_AVAILABLE" >> \$GITHUB_OUTPUT
\`\`\`

**Usage in workflow**:
\`\`\`yaml
- name: Check Infrastructure
  id: infra
  uses: ./.github/actions/check-agent-infrastructure

- name: Invoke Architect
  if: steps.infra.outputs.copilot-available == 'true'
  run: gh copilot analyze ...
  
- name: Skip Notice
  if: steps.infra.outputs.copilot-available != 'true'
  run: echo "::notice::Skipping architect review - Copilot CLI not available"
\`\`\`

## Expected Benefits

- **Reduced false failures**: Distinguish environment errors from quality issues
- **Faster diagnosis**: Clear indication of infrastructure problems
- **Better DX**: Actionable error messages (not generic exit code 1)
- **Non-blocking workflows**: Continue PR validation even if one agent unavailable

## Related

- Session 38 retrospective: `.agents/retrospective/2025-12-20-session-38-comprehensive.md`
- Skill-Agent-Infra-001: Infrastructure health check skill
- Skill-Agent-Diagnosis-001: Error type distinction skill
- PR #121: Example where architect failed due to Copilot CLI

## Labels

- `enhancement` - New feature
- `area-workflows` - GitHub Actions
- `priority:P1` - High priority (prevents debugging waste)
- `automation` - Build/CI automation

---

## Comments

### Comment by @coderabbitai on 12/20/2025 10:05:24

<!-- This is an auto-generated issue plan by CodeRabbit -->


### 📝 CodeRabbit Plan Mode
Generate an implementation plan and prompts that you can use with your favorite coding agent.

- [ ] <!-- {"checkboxId": "8d4f2b9c-3e1a-4f7c-a9b2-d5e8f1c4a7b9"} --> Create Plan

<details>
<summary>Examples</summary>

- [Example 1](https://github.com/coderabbitai/git-worktree-runner/issues/29#issuecomment-3589134556)
- [Example 2](https://github.com/coderabbitai/git-worktree-runner/issues/12#issuecomment-3606665167)

</details>

---

<details>
<summary><b>🔗 Similar Issues</b></summary>

**Related Issues**
- https://github.com/rjmurillo/ai-agents/issues/42
- https://github.com/rjmurillo/ai-agents/issues/116
- https://github.com/rjmurillo/ai-agents/issues/9
- https://github.com/rjmurillo/ai-agents/issues/152
</details>
<details>
<summary><b>🔗 Related PRs</b></summary>

rjmurillo/vs-code-agents#57 - feat: Phase 1 CWE-78 Incident Remediation (Issues #16, #17, #18) [closed]
rjmurillo/ai-agents#60 - feat: AI-powered GitHub Actions workflows with security-hardened PowerShell implementation [merged]
rjmurillo/ai-agents#76 - fix(workflows): strengthen AI review rigor and enable PR gating [merged]
rjmurillo/ai-agents#100 - fix(ci): ensure Pester Tests workflow satisfies required checks for all PRs [closed]
rjmurillo/ai-agents#109 - fix(ci): add checkout step to skip-tests job in Pester workflow [closed]
</details>
<details>
<summary><b>👤 Suggested Assignees</b></summary>

- [rjmurillo-bot](https://github.com/rjmurillo-bot)
- [rjmurillo](https://github.com/rjmurillo)
</details>


---
<details>
<summary> 🧪 Issue enrichment is currently in open beta.</summary>


You can configure auto-planning by selecting labels in the issue_enrichment configuration.

To disable automatic issue enrichment, add the following to your `.coderabbit.yaml`:
```yaml
issue_enrichment:
  auto_enrich:
    enabled: false
```
</details>

💬 Have feedback or questions? Drop into our [discord](https://discord.gg/coderabbit) or [schedule a call](https://calendly.com/parth-coderabbit/issues-feedback)!

### Comment by @github-actions on 12/20/2025 10:06:49

<!-- AI-PRD-GENERATION -->

## 📋 Product Requirements Document

> [!IMPORTANT]
> This PRD was automatically generated based on issue triage escalation.
> **Complexity Score**: 7/12 ()
> **Escalation Criteria**: feature_request, multi_phase_work, architectural_impact

<details>
<summary>📖 About this PRD</summary>

This PRD was generated by the **Explainer Agent** after the issue was flagged
for detailed analysis. The document is designed to be self-contained - it can
be passed to a separate AI agent instance for implementation without additional
context.

**PRD Depth Levels**:
- **Standard** (4-6): Brief analysis, clear requirements
- **Detailed** (7-9): Research section, blocking questions
- **Comprehensive** (10-12): Phased implementation, risk analysis

</details>

---

Now I have comprehensive context. Let me check for any related retrospectives or session files.

I have enough context. Now I will create the PRD for this issue.

The `.agents/planning/` directory requires write permissions. Let me output the PRD content directly since file creation failed:

---

# PRD: Pre-Invocation Infrastructure Health Check for Agent Workflows

## Executive Summary

Agent workflows fail silently when infrastructure prerequisites are missing (Copilot CLI access, GitHub CLI availability). Exit code 1 with no output is indistinguishable from legitimate quality findings, causing wasted debugging effort and false PR blocks.

| Scope | Status | Blocker |
|-------|--------|---------|
| Composite action creation | :green_circle: READY | None |
| Integration with ai-review action | :green_circle: READY | None |
| Workflow-level integration | :green_circle: READY | None |
| Graceful degradation logic | :green_circle: READY | None |

**Verdict: READY** - All implementation paths are clear with existing patterns to follow.

## Problem Statement

### Current State

| Component | Behavior | Gap |
|-----------|----------|-----|
| `ai-review` action | Installs Copilot CLI, invokes it | No pre-check for infrastructure availability |
| Copilot CLI failure | Exit code 1, empty output | Indistinguishable from quality findings |
| Diagnostic mode | Available via `enable-diagnostics: true` | Disabled by default, costs money |
| Error messaging | Inline stderr analysis in invoke step | Not actionable, buried in logs |

### Gap Analysis

1. **No pre-invocation validation**: Agents are invoked without checking prerequisites
2. **Ambiguous failure modes**: Exit code 1 with no output could mean infrastructure unavailable, network timeout, or legitimate code quality issue
3. **Blocking behavior**: Workflow fails on infrastructure issues, blocking PRs unnecessarily
4. **Cost barrier**: Diagnostic mode runs a test prompt, incurring API costs

### User Impact

| User | Impact |
|------|--------|
| PR authors | PRs blocked by environment issues, not code quality |
| Reviewers | Time wasted investigating false failures |
| Operators | Debugging effort spent on infrastructure, not code |

## Research Findings

### Source 1: Existing ai-review Action (CONFIRMED)

Location: `.github/actions/ai-review/action.yml`

Diagnostic checks exist (lines 157-343) but are opt-in via `enable-diagnostics: true` and expensive (runs test prompt).

### Source 2: Failure Analysis (CONFIRMED)

Location: `.github/actions/ai-review/action.yml` lines 539-569

Post-hoc analysis runs after failure, not before invocation.

### Source 3: Copilot CLI Requirements (CONFIRMED)

Requirements: `gh` CLI installed, valid PAT with Copilot access, network access to GitHub API.

## Proposed Solution

### Phase 1: Create Composite Action (Effort: S)

Create `.github/actions/check-agent-infrastructure/action.yml` with GitHub CLI check, Copilot CLI version check (no API call), and token validity check.

### Phase 2: Integrate with ai-review Action (Effort: S)

Add optional pre-check step, expose infrastructure status as output.

### Phase 3: Workflow Integration (Effort: S)

Update `ai-pr-quality-gate.yml` with health check job, implement graceful degradation.

## Functional Requirements

### FR-1: Infrastructure Detection (P0)

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| FR-1.1 | Detect GitHub CLI availability | `command -v gh` returns true/false |
| FR-1.2 | Detect Copilot CLI availability | `copilot --version` succeeds without API call |
| FR-1.3 | Validate token format | Token validated via `gh api user` |
| FR-1.4 | Check GitHub API access | `gh api user` returns valid JSON |

### FR-2: Structured Outputs (P0)

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| FR-2.1 | Output `github-cli-available` | `true` or `false` string |
| FR-2.2 | Output `copilot-cli-available` | `true` or `false` string |
| FR-2.3 | Output `infrastructure-ready` | Composite of all checks |
| FR-2.4 | Output `failure-reason` | Human-readable explanation |

### FR-3: Graceful Degradation (P1)

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| FR-3.1 | Workflows can conditionally skip agent invocation | `if: steps.infra.outputs.infrastructure-ready == 'true'` |
| FR-3.2 | Skipped agents produce notice, not error | `::notice::` annotation |
| FR-3.3 | Workflow continues after skip | PR not blocked |

## Technical Design

### Action Definition

**File**: `.github/actions/check-agent-infrastructure/action.yml`

```yaml
name: 'Check Agent Infrastructure'
description: 'Validate infrastructure prerequisites before invoking AI agents'

inputs:
  bot-pat:
    description: 'GitHub PAT for API access validation'
    required: true
  require-copilot:
    description: 'Whether Copilot CLI is required (vs optional)'
    required: false
    default: 'true'

outputs:
  github-cli-available:
    description: 'Whether GitHub CLI is installed'
    value: ${{ steps.check.outputs.github_cli_available }}
  copilot-cli-available:
    description: 'Whether Copilot CLI is installed'
    value: ${{ steps.check.outputs.copilot_cli_available }}
  token-valid:
    description: 'Whether PAT is valid for GitHub API'
    value: ${{ steps.check.outputs.token_valid }}
  infrastructure-ready:
    description: 'Whether all required infrastructure is available'
    value: ${{ steps.check.outputs.infrastructure_ready }}
  failure-reason:
    description: 'Reason for failure (if any)'
    value: ${{ steps.check.outputs.failure_reason }}

runs:
  using: 'composite'
  steps:
    - name: Check Infrastructure
      id: check
      shell: bash
      env:
        GH_TOKEN: ${{ inputs.bot-pat }}
        REQUIRE_COPILOT: ${{ inputs.require-copilot }}
      run: |
        GITHUB_CLI_AVAILABLE=false
        COPILOT_CLI_AVAILABLE=false
        TOKEN_VALID=false
        INFRASTRUCTURE_READY=false
        FAILURE_REASON=""
        
        # Check 1: GitHub CLI
        if command -v gh >/dev/null 2>&1; then
          GITHUB_CLI_AVAILABLE=true
          echo "::notice::GitHub CLI available: $(gh --version | head -1)"
        else
          FAILURE_REASON="GitHub CLI not installed"
          echo "::warning::GitHub CLI not available"
        fi
        
        # Check 2: Token validity
        if [ "$GITHUB_CLI_AVAILABLE" = "true" ]; then
          if gh api user -q '.login' >/dev/null 2>&1; then
            TOKEN_VALID=true
            echo "::notice::Authenticated as: $(gh api user -q '.login')"
          else
            FAILURE_REASON="GitHub API token invalid or expired"
            echo "::warning::GitHub API authentication failed"
          fi
        fi
        
        # Check 3: Copilot CLI
        if command -v copilot >/dev/null 2>&1; then
          if copilot --version >/dev/null 2>&1; then
            COPILOT_CLI_AVAILABLE=true
            echo "::notice::Copilot CLI available"
          fi
        else
          if [ "$REQUIRE_COPILOT" = "true" ]; then
            FAILURE_REASON="${FAILURE_REASON:+$FAILURE_REASON; }Copilot CLI not installed"
          fi
          echo "::warning::Copilot CLI not available"
        fi
        
        # Determine readiness
        if [ "$GITHUB_CLI_AVAILABLE" = "true" ] && [ "$TOKEN_VALID" = "true" ]; then
          if [ "$REQUIRE_COPILOT" = "true" ]; then
            [ "$COPILOT_CLI_AVAILABLE" = "true" ] && INFRASTRUCTURE_READY=true
          else
            INFRASTRUCTURE_READY=true
          fi
        fi
        
        echo "github_cli_available=$GITHUB_CLI_AVAILABLE" >> $GITHUB_OUTPUT
        echo "copilot_cli_available=$COPILOT_CLI_AVAILABLE" >> $GITHUB_OUTPUT
        echo "token_valid=$TOKEN_VALID" >> $GITHUB_OUTPUT
        echo "infrastructure_ready=$INFRASTRUCTURE_READY" >> $GITHUB_OUTPUT
        echo "failure_reason=$FAILURE_REASON" >> $GITHUB_OUTPUT
```

### Workflow Integration

Add `check-infrastructure` job before `review` matrix in `ai-pr-quality-gate.yml`:

```yaml
check-infrastructure:
  name: Check Infrastructure
  runs-on: ubuntu-latest
  needs: check-changes
  if: needs.check-changes.outputs.should-run == 'true'
  outputs:
    infrastructure-ready: ${{ steps.infra.outputs.infrastructure-ready }}
  steps:
    - uses: actions/checkout@v4
    - run: npm install -g @github/copilot
    - id: infra
      uses: ./.github/actions/check-agent-infrastructure
      with:
        bot-pat: ${{ secrets.BOT_PAT }}

review:
  needs: [check-changes, check-infrastructure]
  if: |
    needs.check-changes.outputs.should-run == 'true' &&
    needs.check-infrastructure.outputs.infrastructure-ready == 'true'
```

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Check passes but Copilot API unavailable | Medium | Medium | Document CLI check != API access |
| Added workflow complexity | Low | Low | Single job, minimal overhead |

## Success Metrics

| Metric | Target |
|--------|--------|
| Infrastructure failures detected pre-invocation | 100% |
| False PR blocks from infrastructure issues | 0 |

## Blocking Questions

None. All implementation paths are clear.

---

PRD complete. File creation failed due to permissions. Recommend copying this content to `.agents/planning/PRD-agent-infrastructure-healthcheck.md`.

---

<sub>📋 Generated by [AI PRD Generation](https://github.com/rjmurillo/ai-agents) · [View Workflow](https://github.com/rjmurillo/ai-agents/actions/runs/20392780607)</sub>



### Comment by @github-actions on 12/20/2025 10:06:51

<!-- AI-ISSUE-TRIAGE -->

## AI Triage Summary

> [!NOTE]
> This issue has been automatically triaged by AI agents

<details>
<summary>What is AI Triage?</summary>

This issue was analyzed by AI agents:

- **Analyst Agent**: Categorizes the issue and suggests appropriate labels
- **Roadmap Agent**: Aligns the issue with project milestones and priorities
- **Explainer Agent** (if escalated): Generates comprehensive PRD

</details>

### Triage Results

| Property | Value |
|:---------|:------|
| **Category** | `enhancement` |
| **Labels** | enhancement area-workflows area-infrastructure |
|  **Priority** | `P1` |
| **Milestone** | v1.1 |
| **PRD Escalation** | Generated (see below) |

<details>
<summary>Categorization Analysis</summary>

```json
```json
{
  "labels": ["enhancement", "area-workflows", "area-infrastructure"],
  "category": "enhancement",
  "confidence": 0.95,
  "reasoning": "Issue proposes a new GitHub Actions composite action for infrastructure health checks before agent invocation, clearly an enhancement to CI/CD workflows."
}
```

```

</details>

<details>
<summary>Roadmap Alignment</summary>

```json
```json
{
  "milestone": "v1.1",
  "priority": "P1",
  "epic_alignment": "",
  "confidence": 0.85,
  "reasoning": "Infrastructure health check aligns with v1.1 maintainability focus; distinct from existing epics so no epic alignment, but high value for CI reliability.",
  "escalate_to_prd": true,
  "escalation_criteria": ["feature_request", "multi_phase_work", "architectural_impact"],
  "complexity_score": 7
}
```

```

</details>

---

<sub>Powered by [AI Issue Triage](https://github.com/rjmurillo/ai-agents) - [View Workflow](https://github.com/rjmurillo/ai-agents/actions/runs/20392780607)</sub>


