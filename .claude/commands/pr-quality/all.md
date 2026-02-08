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

- Current branch: !`git branch --show-current`
- Changed files: !`BASE_ARG="${ARGUMENTS:-main}"; [ -z "$BASE_ARG" ] && BASE_ARG="main"; git diff "$BASE_ARG" --name-only | wc -l`
- Base branch: $ARGUMENTS or main (if not specified)

If no changes detected, exit early with PASS.

## Agent Execution

Invoke each agent command using Skill tool and capture results.

**Note**: All sub-skills are invoked with the base branch ($ARGUMENTS or main if not specified):

1. Security Agent: `/pr-quality:security $BASE_ARG`
2. QA Agent: `/pr-quality:qa $BASE_ARG`
3. Analyst Agent: `/pr-quality:analyst $BASE_ARG`
4. Architect Agent: `/pr-quality:architect $BASE_ARG`
5. DevOps Agent: `/pr-quality:devops $BASE_ARG`
6. Roadmap Agent: `/pr-quality:roadmap $BASE_ARG`

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
