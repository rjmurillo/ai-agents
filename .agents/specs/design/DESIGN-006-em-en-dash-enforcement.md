---
type: design
id: DESIGN-006
title: Em/en-dash prohibition enforcement
status: draft
priority: P1
related:
  - REQ-006
  - issue: 1923
adr: []
author: spec-agent
created: 2026-05-09
updated: 2026-05-09
---

# DESIGN-006: Em/en-dash prohibition enforcement

## Requirements Addressed

- REQ-006-AC1: Pre-commit hook blocks em-dash in staged files
- REQ-006-AC2: Pre-commit hook blocks en-dash in staged files
- REQ-006-AC3: Commit-msg hook blocks dashes in commit message body
- REQ-006-AC4: Dash check applies to `.github/instructions/` staged files
- REQ-006-AC5: Hook skips vendored paths
- REQ-006-AC6: Hook skips merge commits
- REQ-006-AC7: `pre_pr.py` reports branch-wide dash violations
- REQ-006-AC8: `universal.md` rule propagates to Copilot mirror
- REQ-006-AC9: Regression test confirms hook blocks fixture with dashes
- REQ-006-AC10: Regression test confirms hook passes clean fixture
- REQ-006-AC11: Test verifies both source and mirror trees are checked

## Design Overview

Four deliverables close the em/en-dash gap at three enforcement points. A bash section added
to the existing `.githooks/pre-commit` hook detects U+2014 and U+2013 in staged `*.md` files
and blocks the commit. A new `.githooks/commit-msg` bash hook detects dashes in draft commit
messages. A new `validate_dash_prohibition()` Python function in `scripts/validation/pre_pr.py`
performs branch-wide detection before push. A one-line MUST NOT rule added to
`.claude/rules/universal.md` (then regenerated into the Copilot mirror) prevents authoring
dashes. Regression tests under `tests/hooks/` cover positive, negative, and edge cases.

## Component Architecture

### Component 1: Bash section in `.githooks/pre-commit`

**Location**: `.githooks/pre-commit` (existing file, new section added after markdown lint)

**Purpose**: Block staged commits that contain U+2014 or U+2013 in `*.md` files.

**Why bash, not Python**: `.githooks/` scripts are the declared ADR-042 exception. The existing
pre-commit hook is bash. Adding a 15-line bash section follows the established pattern. A
separate Python module would add subprocess latency on every commit.

**Canonical source mirror** (per `.claude/rules/canonical-source-mirror.md`):

The new section reuses two variables already defined in `.githooks/pre-commit`:

- Line 136-144: `IS_MERGE=0` / `IS_MERGE=1`, computed from `[ -f "$REPO_ROOT/.git/MERGE_HEAD" ]`.
- Line 186: `STAGED_MD_FILES=$(echo "$STAGED_FILES" | grep -E '\.md$' || true)`.

The `MD_FILES` bash array exists only inside the markdown-lint block (line 254-258) and is
not visible at the dash-check site. Use `STAGED_MD_FILES` (newline-delimited string) instead
and iterate it with `while IFS= read -r`.

**Responsibilities**:

- Skip if merge commit (`if [ "$IS_MERGE" = "1" ]; then exit early`).
- Iterate `STAGED_MD_FILES` (already computed at line 186; newline-delimited).
- Filter out paths matching `node_modules/`, `.venv/`, `.serena/cache/` prefix (REQ-006-AC5).
  Do NOT filter `.github/instructions/` (REQ-006-AC4).
- Run `LC_ALL=C.UTF-8 grep -lI` with the literal em-dash and en-dash bytes across the
  filtered file list. Use `-I` to skip binary files, `-l` for file-name-only output.
- If violations found: call `record_fail` with each offending file name and the fix instruction.
- Fix instruction text (verbatim): "replace U+2014 with comma, period, or colon; replace
  U+2013 with hyphen in numeric ranges; or restructure the sentence."
- If no violations: call `record_pass`.

**Interfaces**:

- Input: `STAGED_MD_FILES` (newline-delimited string already computed by line 186).
- Output: `record_fail`/`record_pass` calls following existing hook pattern; exit code
  contributed via `EXIT_STATUS` accumulator (per existing hook behavior).

**Locale safety**: Prefix grep with `LC_ALL=C.UTF-8` to ensure UTF-8 byte matching works on
both GNU grep (Linux) and BSD grep (macOS) regardless of the user's default locale.

**Rough implementation**:

```bash
# Em/en-dash prohibition (Issue #1923, REQ-006-AC1, REQ-006-AC2)
# Reuses STAGED_MD_FILES (line 186) and IS_MERGE (line 136-139) from this hook.
if [ "$IS_MERGE" != "1" ] && [ -n "$STAGED_MD_FILES" ]; then
    DASH_HITS=""
    while IFS= read -r file; do
        [ -z "$file" ] && continue
        case "$file" in
            node_modules/*|.venv/*|.serena/cache/*) continue ;;
        esac
        if LC_ALL=C.UTF-8 grep -qI $'[\xe2\x80\x93\xe2\x80\x94]' "$file" 2>/dev/null; then
            DASH_HITS="$DASH_HITS $file"
        fi
    done <<< "$STAGED_MD_FILES"
    if [ -n "$DASH_HITS" ]; then
        record_fail "Em/en-dash prohibition"
        echo_info "  Files:$DASH_HITS"
        echo_info "  Fix: replace U+2014 with comma/period/colon; U+2013 with hyphen; or restructure."
    else
        record_pass "Em/en-dash prohibition"
    fi
fi
```

### Component 2: `.githooks/commit-msg` (standard git hook)

**Location**: `.githooks/commit-msg` (new file, bash, executable)

**Purpose**: Block commit messages that contain U+2014 or U+2013.

**Why `.githooks/commit-msg` not `.claude/hooks/commit-msg/`**: `.githooks/commit-msg` is a
standard git hook that fires for ALL git commits (human, Claude Code via Bash, CI). Claude
Code's `settings.json` hook system (PreToolUse, PostToolUse, etc.) is independent and does
not support a `commit-msg` event type. The standard git hook is the correct mechanism.

**Responsibilities**:

- Accept `$1` (the draft commit message file path) from git.
- Grep the file for U+2014 or U+2013 with `LC_ALL=C.UTF-8 grep`.
- If found: print violation message to stderr, exit 1.
- If not found: exit 0.

**Violation message text** (verbatim): "commit message contains em/en-dash; replace with
comma, period, hyphen, or restructure the sentence."

**Interfaces**:

- Input: `$1` (path to draft commit message file, provided by git).
- Output: stderr violation message; exit code 0 (pass) or 1 (violation).

**Rough implementation**:

```bash
#!/usr/bin/env bash
COMMIT_MSG_FILE="$1"
if LC_ALL=C.UTF-8 grep -qI $'[\xe2\x80\x93\xe2\x80\x94]' "$COMMIT_MSG_FILE" 2>/dev/null; then
    echo "ERROR: commit message contains em/en-dash; replace with comma, period, hyphen, or restructure the sentence." >&2
    exit 1
fi
exit 0
```

### Component 3: `validate_dash_prohibition()` in `pre_pr.py`

**Location**: `scripts/validation/pre_pr.py` (existing file, new function)

**Purpose**: Catch dashes committed to the branch before the hook was installed.

**Responsibilities**:

- Determine the merge-base using the same fallback chain as
  `.claude/hooks/PreToolUse/push_guard_base.py:_detect_default_base_ref` (line 328-368):
  prefer `@{u}` (per-branch upstream), fall back to `refs/remotes/origin/HEAD`, last resort
  is `origin/main`. Then run `git diff <merge-base>...HEAD --name-only` for the branch-diff
  file list.
- Filter to `*.md` files.
- Skip vendored paths (`node_modules/`, `.venv/`, `.serena/cache/`).
- For each remaining file, read and search for U+2014 or U+2013.
- Return `bool` (False on any violation, True on clean), matching the existing pattern of
  `validate_session_end`, `validate_pester_tests`, `validate_markdown_lint`, etc.
  (`scripts/validation/pre_pr.py:177, 202, 217`).

**Integration**: The existing `pre_pr.py` check-runner calls `validate_dash_prohibition()`
alongside the other `validate_*` functions. The runner translates `False` returns to exit
code 1 (logic) per the established pattern; git subprocess failures translate to exit code 2
(config) per AGENTS.md exit-code contract (`pre_pr.py:594, 725`).

### Component 4: `universal.md` rule addition and mirror propagation

**Location**: `.claude/rules/universal.md` (MUST NOT section)

**Purpose**: Prevent AI agents from authoring dashes in the first place.

**Rule text to add** (in the MUST NOT section, after existing entries):

```
N. MUST NOT use em-dashes (U+2014) or en-dashes (U+2013) in any authored text. Use commas,
   periods, colons, hyphens, or restructure the sentence.
```

**Mirror propagation**: After editing `universal.md`, run `python3 build/scripts/build_all.py`
to regenerate `.github/instructions/universal.instructions.md`. Verify with
`python3 build/scripts/build_all.py --check` (exits 0 when mirror is current).

### Component 5: Regression tests

**Location**: `tests/hooks/test_dash_guard.py` and `tests/hooks/fixtures/`

**Purpose**: Machine-verify positive, negative, merge-skip, vendor-skip, and dual-tree cases.

**Test cases required**:

| Test name | Fixture | Expected exit |
|-----------|---------|---------------|
| `test_em_dash_blocked` | `fixtures/dash_violations.md` (contains U+2014) | non-zero |
| `test_en_dash_blocked` | `fixtures/dash_violations.md` (contains U+2013) | non-zero |
| `test_clean_passes` | `fixtures/no_dash_clean.md` | zero |
| `test_instructions_tree_blocked` | `fixtures/instructions_tree/dash_violations.md` | non-zero |
| `test_vendor_skipped` | `fixtures/node_modules/dash_violations.md` | zero |
| `test_merge_commit_skipped` | any fixture; MERGE_HEAD env present | zero |
| `test_empty_staged_passes` | empty staged list | zero |
| `test_commit_msg_blocked` | message file with U+2014 | non-zero |
| `test_commit_msg_clean` | message file without dashes | zero |

## Technology Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Pre-commit detection | Bash grep section in `.githooks/pre-commit` | Follows existing hook patterns, no Python subprocess latency, declared ADR-042 exception |
| Commit-msg detection | Bash grep in `.githooks/commit-msg` (new file) | Standard git hook, fires for all commits regardless of client (human, agent, CI) |
| Locale safety | `LC_ALL=C.UTF-8` prefix on grep | Ensures UTF-8 byte matching on both GNU and BSD grep |
| Branch-diff scan | Python `re` inside `pre_pr.py` `validate_dash_prohibition()` | Consistent with existing validator pattern in `pre_pr.py` |
| Mirror propagation | `build/scripts/build_all.py` (existing) | Canonical generator; no new tooling |
| Hook fail-open | Exit 0 on unhandled exception | Consistent with all existing hooks in repo |
| Merge-commit skip | `git rev-parse -q --verify MERGE_HEAD` | Canonical pattern already in repo hooks |
| Vendor exclusion | Prefix filter in Python before grep | Simpler and more testable than `grep --exclude-dir` in subprocess |

## Security Considerations

- Input: local repo file contents only (trusted boundary). No network calls.
- Shell injection (CWE-78): pre-commit uses bash array iteration (no shell interpolation of
  filenames). pre_pr.py uses Python list (no shell). commit-msg hook receives `$1` from git
  (not user-supplied).
- Path traversal (CWE-22): hook reads only files returned by `git diff --cached`; no
  user-supplied paths are opened directly.
- Binary files: `grep -I` skips binary files.
- No secrets involved.

## Testing Strategy

- Pre-commit and commit-msg hooks are bash. Integration tests run the hook against fixture files
  via `bash -c` or by invoking the script directly.
- `validate_dash_prohibition()` in pre_pr.py is Python. Unit tests use pytest 8+ with mocked
  subprocess calls for git diff.
- Fixtures are static files in `tests/hooks/fixtures/`. Each fixture is committed with its
  expected behavior documented in a comment at the top of the test file.
- Coverage target: 80% business logic per AGENTS.md.

## Open Questions

None. The commit-msg hook placement is resolved: `.githooks/commit-msg` is a standard git hook
independent of Claude Code's hook system. It fires for all git commits regardless of client.
