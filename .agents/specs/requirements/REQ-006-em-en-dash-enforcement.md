---
type: requirement
id: REQ-006
title: Em/en-dash prohibition enforcement
status: draft
priority: P1
category: developer-experience
epic: shift-left-validation
related:
  - DESIGN-006
  - TASK-006
issue: 1923
author: spec-agent
created: 2026-05-09
updated: 2026-05-09
---

# REQ-006: Em/en-dash prohibition enforcement

## Problem

Em-dashes (U+2014) and en-dashes (U+2013) appear in agent-authored prose despite a stated
project prohibition. Each occurrence triggers a bot reviewer thread on the PR, and each thread
costs at least one commit round-trip to resolve. Four enforcement placements close the gap:

1. A pre-commit hook blocks dashes at commit time for staged files.
2. A commit-msg hook blocks dashes in commit message bodies.
3. A branch-wide check in `pre_pr.py` catches dashes committed before the hook was installed.
4. A `universal.md` rule addition prevents authoring dashes in the first place.

Success metric: zero em/en-dash bot reviewer threads on PRs merged after this feature lands.

## User Stories and Requirements

### REQ-006-AC1: Pre-commit hook blocks em-dash in staged files

**Requirement Statement**

WHEN a human or agent runs `git commit` on a branch with at least one staged `*.md` file
containing U+2014
THE SYSTEM SHALL exit 1 and print the file name(s) and a fix instruction to stderr
SO THAT the author can fix the dash before the commit is created.

**Context**

The pre-commit hook runs against staged files. The dash-check section reuses
`STAGED_MD_FILES` (newline-delimited string built at `.githooks/pre-commit:186`) and the
`IS_MERGE` flag (set at `.githooks/pre-commit:136-139` from `[ -f "$REPO_ROOT/.git/MERGE_HEAD" ]`).
Iteration uses `while IFS= read -r ... <<< "$STAGED_MD_FILES"` to handle filenames safely
(no word-splitting). `grep -I` skips binary files and `LC_ALL=C.UTF-8` ensures UTF-8 byte
matching on both GNU grep (Linux) and BSD grep (macOS).

**Acceptance Criteria**

- [ ] WHEN at least one staged `*.md` file contains U+2014, the hook exits 1 (logic error per
  AGENTS.md exit-code contract).
- [ ] The hook prints each offending file name and a fix instruction to stderr.
- [ ] The fix instruction reads: "replace U+2014 with comma, period, or colon; U+2013 with
  hyphen in numeric ranges; or restructure the sentence."
- [ ] The hook does not create the commit when violations are found.

**Rationale**

Em-dashes trigger bot reviewer threads. Blocking at commit time is zero-cost when the staged
set has no dashes and a one-process check when it does.

**Dependencies**

- `git diff --cached --name-only -z` for staged file list
- `grep` with `-I` flag (binary skip) and `-l` flag (file-name-only output)
- pre-commit hook infrastructure (`.githooks/pre-commit`, the repo's standard git hook)

---

### REQ-006-AC2: Pre-commit hook blocks en-dash in staged files

**Requirement Statement**

WHEN a human or agent runs `git commit` on a branch with at least one staged `*.md` file
containing U+2013
THE SYSTEM SHALL behave identically to REQ-006-AC1
SO THAT en-dashes receive the same enforcement as em-dashes.

**Context**

En-dashes (U+2013) are prohibited alongside em-dashes (U+2014). The same grep pattern covers
both code points in a single pass.

**Acceptance Criteria**

- [ ] WHEN at least one staged `*.md` file contains U+2013, the hook exits 1.
- [ ] The hook prints each offending file name and a fix instruction to stderr.
- [ ] Both U+2014 and U+2013 are detected in a single hook invocation (one grep pass).

**Rationale**

En-dashes are equally prohibited. Detecting both in one pass avoids a second subprocess.

**Dependencies**

- Same as REQ-006-AC1.

---

### REQ-006-AC3: Commit-msg hook blocks dashes in commit message body

**Requirement Statement**

WHEN a human or agent runs `git commit -m "message -- body"` where the message body contains
U+2014
THE SYSTEM SHALL exit non-zero via the commit-msg hook
SO THAT dash-bearing commit messages never reach the git log.

**Context**

The commit-msg hook reads the draft message from the file path passed as `$1`. It greps that
file for U+2014 or U+2013 and exits non-zero if either is found. The subject line and body are
both checked; no exemption for the subject.

**Acceptance Criteria**

- [ ] WHEN the commit message file contains U+2014, the commit-msg hook exits non-zero.
- [ ] WHEN the commit message file contains U+2013, the commit-msg hook exits non-zero.
- [ ] WHEN the commit message file contains neither, the hook exits zero.
- [ ] The hook prints an instruction to stderr on violation: "commit message contains em/en-dash;
  replace with comma, period, hyphen, or restructure."

**Rationale**

Commit messages containing dashes embed the prohibited character permanently in the git log.
Blocking at commit-msg hook time is the only interception point before the log is written.

**Dependencies**

- commit-msg hook receiving the draft message file path as `$1`
- `grep` for U+2014 and U+2013

---

### REQ-006-AC4: Dash check applies to .github/instructions/ staged files

**Requirement Statement**

WHEN a staged file is in `.github/instructions/`
THE SYSTEM SHALL apply the dash check to it (not exempt it)
SO THAT dashes in the Copilot-mirror tree are blocked identically to dashes in the
Claude-source tree.

**Context**

`.github/instructions/` contains Copilot-mirror copies of `.claude/rules/` files generated by
`build/scripts/generate_rules.py` (canonical rule-file generator; verified by reading the
script). These files are as authoritative as their source and must meet the same style rules.

**Acceptance Criteria**

- [ ] Staged files under `.github/instructions/` are included in the grep pass, not excluded.
- [ ] A regression test fixture placed under `.github/instructions/` produces the same
  non-zero exit result as an identical fixture under `.claude/rules/`.

**Rationale**

The mirror tree is read by Copilot CLI agents. Dashes there generate the same bot threads.

**Dependencies**

- Same as REQ-006-AC1.

---

### REQ-006-AC5: Hook skips vendored paths

**Requirement Statement**

WHEN a staged file is in `node_modules/`, `.venv/`, or `.serena/cache/`
THE SYSTEM SHALL skip it
SO THAT vendored content does not produce false positives.

**Context**

Vendored directories are not authored content. Checking them produces noise and may block
legitimate commits that happen to stage package lock updates.

**Acceptance Criteria**

- [ ] Files under `node_modules/`, `.venv/`, and `.serena/cache/` are excluded from the grep
  pass.
- [ ] A regression test fixture that stages a file under `node_modules/` confirms exit zero.

**Rationale**

Vendored files are not under the author's style control.

**Dependencies**

- Path-exclusion logic in the staged-file filter (grep `--exclude-dir` or equivalent prefix
  filter in Python).

---

### REQ-006-AC6: Hook skips merge commits

**Requirement Statement**

WHEN the commit is a merge commit
THE SYSTEM SHALL skip the dash check
SO THAT merges of already-validated upstream branches are not blocked.

**Context**

Merge commits combine previously validated content. Blocking on merge introduces false positives
for historical content that predates the hook. The existing pre-commit infrastructure in this
repo already detects merge commits; this hook reuses that detection.

**Acceptance Criteria**

- [ ] WHEN `IS_MERGE=1` (set by `.githooks/pre-commit:136-139` from `[ -f "$REPO_ROOT/.git/MERGE_HEAD" ]`),
  the dash-check section runs zero `grep` invocations and contributes nothing to `EXIT_STATUS`.
- [ ] A regression test fixture simulates `IS_MERGE=1` (or creates `.git/MERGE_HEAD`) and confirms
  the hook section returns 0.

**Rationale**

Merge commit content is already committed in the parents. Re-checking it here is wasteful and
can block merges from upstream.

**Dependencies**

- `IS_MERGE` flag set by `.githooks/pre-commit:136-139` (canonical merge detection, file-existence
  check on `$REPO_ROOT/.git/MERGE_HEAD`).

---

### REQ-006-AC7: pre_pr.py reports branch-wide dash violations

**Requirement Statement**

WHEN a developer runs `python3 scripts/validation/pre_pr.py` on a branch that contains any
`*.md` file with U+2014 or U+2013 anywhere on the branch (not just staged)
THE SYSTEM SHALL report a failure
SO THAT dashes committed before the hook was installed are caught before push.

**Context**

The pre-commit hook only covers staged files at commit time. Files with dashes that were
committed before the hook was installed are invisible to the hook but visible on the branch
diff. A new `validate_dash_prohibition()` function in `pre_pr.py` scans `*.md` files in the
branch diff. The base ref is resolved via the canonical fallback chain (`@{u}`,
`refs/remotes/origin/HEAD`, `origin/main`) mirrored from
`.claude/hooks/PreToolUse/push_guard_base.py:_detect_default_base_ref` (lines 328-368).
The function returns `bool` to match the existing `validate_*` pattern at
`scripts/validation/pre_pr.py:177`; the runner translates `False` to process exit code 1
per AGENTS.md.

**Acceptance Criteria**

- [ ] `scripts/validation/pre_pr.py` contains a `validate_dash_prohibition()` function with
  signature `def validate_dash_prohibition(repo_root: Path) -> bool` (matches existing
  `validate_*` pattern at `pre_pr.py:177`).
- [ ] The function uses `re.search(r'[\u2013\u2014]', content)` to detect dashes in each
  branch-diff `*.md` file.
- [ ] WHEN any such file contains a dash, the function returns `False` and prints structured
  output listing offending file:line locations.
- [ ] WHEN no `*.md` files in the branch diff contain dashes, the function returns `True`.
- [ ] `pre_pr.py` calls `validate_dash_prohibition()` from its `main()` runner via
  `run_validation(...)`. The runner translates `False` to process exit code 1 per AGENTS.md.

**Rationale**

Hooks only intercept future commits. Branch-wide validation catches pre-existing violations
before they reach bot reviewers via the PR.

**Dependencies**

- `scripts/validation/pre_pr.py` (existing)
- Base-ref fallback chain from `.claude/hooks/PreToolUse/push_guard_base.py:_detect_default_base_ref`
  (lines 328-368): `@{u}` then `refs/remotes/origin/HEAD` then `origin/main`.
- `git diff <base-ref>...HEAD --name-only` for branch-diff file list.
- Python `re.search(r'[\u2013\u2014]', content)` for detection (escape form keeps the
  source file clean of the prohibited characters).

---

### REQ-006-AC8: universal.md rule propagates to Copilot mirror

**Requirement Statement**

WHEN `.claude/rules/universal.md` is edited to add the MUST NOT rule and `build/scripts/generate_rules.py` is run
THE SYSTEM SHALL produce `.github/instructions/universal.instructions.md` that contains the
same rule text
SO THAT Copilot CLI agents reading the mirror see the same prohibition.

**Context**

`build/scripts/generate_rules.py --what-if` validates that `universal.instructions.md` mirrors
`universal.md`. Adding the prohibition rule to `universal.md` without regenerating the mirror
causes `build/scripts/generate_rules.py --what-if` to exit 2 (staleness). Running `build/scripts/generate_rules.py` regenerates the
mirror.

**Acceptance Criteria**

- [ ] `.claude/rules/universal.md` contains a MUST NOT rule prohibiting U+2014 and U+2013.
- [ ] After running `python3 build/scripts/generate_rules.py`, `.github/instructions/
  universal.instructions.md` contains the same prohibition rule text.
- [ ] `python3 build/scripts/generate_rules.py --what-if` exits 0 after regeneration.

**Rationale**

AI agents reading the Copilot mirror must see the same prohibition. If the mirror is stale,
Copilot-routed agents will continue authoring dashes.

**Dependencies**

- `build/scripts/generate_rules.py` (existing)
- `.claude/rules/universal.md` (existing)
- `.github/instructions/universal.instructions.md` (generated)

---

### REQ-006-AC9: Regression test confirms hook blocks fixture with dashes

**Requirement Statement**

WHEN a regression test runs against a fixture `*.md` file containing one em-dash and one
en-dash
THE SYSTEM SHALL confirm the hook exits non-zero for that fixture
SO THAT the hook's detection logic is continuously verified.

**Context**

Regression fixtures live under `tests/hooks/fixtures/`. The test invokes the hook logic
directly (not via git) to avoid requiring a full git repo in CI.

**Acceptance Criteria**

- [ ] A fixture file exists at `tests/hooks/fixtures/dash_violations.md` containing at least
  one U+2014 and one U+2013.
- [ ] The corresponding test asserts hook exit code is non-zero when processing that fixture.
- [ ] The test is part of the standard `pytest` suite and passes in CI.

**Rationale**

Automated regression tests prevent silent degradation of the enforcement logic over time.

**Dependencies**

- `tests/hooks/` directory (existing or created by TASK-005)
- pytest 8+

---

### REQ-006-AC10: Regression test confirms hook passes clean fixture

**Requirement Statement**

WHEN a regression test runs against a clean fixture `*.md` file with no dashes
THE SYSTEM SHALL confirm the hook exits zero
SO THAT false-positive behavior is continuously verified.

**Context**

A clean fixture confirms the hook does not block valid content. This test runs in the same
suite as REQ-006-AC9.

**Acceptance Criteria**

- [ ] A fixture file exists at `tests/hooks/fixtures/no_dash_clean.md` containing no U+2014
  and no U+2013.
- [ ] The corresponding test asserts hook exit code is zero when processing that fixture.
- [ ] The test is part of the standard `pytest` suite and passes in CI.

**Rationale**

False positives on clean content would block all commits. The clean-fixture test is the
regression guard against that failure mode.

**Dependencies**

- Same as REQ-006-AC9.

---

### REQ-006-AC11: Test verifies both source and mirror trees are checked

**Requirement Statement**

WHEN a regression test fixture is located under `.github/instructions/`
THE SYSTEM SHALL apply the same exit-non-zero result as a fixture under `.claude/rules/`
SO THAT both trees are verified by tests.

**Context**

This test confirms REQ-006-AC4 at the test level. It uses two fixtures: one under a path
simulating `.github/instructions/` and one simulating `.claude/rules/`, each containing a
dash. Both must produce non-zero exit codes from the same hook logic.

**Acceptance Criteria**

- [ ] A fixture at `tests/hooks/fixtures/instructions_tree/dash_violations.md` (simulating
  `.github/instructions/`) exists and contains U+2014.
- [ ] The test asserts non-zero exit for that fixture.
- [ ] A comment in the test cites REQ-006-AC4 and REQ-006-AC11 as the ACs being verified.

**Rationale**

Without an explicit test, the instructions-tree inclusion is invisible in CI. This test
makes the contract machine-verifiable.

**Dependencies**

- Same as REQ-006-AC9.

---

## Out of Scope

- `~/.claude/CLAUDE.md` global prohibition (already in place).
- Retroactive cleanup of existing files containing dashes.
- Fixing dashes in `node_modules/`, `.venv/`, `.serena/cache/`.
- CI-level enforcement via GitHub Actions (deferred).
- Windows-native hook support.

## Deferred

- D1: Retroactive branch-scan auto-replace tool. Owner: follow-up issue.
- D2: CI-level enforcement (GitHub Actions check on PRs). Owner: follow-up issue.

## Open Questions

None.
