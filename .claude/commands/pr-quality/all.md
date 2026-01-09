---
description: Use when running all 6 PR quality gate agents locally before pushing. Provides comprehensive pre-push validation across security, QA, analysis, architecture, DevOps, and roadmap.
argument-hint: [--base BRANCH]
allowed-tools: [Bash(git:*), Skill]
model: haiku
---

# PR Quality Gate - All Agents

Run all 6 quality gate agents (security, QA, analyst, architect, DevOps, and roadmap) sequentially on your current changes.

## Pre-flight Checks

- Current branch: !`git branch --show-current`
- Changed files: !`git diff "${1:-main}" --name-only | wc -l`
- Base branch: ${1:-main}

If no changes detected, exit early with PASS.

## Agent Execution

Invoke each agent command using Skill tool and capture results:

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
