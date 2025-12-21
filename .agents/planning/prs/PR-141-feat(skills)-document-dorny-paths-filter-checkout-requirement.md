---
number: 141
title: "feat(skills): document dorny/paths-filter checkout requirement"
state: OPEN
author: rjmurillo-bot
created_at: 12/20/2025 09:34:18
closed_at: null
merged_at: null
head_branch: feat/skills-dorny-paths-filter
base_branch: main
labels: []
url: https://github.com/rjmurillo/ai-agents/pull/141
---

# feat(skills): document dorny/paths-filter checkout requirement

## Summary

Add skill memory documenting a critical lesson learned from PRs #100 and #121.

## The Lesson

When using the `dorny/paths-filter` pattern for required status checks:
- Checkout is required in ALL jobs using the pattern
- This includes both check-paths jobs AND skip jobs
- Without checkout, paths-filter cannot analyze changes

## Background

- **PR #100**: Established the paths-filter pattern
- **PR #121**: Copilot incorrectly suggested removing checkout from skip job
- **Owner feedback**: "This is incorrect. This is required for `dorny/paths-filter`"

## Documentation

Added memory: `.serena/memories/skills-dorny-paths-filter-checkout-requirement.md`

Includes:
- Anti-pattern (WRONG)
- Correct pattern
- Evidence from PRs #100 and #121
- Related workflows that use this pattern

## Related

- PR #100, PR #121 (comment 2636959916)
- Requested by rjmurillo: "this lesson should be documented for posterity"

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)

---

## Files Changed (1 files)

| File | Additions | Deletions |
|------|-----------|-----------|| `.serena/memories/skills-dorny-paths-filter-checkout-requirement.md` | +65 | -0 |


---

## Reviews

### Review by @copilot-pull-request-reviewer - COMMENTED (12/20/2025 09:35:46)

## Pull request overview

This PR documents a critical lesson learned about the `dorny/paths-filter` GitHub Actions pattern: checkout is required in ALL jobs that interact with the pattern, not just the check-paths job. This addresses a mistake made in PR #121 where checkout was incorrectly suggested for removal.

**Key Changes:**
- Added skill memory documentation in `.serena/memories/skills-dorny-paths-filter-checkout-requirement.md`
- Includes anti-pattern (wrong) and correct pattern examples with YAML code blocks
- Documents evidence from PRs #100 and #121 with owner feedback





### Review by @coderabbitai - COMMENTED (12/20/2025 09:51:11)

**Actionable comments posted: 0**

> [!CAUTION]
> Some comments are outside the diff and can’t be posted inline due to platform limitations.
> 
> 
> 
> <details>
> <summary>⚠️ Outside diff range comments (1)</summary><blockquote>
> 
> <details>
> <summary>.serena/memories/skills-dorny-paths-filter-checkout-requirement.md (1)</summary><blockquote>
> 
> `1-66`: **Add required skill memory metadata per coding guidelines.**
> 
> Skill memory files in `.serena/memories/*skill*.md` must include atomicity scores, session-specific evidence citations, validation counts, SMART criteria, and deduplication analysis. This file has none of these.
> 
> Add after line 5:
> - **Atomicity Score**: 0-100 rating for consistency across dorny/paths-filter usage
> - **Evidence Session Numbers**: Session IDs from PR #100 and PR #121
> - **Validation Count**: How many times this pattern was successfully applied
> 
> Add before "Related Patterns" section:
> - **SMART Validation Criteria** with Specific, Measurable, Actionable, Relevant, Time-bound breakdown
> - **Deduplication Analysis** comparing against existing memories (e.g., `skills-github-workflow-patterns.md`)
> 
> Update "Related Patterns" to use full paths (`.github/workflows/pester-tests.yml` instead of `pester-tests.yml`) and add cross-reference to related memory files.
> 
> </blockquote></details>
> 
> </blockquote></details>

<details>
<summary>📜 Review details</summary>

**Configuration used**: Repository YAML (base), Organization UI (inherited)

**Review profile**: CHILL

**Plan**: Pro

<details>
<summary>📥 Commits</summary>

Reviewing files that changed from the base of the PR and between 34bf4fe1effcdfd88c3c91ba7b887ffa7580a9fd and f56ebacaf7f88d25ac09908a30895a3e9615be51.

</details>

<details>
<summary>📒 Files selected for processing (1)</summary>

* `.serena/memories/skills-dorny-paths-filter-checkout-requirement.md` (1 hunks)

</details>

<details>
<summary>🧰 Additional context used</summary>

<details>
<summary>📓 Path-based instructions (2)</summary>

<details>
<summary>.serena/memories/**/*.md</summary>


**📄 CodeRabbit inference engine (.agents/retrospective/pr43-coderabbit-root-cause-analysis.md)**

> Update memory/knowledge base snapshots when refined estimates or critical data diverges from previously stored values by more than 10%
> 
> `.serena/memories/**/*.md`: Skill memory files MUST include atomicity scores (>85% threshold required for persistence), evidence citations with specific session numbers, and SMART validation criteria (Specific, Measurable, Actionable, Relevant, Time-bound)
> Skill deduplication analysis MUST be performed with similarity scoring (0-100%) before persistence, comparing new skills against existing memories and documenting the decision (ADD, UPDATE, or MERGE)
> All skill memory entries MUST include source reference, validation count (number of times applied), and cross-references to related skills in other memory files

Files:
- `.serena/memories/skills-dorny-paths-filter-checkout-requirement.md`

</details>
<details>
<summary>.serena/memories/*skill*.md</summary>


**📄 CodeRabbit inference engine (.agents/analysis/004-check-skill-exists-tool.md)**

> Memory files documenting skill usage requirements (e.g., skill-usage-mandatory.md) must be kept synchronized with actual Check-SkillExists.ps1 tool interface and available skills

Files:
- `.serena/memories/skills-dorny-paths-filter-checkout-requirement.md`

</details>

</details>

</details>

</details>

<!-- This is an auto-generated comment by CodeRabbit for review status -->

### Review by @coderabbitai - APPROVED (12/20/2025 09:51:14)



### Review by @rjmurillo - APPROVED (12/20/2025 10:58:36)




---

## Comments

### Comment by @gemini-code-assist on 12/20/2025 09:34:22

> [!NOTE]
> Gemini is unable to generate a review for this pull request due to the file types involved not being currently supported.

### Comment by @coderabbitai on 12/20/2025 09:51:08

<!-- This is an auto-generated comment: summarize by coderabbit.ai -->
<!-- walkthrough_start -->

<details>
<summary>📝 Walkthrough</summary>

## Walkthrough

New documentation file explaining that jobs using `dorny/paths-filter` in GitHub Actions must include `actions/checkout`. Covers correct and incorrect YAML patterns, supporting evidence, and applicability to workflows.

## Changes

| Cohort / File(s) | Summary |
|---|---|
| **Documentation** <br> `\.serena/memories/skills-dorny-paths-filter-checkout-requirement\.md` | New file documenting the requirement for `actions/checkout` in all jobs using `dorny/paths-filter`, including correct/incorrect pattern examples and related workflow guidance |

## Estimated code review effort

🎯 1 (Trivial) | ⏱️ ~3 minutes

## Possibly related PRs

- rjmurillo/ai-agents#100: Implements check-paths/skip-tests using `dorny/paths-filter` which directly depends on the checkout requirement documented here
- rjmurillo/ai-agents#109: Adds `actions/checkout` to workflows to support `dorny` GitHub Actions, addressing the same root issue from the implementation side

## Suggested reviewers

- rjmurillo

</details>

<!-- walkthrough_end -->


<!-- pre_merge_checks_walkthrough_start -->

## Pre-merge checks and finishing touches
<details>
<summary>✅ Passed checks (3 passed)</summary>

|     Check name     | Status   | Explanation                                                                                                                                                                   |
| :----------------: | :------- | :---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
|     Title check    | ✅ Passed | Title follows conventional commit format with 'feat' scope and clearly describes the main change: documenting the dorny/paths-filter checkout requirement.                    |
|  Description check | ✅ Passed | Description directly relates to the changeset, explaining the lesson learned, providing background context from PRs #100 and #121, and detailing the new memory file content. |
| Docstring Coverage | ✅ Passed | No functions found in the changed files to evaluate docstring coverage. Skipping docstring coverage check.                                                                    |

</details>

<!-- pre_merge_checks_walkthrough_end -->

<!-- finishing_touch_checkbox_start -->

<details>
<summary>✨ Finishing touches</summary>

<details>
<summary>🧪 Generate unit tests (beta)</summary>

- [ ] <!-- {"checkboxId": "f47ac10b-58cc-4372-a567-0e02b2c3d479", "radioGroupId": "utg-output-choice-group-unknown_comment_id"} -->   Create PR with unit tests
- [ ] <!-- {"checkboxId": "07f1e7d6-8a8e-4e23-9900-8731c2c87f58", "radioGroupId": "utg-output-choice-group-unknown_comment_id"} -->   Post copyable unit tests in a comment
- [ ] <!-- {"checkboxId": "6ba7b810-9dad-11d1-80b4-00c04fd430c8", "radioGroupId": "utg-output-choice-group-unknown_comment_id"} -->   Commit unit tests in branch `feat/skills-dorny-paths-filter`

</details>

</details>

<!-- finishing_touch_checkbox_end -->


---

<details>
<summary>📜 Recent review details</summary>

**Configuration used**: Repository YAML (base), Organization UI (inherited)

**Review profile**: CHILL

**Plan**: Pro

<details>
<summary>📥 Commits</summary>

Reviewing files that changed from the base of the PR and between 34bf4fe1effcdfd88c3c91ba7b887ffa7580a9fd and f56ebacaf7f88d25ac09908a30895a3e9615be51.

</details>

<details>
<summary>📒 Files selected for processing (1)</summary>

* `.serena/memories/skills-dorny-paths-filter-checkout-requirement.md` (1 hunks)

</details>

<details>
<summary>🧰 Additional context used</summary>

<details>
<summary>📓 Path-based instructions (2)</summary>

<details>
<summary>.serena/memories/**/*.md</summary>


**📄 CodeRabbit inference engine (.agents/retrospective/pr43-coderabbit-root-cause-analysis.md)**

> Update memory/knowledge base snapshots when refined estimates or critical data diverges from previously stored values by more than 10%
> 
> `.serena/memories/**/*.md`: Skill memory files MUST include atomicity scores (>85% threshold required for persistence), evidence citations with specific session numbers, and SMART validation criteria (Specific, Measurable, Actionable, Relevant, Time-bound)
> Skill deduplication analysis MUST be performed with similarity scoring (0-100%) before persistence, comparing new skills against existing memories and documenting the decision (ADD, UPDATE, or MERGE)
> All skill memory entries MUST include source reference, validation count (number of times applied), and cross-references to related skills in other memory files

Files:
- `.serena/memories/skills-dorny-paths-filter-checkout-requirement.md`

</details>
<details>
<summary>.serena/memories/*skill*.md</summary>


**📄 CodeRabbit inference engine (.agents/analysis/004-check-skill-exists-tool.md)**

> Memory files documenting skill usage requirements (e.g., skill-usage-mandatory.md) must be kept synchronized with actual Check-SkillExists.ps1 tool interface and available skills

Files:
- `.serena/memories/skills-dorny-paths-filter-checkout-requirement.md`

</details>

</details>

</details>

</details>

<!-- tips_start -->

---



<sub>Comment `@coderabbitai help` to get the list of available commands and usage tips.</sub>

<!-- tips_end -->

<!-- internal state start -->


<!-- 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 -->

<!-- internal state end -->

