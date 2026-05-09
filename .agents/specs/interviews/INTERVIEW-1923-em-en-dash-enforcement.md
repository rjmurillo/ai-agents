---
type: interview
id: INTERVIEW-1923
title: Em/en-dash prohibition enforcement
status: complete
related:
  - REQ-006
  - DESIGN-006
  - TASK-006
issue: 1923
author: spec-agent
created: 2026-05-09
updated: 2026-05-09
---

# Interview: Em/en-dash prohibition enforcement

## Problem Restatement

Em-dashes (U+2014) and en-dashes (U+2013) recur in agent-authored prose despite
prohibition. Bot reviewers flag every occurrence, costing 1+ round-trip per dash per
PR. A pre-commit hook, a commit-msg hook, a branch-wide pre_pr.py check, and a
universal.md rule close the enforcement gap.

## Design Tree Branches

### Branch 1: User Stories

- US-1: Human committing sees hook block + fix instruction. CONFIRMED.
- US-2: AI agent reads universal.md prohibition before writing. CONFIRMED.
- US-3: Maintainer runs pre_pr.py, catches pre-hook dashes. CONFIRMED.
- US-4: AI agent commit message blocked by commit-msg hook. CONFIRMED.

### Branch 2: Data Model

- No persistent state. Stateless grep at commit time. CONFIRMED.

### Branch 3: Integrations

- markdownlint-cli2: independent, no overlap. CONFIRMED.
- build/scripts/generate_rules.py: propagates universal.md to Copilot mirror. CONFIRMED.
- pre_pr.py: new validate_dash_prohibition() function. CONFIRMED.
- Hook placement: bash in .githooks/pre-commit (existing) and .githooks/commit-msg (new).
  NOT .claude/hooks/ (that is the Claude Code hook system, independent of git hooks). CONFIRMED.

### Branch 4: Failure Modes

- Merge commit: skip (reuse existing `IS_MERGE` flag at `.githooks/pre-commit:136-139`,
  set from `[ -f "$REPO_ROOT/.git/MERGE_HEAD" ]`). CONFIRMED. Note: an earlier draft
  said `IS_MERGE_COMMIT` and `git rev-parse -q --verify MERGE_HEAD`; both were
  inaccurate against the canonical hook and corrected during /review.
- Binary files: grep -I skips. CONFIRMED.
- grep no-match: || true or check output emptiness. CONFIRMED.
- Locale: LC_ALL=C.UTF-8 prefix for cross-platform safety. CONFIRMED.
- origin/main hardcode in pre_pr.py: use ref detection fallback chain. CONFIRMED.

### Branch 5: Security

- CWE-78 mitigated: pre-commit reuses `STAGED_MD_FILES` (newline-delimited, built at
  `.githooks/pre-commit:186`) and iterates via `while IFS= read -r dash_file <<<
  "$STAGED_MD_FILES"` (no word-splitting on filenames with spaces). Files are passed quoted
  to `grep`. commit-msg hook receives `$1` from git directly. pre_pr.py uses Python lists.
  No shell interpolation of filenames anywhere.
- No network calls, no secrets. CONFIRMED.

### Branch 6: Observability

- Hook stderr output with file list and fix instruction. CONFIRMED.
- Output pattern: `echo_error` + `EXIT_STATUS=1` (canonical pattern at `.githooks/pre-commit`; no `record_fail`/`record_pass` helpers exist, contrary to early draft; verified by grep). CONFIRMED.
- No telemetry. CONFIRMED.

### Branch 7: Scope Boundaries

- OUT_OF_SCOPE: ~/.claude/CLAUDE.md (already done), retroactive cleanup, CI enforcement,
  Windows hooks, vendored content remediation.
- DEFERRED: D1 auto-replace tool, D2 CI-level enforcement.

## Review Findings

### Analyst

- Flagged commit-msg hook at .claude/hooks/commit-msg/ as unsupported by Claude Code
  settings.json. REBUTTED: .githooks/commit-msg is a standard git hook, independent of
  Claude Code's hook system. Fires for all git commits via core.hooksPath.
- Flagged exit code ambiguity in AC-1/AC-2. ACCEPTED: specified exit 1 explicitly.
- Flagged origin/main hardcode. ACCEPTED: use ref detection fallback.

### Decision-Critic

- Verdict: STAND with two minor revisions (exit code, locale).
- Contrarian position (markdownlint custom rule): REJECTED. Bash grep is simpler than
  custom JS rule + node dependency.
- Alternative framing (general prose-style enforcement): noted but deferred per YAGNI.

### Pre-Mortem

- P0 scenario: commit-msg hook never fires due to wrong placement. RESOLVED: corrected
  from .claude/hooks/commit-msg/ to .githooks/commit-msg.
- Exit code ambiguity: RESOLVED.
- Locale blind spot: RESOLVED with LC_ALL=C.UTF-8.

## Complexity

Tier 1. All deliverables are scoped punch-list items with pass/fail ACs.
