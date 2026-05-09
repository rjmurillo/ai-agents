---
type: task
id: TASK-006
title: Implement em/en-dash prohibition enforcement
status: todo
priority: P1
complexity: M
related:
  - DESIGN-006
  - REQ-006
blocked_by: []
blocks: []
assignee: implementer
created: 2026-05-09
updated: 2026-05-09
---

# TASK-006: Implement em/en-dash prohibition enforcement

## Objective

Add four enforcement points that prevent em-dashes (U+2014) and en-dashes (U+2013) from
reaching bot reviewers: a pre-commit hook for staged files, a commit-msg hook for draft
messages, a branch-wide check in `pre_pr.py`, and a prohibition rule in `universal.md` with
mirror propagation. Deliver in sequence M1 through M4 because M3 modifies `hooks.json` and M4
modifies `pre_pr.py`; parallel execution would cause merge conflicts.

## In Scope

- Bash section in `.githooks/pre-commit`: staged-file dash check
- `.githooks/commit-msg`: new bash hook for commit message dash check
- `validate_dash_prohibition()` function in `scripts/validation/pre_pr.py`
- MUST NOT rule addition to `.claude/rules/universal.md`
- Mirror regeneration via `build/scripts/generate_rules.py`
- Regression tests under `tests/hooks/test_dash_guard.py`
- Test fixtures under `tests/hooks/fixtures/`

## Out of Scope

- Retroactive cleanup of files with existing dashes
- CI-level GitHub Actions enforcement (deferred)
- Windows-native hook support
- `~/.claude/CLAUDE.md` (already done)
- `node_modules/`, `.venv/`, `.serena/cache/` remediation

---

## Milestone M1: universal.md rule and mirror propagation

### TASK-006-1: Add MUST NOT prohibition to universal.md and regenerate mirror

**Objective**: Surface the prohibition to all AI agents reading either the Claude-source or
Copilot-mirror tree. This is M1 because it is the lowest-risk, zero-hook change and unblocks
agents from learning the rule before other milestones land.

**Complexity**: XS (1-2 hours)

**AC traceability**: REQ-006-AC8

**Files affected**:

| File | Action | Description |
|------|--------|-------------|
| `.claude/rules/universal.md` | Edit | Add MUST NOT entry prohibiting U+2014 and U+2013 in the MUST NOT section |
| `.github/instructions/universal.instructions.md` | Regenerate | Run `python3 build/scripts/generate_rules.py` after editing source |

**Acceptance Criteria**

- [ ] `.claude/rules/universal.md` MUST NOT section contains an entry prohibiting U+2014 and
  U+2013 with the replacement guidance (comma, period, colon, hyphen, or restructure).
- [ ] `python3 build/scripts/generate_rules.py` exits 0 after the edit.
- [ ] `git diff .github/instructions/universal.instructions.md` shows the new MUST NOT rule
  added (confirms mirror was regenerated and reflects the source change).
- [ ] The prohibition text in the mirror matches the source verbatim.

**Implementation Notes**

Add after the last existing MUST NOT bullet. Rule text:

> MUST NOT use em-dashes (U+2014) or en-dashes (U+2013) in any authored text. Use commas,
> periods, colons, hyphens, or restructure the sentence instead.

Run `python3 build/scripts/generate_rules.py` immediately after saving. Verify with
`git diff .github/instructions/universal.instructions.md`. Do not hand-edit the generated
`.github/instructions/universal.instructions.md`.

---

## Milestone M2: Regression test fixtures and test skeleton

### TASK-006-2: Create test fixtures and test skeleton

**Objective**: Create the fixtures and empty test file that M3 will populate with assertions.
Landing fixtures first keeps M3 focused on hook code only.

**Complexity**: XS (1-2 hours)

**AC traceability**: REQ-006-AC9, REQ-006-AC10, REQ-006-AC11

**Files affected**:

| File | Action | Description |
|------|--------|-------------|
| `tests/hooks/__init__.py` | Create (if absent) | Python package marker |
| `tests/hooks/fixtures/dash_violations.md` | Create | Contains at least one U+2014 and one U+2013 |
| `tests/hooks/fixtures/no_dash_clean.md` | Create | Contains no U+2014 or U+2013 |
| `tests/hooks/fixtures/instructions_tree/dash_violations.md` | Create | Simulates `.github/instructions/` tree; contains U+2014 |
| `tests/hooks/fixtures/node_modules/dash_violations.md` | Create | Simulates vendored path; contains U+2014 |
| `tests/hooks/test_dash_guard.py` | Create | Test skeleton with imports, fixture references, and test stubs |

**Acceptance Criteria**

- [ ] `dash_violations.md` contains literal U+2014 and U+2013 characters in its body
  (verifiable via `grep -P '\xe2\x80\x94' fixture` and `grep -P '\xe2\x80\x93' fixture`).
- [ ] `no_dash_clean.md` contains neither U+2014 nor U+2013.
- [ ] `instructions_tree/dash_violations.md` contains literal U+2014.
- [ ] `node_modules/dash_violations.md` contains literal U+2014.
- [ ] The test file imports are valid Python and `pytest --collect-only` finds the stubs without
  errors.

**Implementation Notes**

Fixture files must contain literal U+2014 and U+2013 bytes to exercise the detection logic.
Generate fixture content programmatically with Python escape sequences (so this spec file
itself does not contain the prohibited characters):

```python
# In a setup helper or a one-shot script that creates the fixtures.
# Use Unicode escape sequences so this source file does not contain the prohibited bytes;
# the encoded output of write_text() is what carries the literal U+2014 and U+2013.
content = (
    "# Fixture: dash violations\n\n"
    "This sentence contains an em-dash \u2014 used incorrectly.\n"
    "This range uses an en-dash \u2013 also prohibited.\n"
)
fixture_path.write_text(content, encoding="utf-8")
```

Verify fixtures after creation:

```bash
LC_ALL=C.UTF-8 grep -qI $'[\xe2\x80\x93\xe2\x80\x94]' tests/hooks/fixtures/dash_violations.md
```

---

## Milestone M3: Hook implementation and test assertions

### TASK-006-3: Add dash check section to `.githooks/pre-commit`

**Objective**: Add a bash section to the existing pre-commit hook that blocks staged `*.md`
files containing U+2014 or U+2013.

**Complexity**: S (2-4 hours)

**AC traceability**: REQ-006-AC1, REQ-006-AC2, REQ-006-AC4, REQ-006-AC5, REQ-006-AC6,
REQ-006-AC9, REQ-006-AC10, REQ-006-AC11

**Files affected**:

| File | Action | Description |
|------|--------|-------------|
| `.githooks/pre-commit` | Edit | Add dash check section after markdown lint section |
| `tests/hooks/test_dash_guard.py` | Edit | Add integration test assertions |

**Acceptance Criteria**

- [ ] Pre-commit hook exits 1 (via `record_fail`) when a staged `*.md` file contains U+2014.
- [ ] Pre-commit hook exits 1 when a staged `*.md` file contains U+2013.
- [ ] Pre-commit hook records pass when no staged `*.md` files contain dashes.
- [ ] Pre-commit hook skips the check when `IS_MERGE=1` (canonical variable defined at
  `.githooks/pre-commit:136-139`).
- [ ] Pre-commit hook skips files under `node_modules/`, `.venv/`, `.serena/cache/`.
- [ ] Pre-commit hook checks files under `.github/instructions/` (not excluded).
- [ ] Output on violation includes the fix instruction.
- [ ] All test cases from `tests/hooks/test_dash_guard.py` pass.

**Implementation Notes**

Add after the markdown lint section. Reuse `STAGED_MD_FILES` (newline-delimited, defined at
`.githooks/pre-commit:186`) and `IS_MERGE` (defined at line 136-139). The `MD_FILES` bash
array exists only inside the markdown-lint block (line 254-258) and is not visible at the new
section site. Pattern:

```bash
# Em/en-dash prohibition (Issue #1923, REQ-006-AC1, REQ-006-AC2)
# Reuses STAGED_MD_FILES (line 186) and IS_MERGE (line 136-139) from this hook.
# Uses bash array (DASH_HITS) so filenames with spaces are preserved through
# iteration. Uses echo_error + EXIT_STATUS=1 (canonical pattern; no record_fail
# helper exists in this hook, contrary to early spec text).
if [ "$IS_MERGE" != "1" ] && [ -n "$STAGED_MD_FILES" ]; then
    DASH_HITS=()
    while IFS= read -r dash_file; do
        [ -z "$dash_file" ] && continue
        case "$dash_file" in
            node_modules/*|.venv/*|.serena/cache/*) continue ;;
        esac
        if [ -f "$dash_file" ] && LC_ALL=C.UTF-8 grep -qI $'[\xe2\x80\x93\xe2\x80\x94]' "$dash_file" 2>/dev/null; then
            DASH_HITS+=("$dash_file")
        fi
    done <<< "$STAGED_MD_FILES"
    if [ ${#DASH_HITS[@]} -gt 0 ]; then
        echo_error "Em/en-dash prohibition violated"
        echo_info "  Files containing U+2014 (em-dash) or U+2013 (en-dash):"
        for hit in "${DASH_HITS[@]}"; do
            echo_info "    $hit"
        done
        echo_info "  Fix: replace U+2014 with comma/period/colon; U+2013 with hyphen; or restructure."
        EXIT_STATUS=1
    fi
fi
```

Locale safety: `LC_ALL=C.UTF-8` ensures UTF-8 matching on both GNU and BSD grep.

**Testing Requirements**

- Integration tests create temp fixture files, stage them, and run the hook section logic
  against `STAGED_MD_FILES` populated with fixture paths.
- Test merge-commit skip by simulating `IS_MERGE=1` (or by creating `.git/MERGE_HEAD`).
- Test vendor exclusion by using a `node_modules/` prefixed path.

---

### TASK-006-4: Create `.githooks/commit-msg` hook

**Objective**: Create a standard git commit-msg hook that blocks commit messages containing
U+2014 or U+2013.

**Complexity**: XS (1-2 hours)

**AC traceability**: REQ-006-AC3

**Files affected**:

| File | Action | Description |
|------|--------|-------------|
| `.githooks/commit-msg` | Create | Bash commit-msg hook (executable) |
| `tests/hooks/test_dash_guard.py` | Edit | Add commit-msg test assertions |

**Acceptance Criteria**

- [ ] `.githooks/commit-msg` exists and is executable.
- [ ] The hook exits 1 when the draft message file contains U+2014.
- [ ] The hook exits 1 when the draft message file contains U+2013.
- [ ] The hook exits 0 when the draft message file contains neither.
- [ ] Stderr output on violation contains: "commit message contains em/en-dash; replace with
  comma, period, hyphen, or restructure the sentence."
- [ ] All test cases pass.

**Implementation Notes**

```bash
#!/usr/bin/env bash
# commit-msg hook: em/en-dash prohibition (Issue #1923, REQ-006-AC3)
# Standard git hook. Fires for all git commits (human, agent, CI).
COMMIT_MSG_FILE="$1"
if LC_ALL=C.UTF-8 grep -qI $'[\xe2\x80\x93\xe2\x80\x94]' "$COMMIT_MSG_FILE" 2>/dev/null; then
    echo "ERROR: commit message contains em/en-dash; replace with comma, period, hyphen, or restructure the sentence." >&2
    exit 1
fi
exit 0
```

---

## Milestone M4: Branch-wide pre_pr.py check

### TASK-006-5: Add `validate_dash_prohibition()` to `pre_pr.py`

**Objective**: Catch dashes on the branch that were committed before the hook was installed.

**Complexity**: S (2-4 hours)

**AC traceability**: REQ-006-AC7

**Files affected**:

| File | Action | Description |
|------|--------|-------------|
| `scripts/validation/pre_pr.py` | Edit | Add `validate_dash_prohibition()` function and call it from the main check runner |
| `tests/validation/test_pre_pr.py` | Edit (or create) | Add tests for `validate_dash_prohibition()` positive, negative, and empty-diff cases |

**Acceptance Criteria**

- [ ] `validate_dash_prohibition()` function exists in `pre_pr.py`.
- [ ] The function uses the pre-push ref detection fallback chain (`@{u}` then
  `refs/remotes/origin/HEAD` then `origin/main`) to determine the merge-base, then runs
  `git diff <merge-base>...HEAD --name-only`.
- [ ] The function filters to `*.md` files and excludes vendored paths.
- [ ] The function returns `False` (matching existing `validate_*` pattern in pre_pr.py:177)
  when any file contains U+2014 or U+2013, with structured output listing offending files.
- [ ] The function returns `True` when no `*.md` files in the branch diff contain dashes.
- [ ] `pre_pr.py` calls `validate_dash_prohibition()` as part of its standard check suite.
- [ ] Tests cover: violations found (returns False), clean branch (returns True), empty
  diff (returns True), git command failure (raises subprocess error which the runner
  translates to exit 2 per AGENTS.md exit-code contract; pre_pr.py:594).
- [ ] All new tests pass in CI.

**Implementation Notes**

Follow the existing `validate_*` function pattern (see `validate_session_end` at pre_pr.py:177
or `validate_markdown_lint` at pre_pr.py:217). Signature:
`def validate_dash_prohibition(repo_root: Path) -> bool:`. Return False on violations, True
on clean. The runner at the bottom of `pre_pr.py` translates False to exit 1.

Use Python `re.search(r'[\u2013\u2014]', content)` on each file's text (escape form keeps
the prohibited characters out of source files). Emit violation lines in the same structured
format as other checks (see `validate_design_review_frontmatter` at pre_pr.py:391 for an
example of structured output with file:line evidence).

Exit code contract per AGENTS.md and pre_pr.py:594, 725: 0 = pass, 1 = logic (violations
found), 2 = config (git subprocess failure).

---

## Sequencing

```
M1 (universal.md rule)
  |
  v
M2 (fixtures and test skeleton)
  |
  v
M3 (pre-commit section + .githooks/commit-msg + test assertions)
  |
  v
M4 (pre_pr.py validate_dash_prohibition)
```

M1 and M2 can land in the same PR. M3 and M4 must be separate commits because they touch
different files and `hooks.json` is modified only in M3.

## Effort Estimate

| Milestone | Tasks | Complexity | Estimated Hours |
|-----------|-------|------------|----------------|
| M1 | TASK-006-1 | XS | 1-2 |
| M2 | TASK-006-2 | XS | 1-2 |
| M3 | TASK-006-3, TASK-006-4 | S+XS | 3-6 |
| M4 | TASK-006-5 | S | 2-4 |
| **Total** | 5 tasks | M aggregate | **7-14 hours** |
