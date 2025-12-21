---
number: 150
title: "Extract duplicated verdict evaluation logic to reusable function"
state: OPEN
created_at: 12/20/2025 09:37:32
author: rjmurillo-bot
labels: ["enhancement", "area-workflows", "priority:P2"]
assignees: []
milestone: null
url: https://github.com/rjmurillo/ai-agents/issues/150
---

# Extract duplicated verdict evaluation logic to reusable function

## Problem

The PARTIAL→FAIL semantic logic for verdict evaluation appears twice in `.github/workflows/ai-spec-validation.yml` (lines 236 and 347). If this logic changes, both locations must be updated, creating a maintenance burden and risk of inconsistency.

## Evidence

**Source**: CodeRabbit review comment in PR #76
**Review ID**: PRR_kwDOQoWRls7WnNIQ
**Comment**: "PARTIAL→FAIL semantic change is intentional but logic is duplicated. The condition on line 236 is repeated on line 347. If this logic changes, both must update."

## Current State

**Line 236**:
```yaml
# Logic for checking verdict
$TraceVerdict -in 'CRITICAL_FAIL', 'FAIL' -or $CompletenessVerdict -in 'CRITICAL_FAIL', 'FAIL', 'PARTIAL'
```

**Line 347**:
```yaml
# Same logic repeated
$TraceVerdict -in 'CRITICAL_FAIL', 'FAIL' -or $CompletenessVerdict -in 'CRITICAL_FAIL', 'FAIL', 'PARTIAL'
```

## Proposed Solution

Extract the verdict evaluation logic to a PowerShell helper function in `AIReviewCommon.psm1`:

```powershell
function Test-SpecValidationFailed {
    param(
        [string]$TraceVerdict,
        [string]$CompletenessVerdict
    )
    return $TraceVerdict -in 'CRITICAL_FAIL', 'FAIL' -or
           $CompletenessVerdict -in 'CRITICAL_FAIL', 'FAIL', 'PARTIAL'
}
```

Then call this function from both locations in the workflow.

## Benefits

- Single source of truth for verdict logic
- Easier to maintain and update
- Reduces risk of inconsistent behavior
- Testable with Pester unit tests

## Related

- PR #76
- File: `.github/workflows/ai-spec-validation.yml`

---

🤖 Generated from PR homework scan


---

## Comments

### Comment by @coderabbitai on 12/20/2025 09:38:33

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
- https://github.com/rjmurillo/ai-agents/issues/144
- https://github.com/rjmurillo/ai-agents/issues/115
- https://github.com/rjmurillo/ai-agents/issues/104
- https://github.com/rjmurillo/ai-agents/issues/83
- https://github.com/rjmurillo/ai-agents/issues/145
</details>
<details>
<summary><b>🔗 Related PRs</b></summary>

rjmurillo/ai-agents#76 - fix(workflows): strengthen AI review rigor and enable PR gating [merged]
rjmurillo/ai-agents#100 - fix(ci): ensure Pester Tests workflow satisfies required checks for all PRs [closed]
</details>
<details>
<summary><b>👤 Suggested Assignees</b></summary>

- [rjmurillo-bot](https://github.com/rjmurillo-bot)
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

### Comment by @github-actions on 12/20/2025 09:38:38

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
|  **Priority** | `P2` |
| **Milestone** | v1.1 |


<details>
<summary>Categorization Analysis</summary>

```json
```json
{
  "labels": ["enhancement", "area-workflows", "area-infrastructure"],
  "category": "enhancement",
  "confidence": 0.95,
  "reasoning": "Issue requests refactoring duplicated verdict logic in GitHub Actions workflow into a reusable PowerShell function for maintainability"
}
```

```

</details>

<details>
<summary>Roadmap Alignment</summary>

```json
Based on my analysis:

**Issue Assessment:**
- Confirmed duplication exists (lines 238 and 349 have identical verdict logic)
- Scope: Single workflow file + shared module (`AIReviewCommon.psm1`)
- Clear implementation path proposed in issue
- Bug fix/refactoring to reduce maintenance burden
- Internal tooling improvement

**Framework Analysis:**
- **KANO**: Performance (improves maintainability proportionally)
- **RICE**: Low reach (maintainers only), medium impact, high confidence, low effort
- **Eisenhower**: Not Urgent, Moderately Important (schedule it)

**PRD Escalation Check:**
- Not a feature request (refactoring/tech debt)
- No research required (solution proposed)
- No external dependencies
- Single PR work
- No architectural impact
- Internal tooling only

```json
{
  "milestone": "v1.1",
  "priority": "P2",
  "epic_alignment": "",
  "confidence": 0.85,
  "reasoning": "Technical debt reduction for internal CI tooling with clear implementation path and minimal scope",
  "escalate_to_prd": false,
  "escalation_criteria": [],
  "complexity_score": 0
}
```

```

</details>

---

<sub>Powered by [AI Issue Triage](https://github.com/rjmurillo/ai-agents) - [View Workflow](https://github.com/rjmurillo/ai-agents/actions/runs/20392529791)</sub>


