---
type: task
id: TASK-015
title: Implement pre-push validation hooks for PR iteration cost reduction
status: todo
priority: P1
complexity: L
related:
  - DESIGN-005
  - REQ-005
  - issue: 1884
  - issue: 1885
blocked_by: []
blocks: []
assignee: implementer
created: 2026-05-03
updated: 2026-05-04
---

# TASK-015: Implement pre-push validation hooks for PR iteration cost reduction

## Objective

Implement three Claude Code PreToolUse hooks that block `git push` on markdown style violations,
manifest count drift, and session log placeholder values. Deliver as four milestones in
sequence (M1, then M2, then M3, then M4) because all three appended hooks modify
`.claude/hooks/hooks.json` and parallel branches would collide on that file.

For full milestone exit criteria, dependency graph, risk register, and pre-mortem mitigations
that this task list inherits, see `.agents/plans/active/PLAN-1884-pr-iteration-cost.md`.

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

### TASK-015-1: Implement `push_guard_base.py` and its tests

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
  If both fail, returns 0 (fail-open) with a stderr warning. Filters paths by globs, calls
  `validator_fn` only when matches exist.
- [ ] Returns 0 when no matching files in changeset.
- [ ] Returns 2 when `validator_fn` returns non-empty violation list.
- [ ] Prints `## BLOCKED [E_<CODE>]: <name>` header and each violation line on stdout.
- [ ] Returns 0 (fail-open) and prints to stderr on any unhandled exception.
- [ ] `skip_if_consumer_repo` called before any logic.
- [ ] AC-11: a unit test asserts the hook entry in `hooks.json` uses the matcher
  `Bash(git push*)` exactly. This is the documented invariant; PreToolUse hooks are
  runtime-enforced and `--no-verify` does not apply, so this test is the static contract.
- [ ] Glob matching for nested patterns like `.claude/skills/*/SKILL.md` uses prefix+suffix
  string check (`startswith` plus `endswith`), NOT `fnmatch.fnmatch` (which fails on nested
  paths) and NOT `pathlib.PurePosixPath.match` (which also fails on the same input).
- [ ] All tests pass. Coverage >= 80%.

**Implementation Notes**

Copy the lib-bootstrap block verbatim from the comment-and-code block in
`invoke_session_log_guard.py` (currently lines 26-49 at HEAD; re-confirm exact range when
implementing). Do not paraphrase or shorten; the exact walk-up logic handles both source-tree
and installed layouts.

For glob matching, `.claude/skills/*/SKILL.md` cannot be matched with `fnmatch` or
`pathlib.match` because both fail on multi-segment paths. Implement a small helper:

```python
def _matches_skill_pattern(path: str) -> bool:
    return path.startswith('.claude/skills/') and path.endswith('/SKILL.md')
```

Apply the same prefix+suffix shape to other multi-segment patterns. Document the helper inline
so future maintainers see the rationale.

For single-segment glob patterns (e.g., `*.md`), `fnmatch.fnmatch` is acceptable. For all
multi-segment patterns (e.g., `.claude/skills/*/SKILL.md`, `templates/agents/*.md`), use the
prefix+suffix helper shown above. Do not use `pathlib.PurePosixPath.match`; it has the same
multi-segment limitation as `fnmatch`.

---

## Milestone M2: Markdownlint guard

### TASK-015-2: Implement `invoke_markdownlint_guard.py` and its tests

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
- [ ] Logs `markdownlint-cli2 --version` output to stderr before running validation (AC-3a).
- [ ] Runs `markdownlint-cli2 <files...>` with `timeout=60`, `shell=False`.
- [ ] On `subprocess.TimeoutExpired`: prints prominent stderr warning
  `[TIMEOUT] markdownlint-cli2 exceeded 60s; allowing push`, returns 0 (fail-open).
  Reverses the original block-on-timeout decision per pre-mortem mitigation: infrastructure
  latency is not a real lint violation and should not block work.
- [ ] On `OSError` (wrong-architecture binary, missing shared libraries): prints stderr warning
  `[OSError] markdownlint-cli2 failed to invoke: <message>; allowing push`, returns 0
  (fail-open).
- [ ] On non-zero exit, passes markdownlint output lines through as violations.
- [ ] On zero exit (no violations), returns 0.
- [ ] On empty changeset (no `*.md` files), returns 0 without invoking binary.
- [ ] `hooks.json` entry added with `timeout: 70` (subprocess 60s + 10s overhead).
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

### TASK-015-3: Implement `invoke_manifest_count_guard.py` and its tests

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
  `validate_marketplace_counts.validate_known_marketplaces`. The hook MUST pass
  `repo_root=project_dir` explicitly. The validator's module-level `REPO_ROOT` constant is
  resolved at import time relative to `__file__`, which can resolve incorrectly under
  alternate `sys.path` layouts (e.g., editable installs, test environments). Tests MUST
  assert that the explicit parameter is forwarded, not shadowed.
- [ ] On return code 1 (mismatch), captures stdout and formats as violation lines.
  Includes hint: "Run `python3 build/scripts/validate_marketplace_counts.py --fix` to auto-correct."
- [ ] On return code 2 (config error), produces violation with parse-error message.
- [ ] Returns 0 when all counts agree.
- [ ] Returns 0 immediately when no manifest-affecting files in changeset.
- [ ] All tests pass. Coverage >= 80%.

**Implementation Notes**

The existing script at `build/scripts/validate_marketplace_counts.py` handles all count
derivation, regex parsing, and fix mode. Config lives in `templates/marketplace-counters.yaml`.
`docs/SEMANTIC_INDEX.yaml` is NOT part of this validation; it is a semantic search index, not a
count manifest. The hook is a thin adapter: bootstrap, detect relevant files, call the existing
function, translate exit codes. No `pre_pr.py` extension needed (CI already runs the script).

---

## Milestone M4: Session log field guard

### TASK-015-4: Implement `invoke_session_log_field_guard.py` and its tests

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
- [ ] Checks `markdownLintRun.Complete` is `true` (not `false` or absent).
- [ ] Checks `markdownLintRun.Evidence` is a non-placeholder string. The check, in order:
  - `Evidence.strip()` length >= 20 characters (pre-mortem mitigation against single-character
    bypasses).
  - `Evidence.strip().lower()` not in placeholder set:
    `{"", "pending", "tbd", "n/a", "none", "done", "."}`.
- [ ] Produces violation line `<path>:<field> <reason>` for each failed check.
- [ ] Returns 0 when all checks pass.
- [ ] Returns 0 immediately when no `.agents/sessions/*.json` in changeset.
- [ ] All tests pass. Coverage >= 80%.

**Implementation Notes**

The `markdownLintRun` schema is `{Complete: bool, Evidence: str}`. There is no `.scanned`
field. The check has two parts:
- `markdownLintRun.Complete` must be present and `true`. Missing key, `false`, or other type is
  a violation.
- `markdownLintRun.Evidence` must be a non-empty string and not a placeholder (e.g., `""`,
  `"pending"`, `"TBD"`, `"n/a"`). The list of placeholder strings is defined in the test
  fixture and kept narrow to avoid false positives.

The validator does not attempt to verify that `Evidence` semantically matches the diff. That is
intractable given session logs may be written before the final edit. Structural completeness is
the contract.

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

Sequential: M1 -> M2 -> M3 -> M4.

Each of M2, M3, M4 modifies `.claude/hooks/hooks.json` (appends one entry to the
`Bash(git push*)` block). Parallel branches would collide on that file. Sequencing trades
parallel speed for clean merges.

If parallel implementation is unavoidable, the documented strategy is: M2 ships first; M3
and M4 each rebase on the merged M2 (and then M3) before pushing.

M3 imports from existing `build/scripts/validate_marketplace_counts.py` (no new script).

---

