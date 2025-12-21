---
number: 149
title: "Pre-commit hook should validate staged content, not working tree"
state: OPEN
created_at: 12/20/2025 09:36:51
author: rjmurillo-bot
labels: ["documentation", "enhancement", "area-workflows", "priority:P2", "area-skills"]
assignees: []
milestone: null
url: https://github.com/rjmurillo/ai-agents/issues/149
---

# Pre-commit hook should validate staged content, not working tree

## Problem

The pre-commit hook example in skill memory files validates the working tree instead of staged content.

## Evidence

**Source**: rjmurillo-bot comment in PR #94
**Comment**: "**cursor[bot] comment addressed**: The pre-commit hook example validates working tree instead of staged content. This is valid feedback, but the code is documentation/example in a skill memory file. The core learning (run PSScriptAnalyzer in pre-commit) remains actionable. Recommend accept-as-is with follow-up issue for enhancement."

## Current Behavior

The pre-commit hook example runs PSScriptAnalyzer against files in the working tree, not the staged changes.

## Expected Behavior

Pre-commit hooks should validate only staged changes to ensure what's being committed passes validation, regardless of unstaged modifications in the working tree.

## Proposed Solution

Update pre-commit hook examples to:
1. Get list of staged `.ps1` files using `git diff --cached --name-only --diff-filter=ACM`
2. Run PSScriptAnalyzer only against staged files
3. Provide clear documentation on why validating staged content is important

## Related

- PR #94
- Skill memory documentation for pre-commit hooks

---

🤖 Generated from PR homework scan


---

## Comments

### Comment by @coderabbitai on 12/20/2025 09:37:41

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

**Possible Duplicates**
- https://github.com/rjmurillo/ai-agents/issues/120

**Related Issues**
- https://github.com/rjmurillo/ai-agents/issues/81
- https://github.com/rjmurillo/ai-agents/issues/83
- https://github.com/rjmurillo/ai-agents/issues/9
- https://github.com/rjmurillo/ai-agents/issues/97
</details>
<details>
<summary><b>🔗 Related PRs</b></summary>

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

### Comment by @github-actions on 12/20/2025 09:37:49

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
| **Labels** | enhancement area-infrastructure |
|  **Priority** | `P2` |
| **Milestone** | v1.1 |


<details>
<summary>Categorization Analysis</summary>

```json
```json
{
  "labels": ["enhancement", "area-infrastructure"],
  "category": "enhancement",
  "confidence": 0.9,
  "reasoning": "Issue requests improvement to pre-commit hook examples to validate staged content instead of working tree, related to CI infrastructure documentation"
}
```

```

</details>

<details>
<summary>Roadmap Alignment</summary>

```json
Based on my analysis of the issue and roadmap context:

**Issue Analysis:**
- **Type**: Documentation/skill enhancement (pre-commit hook example improvement)
- **Scope**: Single file change (skill memory file with pre-commit hook example)
- **Impact**: Medium - affects developer experience with pre-commit hooks
- **Urgency**: Low - originated from PR #94 homework scan, not blocking anything

**Roadmap Alignment:**
- No direct epic alignment - this is a documentation quality improvement
- Relates tangentially to skill management but not a feature request per se

**PRD Escalation Assessment:**
- NOT a new feature request (documentation improvement to existing example)
- No research required (solution is clear: use `git diff --cached`)
- No external dependencies
- Single-phase work (one PR)
- No architectural impact
- Not customer-facing (internal tooling documentation)

```json
{
  "milestone": "v1.1",
  "priority": "P2",
  "epic_alignment": "",
  "confidence": 0.85,
  "reasoning": "Documentation quality fix for pre-commit hook example; clear solution, single PR scope",
  "escalate_to_prd": false,
  "escalation_criteria": [],
  "complexity_score": 0
}
```

```

</details>

---

<sub>Powered by [AI Issue Triage](https://github.com/rjmurillo/ai-agents) - [View Workflow](https://github.com/rjmurillo/ai-agents/actions/runs/20392523373)</sub>


