---
type: task
id: TASK-005
title: Implement pre-push validation hooks for PR iteration cost reduction
status: draft
priority: high
complexity: L
related:
  - DESIGN-005
  - REQ-005
  - issue: 1884
blocked_by: []
blocks: []
assignee: implementer
date: 2026-05-03
---

# TASK-005: Implement pre-push validation hooks for PR iteration cost reduction

## Objective

Implement three Claude Code PreToolUse hooks that block `git push` on markdown style violations,
manifest count drift, and session log placeholder values. Deliver as four milestones so each
can be reviewed and merged independently without blocking subsequent work.

## In Scope

- `push_guard_base.py`: shared hook framework
- `invoke_markdownlint_guard.py`: US-1
- `invoke_manifest_count_guard.py`: US-2
- `invoke_session_log_field_guard.py`: US-3
- `hooks.json` registration entries
- Unit tests for all new modules

## Out of Scope

- FM-3 (PR description staleness): issue #1885
- FM-5 (spec-before-code enforcement)
- Auto-fix behavior
- Git pre-push hook bootstrapping
- CI workflow changes
- Full-repo violation remediation

---

## Milestone M1: Shared hook framework

### TASK-005-1: Implement `push_guard_base.py` and its tests

**Objective**: Deliver the shared Strategy framework used by all three push guards.

**Complexity**: S (2-4 hours)

**Files affected**:

| File | Action | Description |
|------|--------|-------------|
| `.claude/hooks/PreToolUse/push_guard_base.py` | Create | Shared framework: lib bootstrap, changeset reading, dispatcher, output formatter |
| `tests/hooks/__init__.py` | Create (if absent) | Python package marker |
| `tests/hooks/test_push_guard_base.py` | Create | Unit tests: consumer repo skip, empty stdin, empty diff, exception fail-open, violation output format |

**Acceptance Criteria**

- [ ] `run_guard(validator_fn, globs, name)` reads stdin JSON, extracts command, runs
  `git diff --name-only @{push}..HEAD` (subprocess, no shell) to get committed-but-not-pushed
  files. If that fails (no upstream), falls back to `git diff --name-only origin/main...HEAD`.
  Filters paths by globs, calls `validator_fn` only when matches exist.
- [ ] Returns 0 when no matching files in changeset.
- [ ] Returns 2 when `validator_fn` returns non-empty violation list.
- [ ] Prints `## BLOCKED [E_<CODE>]: <name>` header and each violation line on stdout.
- [ ] Returns 0 (fail-open) and prints to stderr on any unhandled exception.
- [ ] `skip_if_consumer_repo` called before any logic.
- [ ] All tests pass. Coverage >= 80%.

**Implementation Notes**

Copy the lib-bootstrap block verbatim from `invoke_session_log_guard.py` lines 31-48. Do not
paraphrase or shorten; the exact walk-up logic handles both source-tree and installed layouts.

Use `fnmatch.fnmatch` for glob matching against the flat path list from `git diff --name-only`.
For patterns like `.claude/skills/*/SKILL.md`, use `pathlib.PurePosixPath` matching or a
two-step filter (directory depth check + filename check) since `fnmatch` does not handle `**`.

---

## Milestone M2: Markdownlint guard

### TASK-005-2: Implement `invoke_markdownlint_guard.py` and its tests

**Objective**: Ship US-1. Block `git push` when changed `.md` files violate markdownlint.

**Complexity**: S (2-4 hours)

**Files affected**:

| File | Action | Description |
|------|--------|-------------|
| `.claude/hooks/PreToolUse/invoke_markdownlint_guard.py` | Create | Hook: binary check, subprocess invocation, violation parsing |
| `tests/hooks/test_markdownlint_guard.py` | Create | Unit tests: AC-1 through AC-3, AC-8 partial, timeout |
| `.claude/hooks/hooks.json` | Modify | Append markdownlint hook entry to `Bash(git push*)` block |

**Acceptance Criteria**

- [ ] Hook calls `shutil.which("markdownlint-cli2")`. If None, prints WARN to stderr, returns 0.
- [ ] Runs `markdownlint-cli2 <files...>` with `timeout=60`, `shell=False`.
- [ ] On timeout (`subprocess.TimeoutExpired`), returns violation line
  `[TIMEOUT] markdownlint-cli2 exceeded 60s` and exits 2.
- [ ] On non-zero exit, passes markdownlint output lines through as violations.
- [ ] On zero exit (no violations), returns 0.
- [ ] On empty changeset (no `*.md` files), returns 0 without invoking binary.
- [ ] `hooks.json` entry added with `timeout: 70`.
- [ ] All tests pass. Coverage >= 80%.

**Implementation Notes**

markdownlint-cli2 automatically finds `.markdownlint-cli2.yaml` when run from the project root.
The hook runs in the project root (CWD is set by Claude Code before hook invocation). Do not
pass `--config` explicitly unless tests reveal the CWD assumption is incorrect.

Test the binary-absent case by patching `shutil.which` to return `None`.
Test the violation case by patching `subprocess.run` to return a `CompletedProcess` with
returncode=1 and sample stdout.

---

## Milestone M3: Manifest count guard (wires existing validator)

### TASK-005-3: Implement `invoke_manifest_count_guard.py` and its tests

**Objective**: Ship US-2. Block `git push` when marketplace.json description counts disagree
with filesystem. Reuses existing `build/scripts/validate_marketplace_counts.py` (no new script).

**Complexity**: S (2-4 hours)

**Files affected**:

| File | Action | Description |
|------|--------|-------------|
| `.claude/hooks/PreToolUse/invoke_manifest_count_guard.py` | Create | Hook: import existing validator, translate exit code to block/allow |
| `tests/hooks/test_manifest_count_guard.py` | Create | Tests: AC-4, AC-5, AC-8 partial, counts match, counts mismatch |
| `.claude/hooks/hooks.json` | Modify | Append manifest count hook entry to `Bash(git push*)` block |

**Acceptance Criteria**

- [ ] Hook activates only when changeset includes files matching `templates/agents/*.md`,
  `.claude/skills/*/SKILL.md`, `.claude/commands/*.md`, or `.claude-plugin/marketplace.json`.
- [ ] Adds `build/scripts/` to `sys.path` and imports
  `validate_marketplace_counts.validate_known_marketplaces(repo_root=project_dir)`.
- [ ] On return code 1 (mismatch), captures stdout and formats as violation lines.
  Includes hint: "Run `python3 build/scripts/validate_marketplace_counts.py --fix` to auto-correct."
- [ ] On return code 2 (config error), produces violation with parse-error message.
- [ ] Returns 0 when all counts agree.
- [ ] Returns 0 immediately when no manifest-affecting files in changeset.
- [ ] All tests pass. Coverage >= 80%.

**Implementation Notes**

The existing script at `build/scripts/validate_marketplace_counts.py` handles all count
derivation, regex parsing, and fix mode. Config lives in `templates/marketplace-counters.yaml`.
SEMANTIC_INDEX.yaml is NOT part of this validation (removed per Amendment 2).
The hook is a thin adapter: bootstrap, detect relevant files, call the existing function,
translate exit codes. No pre_pr.py extension needed (CI already runs the script).

---

## Milestone M4: Session log field guard

### TASK-005-4: Implement `invoke_session_log_field_guard.py` and its tests

**Objective**: Ship US-3. Block `git push` when session logs have placeholder values.

**Complexity**: S (2-4 hours)

**Files affected**:

| File | Action | Description |
|------|--------|-------------|
| `.claude/hooks/PreToolUse/invoke_session_log_field_guard.py` | Create | Hook: JSON parse, three-field check, violation lines |
| `tests/hooks/test_session_log_field_guard.py` | Create | Tests: AC-6, AC-7, AC-8 partial, malformed JSON, all fields valid |
| `.claude/hooks/hooks.json` | Modify | Append session log field hook entry to `Bash(git push*)` block |

**Acceptance Criteria**

- [ ] Hook activates only when changeset includes files matching `.agents/sessions/*.json`.
- [ ] For each matching file, parses JSON. On parse failure, produces violation line
  `<path>: JSON parse error - <message>` and blocks.
- [ ] Checks `schemaVersion` is present and non-empty.
- [ ] Checks `endingCommit` is present and not the literal string `"pending"`.
- [ ] Checks `markdownLintRun.Complete` is `true` (not `false` or absent) and
  `markdownLintRun.Evidence` is a non-empty, non-placeholder string.
- [ ] Produces violation line `<path>:<field> <reason>` for each failed check.
- [ ] Returns 0 when all checks pass.
- [ ] Returns 0 immediately when no `.agents/sessions/*.json` in changeset.
- [ ] All tests pass. Coverage >= 80%.

**Implementation Notes**

The `markdownLintRun.scanned` check is conditioned on two things: (a) the key exists in the
session log and (b) the changeset contains `.md` files. If the key is absent, skip the check
(not a violation). If the key exists but the list is empty and `*.md` files are in the
changeset, that is a violation.

---

## Testing Requirements (AC-10)

All tests live under `tests/hooks/`. Each test module covers:
- **Positive case**: valid input, returns 0, no output block.
- **Negative case**: violating input, returns 2, violation lines in stdout.
- **Edge cases**: empty changeset (returns 0), missing/unavailable tool (WARN + returns 0 for
  markdownlint; parse error + returns 2 for JSON-based hooks), malformed input files.

Coverage target: >= 80% per AGENTS.md business-logic floor.

Run with: `pytest tests/hooks/ -v`

---

## Summary of File Changes per Milestone

| Milestone | Files | Max files/commit (AGENTS.md limit: 5) |
|-----------|-------|---------------------------------------|
| M1 | `push_guard_base.py`, `tests/hooks/__init__.py`, `tests/hooks/test_push_guard_base.py` | 3 |
| M2 | `invoke_markdownlint_guard.py`, `test_markdownlint_guard.py`, `hooks.json` | 3 |
| M3 | `invoke_manifest_count_guard.py`, `test_manifest_count_guard.py`, `hooks.json` | 3 |
| M4 | `invoke_session_log_field_guard.py`, `test_session_log_field_guard.py`, `hooks.json` | 3 |

All milestones are within the 5-file atomic commit limit.

---

## Recommended Delivery Order

1. M1 (framework) first. M2, M3, M4 can proceed in any order after M1 merges.
2. M3 imports from existing `build/scripts/validate_marketplace_counts.py` (no new script prerequisite).
3. M2, M3, M4 are independent of each other once M1 is merged.

---

## Amendments Applied

Per REQ-005 Amendments 1-7:

- M3 simplified: no new `scripts/validation/manifest_counts.py` or `pre_pr.py` extension.
  Hook calls existing `build/scripts/validate_marketplace_counts.py`.
- SEMANTIC_INDEX.yaml removed from scope.
- Session log field check uses actual schema: `{Complete: bool, Evidence: str}`.
- Success metric: 50% reduction in mechanical-error iterations (not "1-2 rounds").
- #1885 (FM-3) is a blocking follow-up, not optional.
