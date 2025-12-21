---
number: 160
title: "Add directory structure review guidance to architect agent"
state: OPEN
created_at: 12/20/2025 10:18:32
author: rjmurillo-bot
labels: ["documentation", "enhancement"]
assignees: []
milestone: null
url: https://github.com/rjmurillo/ai-agents/issues/160
---

# Add directory structure review guidance to architect agent

## Problem

PR #147 created an unnecessary nested directory structure (`scripts/copilot/`) without clear justification. The architect agent didn't flag this as a cohesion concern.

## Current State

The architect agent (src/claude/architect.md) focuses on:
- ADRs and design decisions
- Design patterns and principles
- System architecture

But lacks guidance on:
- Directory structure review
- Unnecessary nesting detection
- File placement cohesion

## Proposed Enhancement

Add to architect.md:

```markdown
## Code Organization Review

When reviewing PRs that add new directories:

### Questions to Ask
1. Does this directory nesting serve a clear purpose?
2. Could these files live one level up without loss of clarity?
3. Is there an existing directory where this code belongs?
4. Does the structure follow established patterns in the codebase?

### Anti-Patterns to Flag
- Single-file directories (directory with only one file)
- Deep nesting without clear domain separation
- Parallel structures that could be consolidated
- Inconsistent naming with existing directories
```

## Evidence

PR #147 created `scripts/copilot/` containing a single script that could have lived at `scripts/Invoke-CopilotAssignment.ps1`.

## Related

- Skill-Review-005: Cohesion check for new files
- PR #147 review failure retrospective

---

Generated with [Claude Code](https://claude.com/claude-code)

---

## Comments

### Comment by @github-actions on 12/20/2025 10:19:28

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
| **Labels** | enhancement agent-architect area-prompts |
|  **Priority** | `P2` |
| **Milestone** | v1.1 |


<details>
<summary>Categorization Analysis</summary>

```json
```json
{
  "labels": ["enhancement", "agent-architect", "area-prompts"],
  "category": "enhancement",
  "confidence": 0.92,
  "reasoning": "Issue requests adding directory structure review guidance to the architect agent prompt file"
}
```

```

</details>

<details>
<summary>Roadmap Alignment</summary>

```json
Based on my analysis:

1. **Issue type**: Enhancement to architect agent documentation
2. **Scope**: Single-file modification to `src/claude/architect.md`
3. **Alignment**: Relates to code review quality and structural governance, which aligns with architect agent responsibilities
4. **Complexity**: Low - clear implementation path, specific guidance proposed, single file change
5. **PRD need**: No - this is a documentation update with explicit guidance already provided in the issue

```json
{
  "milestone": "v1.1",
  "priority": "P2",
  "epic_alignment": "",
  "confidence": 0.80,
  "reasoning": "Documentation enhancement to existing agent with clear implementation; does not impact core functionality or require research",
  "escalate_to_prd": false,
  "escalation_criteria": [],
  "complexity_score": 0
}
```

```

</details>

---

<sub>Powered by [AI Issue Triage](https://github.com/rjmurillo/ai-agents) - [View Workflow](https://github.com/rjmurillo/ai-agents/actions/runs/20392963617)</sub>


### Comment by @coderabbitai on 12/20/2025 10:20:03

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
- https://github.com/rjmurillo/ai-agents/issues/65
- https://github.com/rjmurillo/ai-agents/issues/157
- https://github.com/rjmurillo/ai-agents/issues/124
- https://github.com/rjmurillo/ai-agents/issues/45
</details>
<details>
<summary><b>🔗 Related PRs</b></summary>

rjmurillo/vs-code-agents#1 - feat: Add customized multi-agent system for VS Code and Claude Code [merged]
rjmurillo/vs-code-agents#3 - feat: add GitHub Copilot CLI support  [merged]
rjmurillo/vs-code-agents#11 - feat: achieve Claude agent parity with VS Code agents [merged]
rjmurillo/vs-code-agents#13 - docs: update documentation to reflect agent parity [merged]
rjmurillo/ai-agents#20 - feat: Phase 2 CWE-78 Incident Remediation - Operational Capabilities [merged]
</details>
<details>
<summary><b>👤 Suggested Assignees</b></summary>

- [rjmurillo](https://github.com/rjmurillo)
- [rjmurillo-bot](https://github.com/rjmurillo-bot)
- [coderabbitai](https://github.com/coderabbitai)
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

