---
type: design
id: DESIGN-005
title: Pre-push validation hooks for PR iteration cost reduction
status: draft
priority: P1
related:
  - REQ-005
  - issue: 1884
  - issue: 1885
adr: []
author: spec-agent
created: 2026-05-03
updated: 2026-05-04
---

# DESIGN-005: Pre-push validation hooks for PR iteration cost reduction

## Requirements Addressed

- REQ-005-US1: Block markdown style violations pre-push (AC-1, AC-2, AC-3, AC-3a)
- REQ-005-US2: Block marketplace count drift pre-push (AC-4, AC-5, AC-9)
- REQ-005-US3: Block session log placeholder values pre-push (AC-6, AC-7)
- REQ-005-CROSS: Shared hook framework (AC-8, AC-10, AC-11)

## Design Overview

Three new PreToolUse hooks fire on `Bash(git push*)`. Each hook is a thin dispatcher that reads
the changed-file list from `git diff --name-only`, runs a validator only when relevant files are
present, and blocks with exit code 2 on violation. A shared `push_guard_base.py` module owns
changeset reading, output formatting, and the binary-availability check. Each validator body is
a separate function/class injected via the Strategy pattern (CVA from PRD).

## Component Architecture

### Shared framework: `push_guard_base.py`

**Location**: `.claude/hooks/PreToolUse/push_guard_base.py`

**Purpose**: Eliminate duplicate logic across the three push-time validators.

**Responsibilities**:
- Bootstrap the `hook_utilities` lib path (identical to existing hooks; copy the existing
  bootstrap block verbatim to maintain consistency).
- Call `skip_if_consumer_repo(guard_name)` and return 0 if in consumer repo.
- Read stdin JSON, extract `tool_input.command`.
- Run `git diff --name-only @{push}..HEAD` as a subprocess (argument list, no shell, timeout 10s)
  to produce the changed-file list (files committed locally but not yet pushed). If that fails
  (e.g., no upstream configured), fall back to `git diff --name-only origin/main...HEAD`. On
  subprocess failure after fallback, return 0 (fail-open). Note: empty diff is valid (nothing to
  push), so return 0 without running validators.
- Expose `run_guard(validator_fn, globs, name)` where:
  - `globs` is the list of path patterns that activate the validator.
  - `validator_fn(matching_files, all_changed_files) -> list[str]` returns violation lines.
  - `name` is the guard name for logging.
- Print violation lines to stdout (one per line) and return exit code 2 if any violations.
  Print a summary header (`[BLOCKED] <name>: N violation(s)`) followed by each line.
- On any unhandled exception, print to stderr and return 0 (fail-open, consistent with existing
  hooks).

**Interface**:
```python
def run_guard(
    validator_fn: Callable[[list[str], list[str]], list[str]],
    globs: list[str],
    name: str,
) -> int:
    ...
```

**Output format** (mirrors `invoke_session_log_guard.py`):
```
## BLOCKED [E_<CODE>]: <Guard Name>

<violation line 1>
<violation line 2>

Fix and re-push.
```

---

### Hook 1: `invoke_markdownlint_guard.py`

**Location**: `.claude/hooks/PreToolUse/invoke_markdownlint_guard.py`

**Purpose**: Block `git push` when changed `.md` files have markdownlint violations.

**Responsibilities**:
- Activate on glob `*.md`.
- Check `shutil.which("markdownlint-cli2")`. If absent, print WARN to stderr and return 0
  (fail-open, per AC-3). Do not return 2.
- Log the markdownlint-cli2 binary version to stderr (`markdownlint-cli2 --version`) before
  running the validation, per AC-3a, for diagnostic purposes.
- Run `markdownlint-cli2 <file1> <file2> ...` as a subprocess (argument list, no shell,
  timeout 60s). The binary uses the repo's `.markdownlint-cli2.yaml` config automatically when
  run from the repo root.
- Capture stdout/stderr. On non-zero exit, parse violation lines. Each line from
  markdownlint-cli2 is already in `<file>:<line> <rule> <description>` format; pass through
  unchanged.
- On `subprocess.TimeoutExpired`: print prominent stderr warning and return 0 (fail-open).
  Infrastructure latency is not a lint violation and should not block work. The original
  block-on-timeout decision was reversed per pre-mortem mitigation R-H.
- On `OSError` (wrong-architecture binary, missing libs): print stderr warning, return 0
  (fail-open).

**Validator signature**:
```python
def _validate_markdown(md_files: list[str], _all: list[str]) -> list[str]:
    ...
```

---

### Hook 2: `invoke_manifest_count_guard.py`

**Location**: `.claude/hooks/PreToolUse/invoke_manifest_count_guard.py`

**Purpose**: Block `git push` when manifest count fields disagree with the filesystem.

**Responsibilities**:
- Activate on globs: `templates/agents/*.md`, `.claude/skills/*/SKILL.md`,
  `.claude/commands/*.md`, `.claude-plugin/marketplace.json`.
- Add `build/scripts/` to `sys.path` and import
  `validate_marketplace_counts.validate_known_marketplaces(repo_root=project_dir)`.
- On return code 1 (mismatch): capture stdout, format as violation lines,
  append hint "Run `python3 build/scripts/validate_marketplace_counts.py --fix` to auto-correct."
- On return code 2 (config error): produce violation with parse-error message.

**Validator signature**:
```python
def _validate_manifest_counts(_manifest_files: list[str], _all: list[str]) -> list[str]:
    ...
```

---

### Existing script: `build/scripts/validate_marketplace_counts.py`

**Location**: `build/scripts/validate_marketplace_counts.py` (EXISTING, not new)

**Purpose**: Validates marketplace.json description strings contain accurate counts. Already
used in CI via `validate-marketplace-counts.yml`. Config in `templates/marketplace-counters.yaml`.

**Key functions for hook integration**:
- `validate_known_marketplaces(fix=False, repo_root=Path)` returns 0 (match) or 1 (mismatch).
- `parse_counts_from_description(description)` extracts counts via regex.
- `--fix` mode auto-corrects stale counts in descriptions.

**Hook imports this directly.** No new script needed. The hook calls
`validate_known_marketplaces(repo_root=project_dir)` and translates exit code 1 to a block.

**NOTE**: `docs/SEMANTIC_INDEX.yaml` is NOT part of marketplace count validation; it is a
semantic search index, not a count manifest, and is not in scope for this work.

**NOTE**: `pre_pr.py` extension is NOT needed. CI already runs this script via
`validate-marketplace-counts.yml`. The hook provides the pre-push gate.

---

### Hook 3: `invoke_session_log_field_guard.py`

**Location**: `.claude/hooks/PreToolUse/invoke_session_log_field_guard.py`

**Purpose**: Block `git push` when changed session log files have placeholder values.

**Responsibilities**:
- Activate on glob `.agents/sessions/*.json`.
- For each matching file, parse JSON. On parse failure, produce violation line
  `<path>: JSON parse error - <message>` and block.
- Check three fields per AC-6:
  - `schemaVersion` present and non-empty.
  - `endingCommit` present and not the literal string `"pending"`.
  - `markdownLintRun.Complete` is `true` (not `false` or absent) AND
    `markdownLintRun.Evidence` is a non-empty, non-placeholder string.
- Produce violation lines as `<path>:<field> <reason>`.

**Validator signature**:
```python
def _validate_session_log_fields(
    session_files: list[str], all_changed: list[str]
) -> list[str]:
    ...
```

---

## File Layout

```
.claude/hooks/PreToolUse/
    push_guard_base.py                   # NEW: shared framework
    invoke_markdownlint_guard.py         # NEW: US-1
    invoke_manifest_count_guard.py       # NEW: US-2
    invoke_session_log_field_guard.py    # NEW: US-3
    invoke_session_log_guard.py          # EXISTING (not changed)
    invoke_skill_first_guard.py          # EXISTING (not changed)

build/scripts/
    validate_marketplace_counts.py       # EXISTING: imported by manifest count hook

tests/
    hooks/
        test_push_guard_base.py          # NEW: M1
        test_markdownlint_guard.py       # NEW: M2
        test_manifest_count_guard.py     # NEW: M3
        test_session_log_field_guard.py  # NEW: M4

.claude/hooks/hooks.json                # MODIFY: add three new hook entries
```

---

## hooks.json Integration

Append three entries to the existing `Bash(git push*)` matcher block. The existing
`invoke_branch_context_guard.py`, `invoke_branch_protection_guard.py`, and
`invoke_retrospective_gate.py` remain. New hooks are appended after existing ones so that
branch/protection checks run first.

```json
{
  "matcher": "Bash(git push*)",
  "hooks": [
    ... existing entries ...
    {
      "type": "command",
      "command": "python3 -u \"${CLAUDE_PLUGIN_ROOT}/hooks/PreToolUse/invoke_markdownlint_guard.py\"",
      "timeout": 70,
      "statusMessage": "Checking markdownlint violations on changed .md files (BLOCKING)"
    },
    {
      "type": "command",
      "command": "python3 -u \"${CLAUDE_PLUGIN_ROOT}/hooks/PreToolUse/invoke_manifest_count_guard.py\"",
      "statusMessage": "Checking manifest count drift (BLOCKING)"
    },
    {
      "type": "command",
      "command": "python3 -u \"${CLAUDE_PLUGIN_ROOT}/hooks/PreToolUse/invoke_session_log_field_guard.py\"",
      "statusMessage": "Checking session log placeholder values (BLOCKING)"
    }
  ]
}
```

The `timeout: 70` on the markdownlint hook accounts for the 60s subprocess timeout plus 10s
hook overhead. Other two hooks have no explicit timeout (default 30s is sufficient).

---

## Existing Patterns to Mirror

Both `invoke_session_log_guard.py` and `invoke_skill_first_guard.py` establish the template:

1. **Bootstrap block** (the comment-and-code block at lines 26-49 of
   `invoke_session_log_guard.py` at this PR's HEAD): walk up from `__file__` looking for
   `.claude-plugin/plugin.json`. Copy verbatim into each new hook. Re-confirm exact line range
   when implementing in case the file has changed.
2. **`skip_if_consumer_repo(guard_name)`**: first call in `main()`, returns 0 if in consumer
   repo. All new hooks call this.
3. **`sys.stdin.isatty()` guard**: return 0 early if no stdin pipe.
4. **`hook_input.get("tool_input")`**: extract command from the standardized JSON envelope.
5. **Fail-open on unhandled exception**: `except Exception as exc: print(..., file=sys.stderr); return 0`.
6. **Exit codes**: 0 = allow, 2 = block. (Exempt from ADR-035 per hook semantics comment.)
7. **Output format**: `## BLOCKED [E_CODE]: Title` on stdout, brief stderr line with error code.

The `push_guard_base.py` module formalizes items 1-6 so each hook body contains only the
validator-specific logic.

---

## Technology Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Subprocess call style | Argument list, no `shell=True` | CWE-78 mitigation; matches `pre_pr.py` pattern |
| markdownlint-cli2 absence handling | WARN + allow | Tooling gap != code problem; AC-3 |
| Changeset source | `git diff --name-only @{push}..HEAD` (fallback: `origin/main...HEAD`) | Committed but not-yet-pushed files; per ADR-043 |
| Count SoR | Filesystem globs (via existing validator) | Per `.claude/rules/templates.md` and PRD Data model |
| Framework pattern | Strategy (CVA) | Three validators share identical shell; differ only in body |
| Manifest count validation | Reuse existing `build/scripts/validate_marketplace_counts.py` | DRY; already runs in CI |
| Timeout (markdownlint) | 60s subprocess, 70s hook, fail-open on timeout | Large changeset upper bound; CI runner latency under load is infrastructure noise, not a lint violation. See PLAN-1884 R-H. |
| Glob matching | Prefix+suffix string check for multi-segment patterns | `fnmatch.fnmatch` and `pathlib.match` both fail to match `.claude/skills/foo/SKILL.md` against `.claude/skills/*/SKILL.md`. Pre-mortem mitigation R-E. |
| Marketplace validator import | Always pass `repo_root=project_dir` explicitly to `validate_known_marketplaces` | Validator's module-level `REPO_ROOT` resolves at import time and is fragile under alternate `sys.path`. Pre-mortem mitigation R-F. |

---

## Security Considerations

- All subprocess calls use argument lists. `shell=False` is the default; do not pass `shell=True`.
- File paths come from `git diff --name-only`. These are repo-relative paths. Resolve against
  the project root, not CWD, to prevent path traversal if CWD differs.
- No network calls. No secrets. No PII.
- All file access is read-only.
- The hooks invoke `validate_marketplace_counts.py` without `--fix`; that mode (which writes)
  is reserved for the agent to invoke explicitly when fixing a flagged drift.

---

## Testing Strategy

Each AC maps to at least one pytest test file. Test files live under `tests/hooks/`.

| AC | Test file | Cases |
|----|-----------|-------|
| AC-1, AC-2 | `test_markdownlint_guard.py` | positive (clean files pass), negative (violation blocks) |
| AC-3 | `test_markdownlint_guard.py` | binary absent -> WARN + allow; subprocess timeout -> WARN + allow (fail-open per pre-mortem R-H); OSError -> WARN + allow |
| AC-4, AC-5 | `test_manifest_count_guard.py` | counts match pass, agent count mismatch blocks, skill count mismatch blocks, config error blocks, repo_root forwarded explicitly |
| AC-6, AC-7 | `test_session_log_field_guard.py` | all fields valid pass, pending endingCommit blocks, missing schemaVersion blocks, markdownLintRun.Complete=false blocks, empty Evidence blocks, short Evidence (<20 chars) blocks, placeholder Evidence ("none", ".") blocks, malformed JSON blocks |
| AC-8 | All three test files | empty changeset exits 0 without subprocess |
| AC-9 | (existing tests in `tests/` for the marketplace-counts validator) | Already covered |
| AC-10 | All test files | coverage >= 80% asserted by `pytest --cov-fail-under=80` in M1 test setup; CI threshold enforcement (workflow change) is deferred |
| AC-11 | `test_push_guard_base.py` | hooks.json matcher equals `Bash(git push*)` exactly |
| shared framework | `test_push_guard_base.py` | consumer repo skip, empty stdin, exception fail-open, `@{push}..HEAD` fallback to `origin/main...HEAD`, double-fallback returns 0 |

Tests mock `subprocess.run` and filesystem I/O. No real git repo required in unit tests.
Integration smoke test (optional M5) exercises the full hook against a temporary git repo.

---

## Open Questions

None. All confirmed during the interview at
`.agents/specs/interviews/INTERVIEW-1884-pr-iteration-cost.md` and during gap-analysis,
pre-mortem, and decision-critic review.
