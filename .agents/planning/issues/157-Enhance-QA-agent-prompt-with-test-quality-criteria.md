---
number: 157
title: "Enhance QA agent prompt with test quality criteria"
state: OPEN
created_at: 12/20/2025 10:17:43
author: rjmurillo-bot
labels: ["documentation", "enhancement"]
assignees: []
milestone: null
url: https://github.com/rjmurillo/ai-agents/issues/157
---

# Enhance QA agent prompt with test quality criteria

## Problem

The QA agent correctly identified CRITICAL_FAIL for PR #147 due to pattern-based tests, but the finding was not specific enough about what constitutes inadequate tests.

## Current State

QA agent prompt (src/claude/qa.md) focuses on:
- Test strategy
- Coverage requirements
- User perspective validation

But lacks explicit guidance on:
- Pattern-matching tests vs functional tests
- Mock requirements for external dependencies
- Edge case coverage requirements

## Proposed Enhancement

Add a Test Quality Criteria section to qa.md:

```markdown
## Test Quality Criteria

### Insufficient Test Patterns (CRITICAL_FAIL)

- Tests that use `Should -Match` on script content instead of executing functions
- Tests that verify code structure via regex without testing behavior
- Tests claiming AAA pattern but only verifying existence of code blocks
- Tests without Mock blocks for external dependencies (gh CLI, APIs)

### Required Test Patterns (PASS)

- Tests that actually execute the function under test
- Mock blocks for all external dependencies
- Edge case coverage: null inputs, empty arrays, error conditions
- Integration tests that verify end-to-end behavior
```

## Evidence

PR #147 had 60 \tests\ that only pattern-matched code structure. QA correctly flagged this but the prompt could be more explicit about why pattern-based tests are insufficient.

## Related

- PR #147 review failure retrospective
- Skill-Review-003: Pattern-based tests are insufficient

---

Generated with [Claude Code](https://claude.com/claude-code)

---

## Comments

### Comment by @github-actions on 12/20/2025 10:18:46

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
| **Labels** | enhancement agent-qa area-prompts |
|  **Priority** | `P2` |
| **Milestone** | v1.1 |


<details>
<summary>Categorization Analysis</summary>

```json
```json
{
  "labels": ["enhancement", "agent-qa", "area-prompts"],
  "category": "enhancement",
  "confidence": 0.95,
  "reasoning": "Issue proposes adding test quality criteria section to the QA agent prompt file (src/claude/qa.md)"
}
```

```

</details>

<details>
<summary>Roadmap Alignment</summary>

```json
Based on my analysis of the issue and roadmap context:

**Issue Analysis:**
- Enhances QA agent prompt with explicit test quality criteria
- Documentation/prompt improvement (enhancement + documentation labels)
- Evidence-based request from PR #147 retrospective
- References existing skill (Skill-Review-003)
- Single file change (src/claude/qa.md)
- Clear implementation path with proposed content

**Roadmap Alignment:**
- No direct epic match. This is internal tooling improvement, not a user-facing feature
- Aligns with Master Product Objective (quality multi-agent workflows)
- Low complexity, single file scope

**Priority Assessment:**
- Impact: Medium (improves agent effectiveness)
- Urgency: Not immediate (process improvement, not blocking)
- P2 is appropriate

**PRD Escalation Check:**
- Not a new feature (enhancement to existing capability)
- No research required (clear proposed solution)
- No external dependencies
- Single-phase work (one PR)
- No architectural impact (content change only)
- Not customer-facing (internal tooling)

```json
{
  "milestone": "v1.1",
  "priority": "P2",
  "epic_alignment": "",
  "confidence": 0.85,
  "reasoning": "Documentation enhancement to QA agent with clear implementation path; aligns with v1.1 maintainability theme",
  "escalate_to_prd": false,
  "escalation_criteria": [],
  "complexity_score": 0
}
```

```

</details>

---

<sub>Powered by [AI Issue Triage](https://github.com/rjmurillo/ai-agents) - [View Workflow](https://github.com/rjmurillo/ai-agents/actions/runs/20392955056)</sub>


### Comment by @coderabbitai on 12/20/2025 10:18:50

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
- https://github.com/rjmurillo/ai-agents/issues/130
- https://github.com/rjmurillo/ai-agents/issues/77
- https://github.com/rjmurillo/ai-agents/issues/82
- https://github.com/rjmurillo/ai-agents/issues/115
</details>
<details>
<summary><b>🔗 Related PRs</b></summary>

rjmurillo/ai-agents#20 - feat: Phase 2 CWE-78 Incident Remediation - Operational Capabilities [merged]
rjmurillo/ai-agents#52 - feat: MCP config sync utility and pre-commit architecture documentation [merged]
rjmurillo/ai-agents#70 - feat(agents): add VS Code agent system [merged]
rjmurillo/ai-agents#76 - fix(workflows): strengthen AI review rigor and enable PR gating [merged]
rjmurillo/ai-agents#100 - fix(ci): ensure Pester Tests workflow satisfies required checks for all PRs [closed]
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

