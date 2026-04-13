---
description: Use when running all 6 PR quality gate agents locally before pushing. Provides comprehensive pre-push validation across security, QA, analysis, architecture, DevOps, and roadmap.
argument-hint: [BASE_BRANCH]
allowed-tools:
  - Bash(git:*)
  - Skill
model: haiku
---

# PR Quality Gate - All Agents

Run all 6 quality gate agents (security, QA, analyst, architect, DevOps, and roadmap) sequentially on your current changes.

## Pre-flight Checks

Use the Bash tool to gather context:

1. Run `git branch --show-current` to determine the current branch
2. Use $ARGUMENTS as the base branch if provided, otherwise default to `main`
3. Run `git diff "<base_branch>" --name-only | wc -l` to count changed files

If no changes detected, exit early with PASS.

## Agent Execution

Invoke each agent command using Skill tool and capture results.

**Note**: The base branch argument is forwarded to each sub-command.

1. Security Agent: `/pr-quality:security $ARGUMENTS`
2. QA Agent: `/pr-quality:qa $ARGUMENTS`
3. Analyst Agent: `/pr-quality:analyst $ARGUMENTS`
4. Architect Agent: `/pr-quality:architect $ARGUMENTS`
5. DevOps Agent: `/pr-quality:devops $ARGUMENTS`
6. Roadmap Agent: `/pr-quality:roadmap $ARGUMENTS`

## Verdict Aggregation

Parse each agent's `VERDICT: TOKEN` output and merge using these rules:

**Merge Logic** (from AIReviewCommon.psm1:Merge-Verdicts):

- ANY `CRITICAL_FAIL`, `REJECTED`, or `FAIL` → Final: **CRITICAL_FAIL**
- ANY `WARN` (no critical failures) → Final: **WARN**
- ALL `PASS` → Final: **PASS**

## Output Summary

Generate consolidated report in EXACTLY this format. Do not add preambles or explanations before the table:

| Agent | Verdict | Status | Key Findings |
|-------|---------|--------|--------------|
| 🔒 Security | [verdict] | [emoji] | [summary] |
| 🧪 QA | [verdict] | [emoji] | [summary] |
| 📊 Analyst | [verdict] | [emoji] | [summary] |
| 📐 Architect | [verdict] | [emoji] | [summary] |
| ⚙️ DevOps | [verdict] | [emoji] | [summary] |
| 🗺️ Roadmap | [verdict] | [emoji] | [summary] |

**FINAL VERDICT**: [PASS|WARN|CRITICAL_FAIL]

**Emoji Mapping** (from AIReviewCommon.psm1:Get-VerdictEmoji):

- PASS → ✅
- WARN → ⚠️
- CRITICAL_FAIL/REJECTED/FAIL → ❌
- UNKNOWN → ❔

**Next Steps**:

- **PASS**: Safe to commit and push
- **WARN**: Review findings, address if time permits, safe to push
- **CRITICAL_FAIL**: Fix blocking issues before pushing
