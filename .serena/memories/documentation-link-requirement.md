# Documentation Link Requirement

**Importance**: HIGH
**Date**: 2026-03-09
**Applies To**: ALL agents producing documentation artifacts
**Source**: [PR #60 review](https://github.com/rjmurillo/ai-agents/pull/60#discussion_r2633132093), Issue #64

## The Rule

When referencing an existing repository file in documentation, the reference MUST be a clickable relative link. Plain text file paths without links are prohibited.

## Scope

All markdown artifacts: `.agents/`, `.gemini/`, `docs/`, retrospectives, session logs, plans, and any documentation that references repository files.

## Examples

WRONG: `` Plan referenced test file `.github/workflows/tests/ai-issue-triage.Tests.ps1` ``

CORRECT: `Plan referenced test file [`.github/workflows/tests/ai-issue-triage.Tests.ps1`](.github/workflows/tests/ai-issue-triage.Tests.ps1)`

## Exceptions

- Code blocks (fenced with triple backticks) are exempt
- Shell commands and script invocations are exempt
- Paths referencing non-existent files (hypothetical examples) are exempt
- Informational tables listing file path patterns (not specific files) are exempt

## Canonical Reference

See [`.agents/governance/DOCUMENTATION-LINK-REQUIREMENTS.md`](../../.agents/governance/DOCUMENTATION-LINK-REQUIREMENTS.md).
