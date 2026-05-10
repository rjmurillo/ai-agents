---
type: design
id: DESIGN-009
title: Retro fixes from PR #1965 (rework + contract drift)
status: draft
priority: high
created: 2026-05-10
updated: 2026-05-10
related:
  - REQ-009
  - TASK-009
adr:
  - ADR-035 (exit codes)
  - ADR-042 (Python-first)
author: Richard Murillo
---

# DESIGN-009: Retro fixes from PR #1965 (rework + contract drift)

## Requirements Addressed

REQ-009-01 through REQ-009-09. Resolves three RCAs from `.agents/retrospective/2026-05-10-pr-1965-review-axes-convergence.md`:

- RCA-1: `get_unresolved_review_threads.py` returned 0 for paginated results.
- RCA-2: `.claude/rules/canonical-source-mirror.md` `applyTo` glob excluded axis and prompt directories.
- RCA-3: No tooling surfaced multi-site cascade risk at spec time or rework loops at session-end.

## Design Overview

Four targeted file edits plus three new test files address each RCA without refactoring production scripts or introducing new abstractions. The pagination fix is a pure test addition that pins the existing script's contract. The glob fix is a one-field edit that preserves rule semantics. The co-change-checklist is a template addition to a command file. The rework warning is a new function in the session-end skill's script layer plus a contract test. All new code is Python per ADR-042. All exit codes follow ADR-035.

## Architecture

### Files Changed

| File | Type | Action | RCA addressed |
|------|------|--------|--------------|
| `tests/skills/github/test_get_unresolved_review_threads.py` | Test | Create | RCA-1 |
| `.claude/rules/canonical-source-mirror.md` | Rule | Edit (applyTo only) | RCA-2 |
| `tests/build_scripts/test_canonical_source_mirror.py` | Test | Create | RCA-2 |
| `.claude/commands/spec.md` | Command | Edit (Step 6 section) | RCA-3a |
| `.claude/skills/session-end/scripts/complete_session_log.py` | Script | Edit (add function) | RCA-3b |
| `tests/skills/session-end/test_rework_warning.py` | Test | Create | RCA-3b |

No files are deleted. No new directories are created (all parent directories already exist).

### Unchanged

- `get_unresolved_review_threads.py` itself (test only, per scope constraint)
- All `.claude/review-axes/` axis files (out of scope)
- `.github/workflows/` (no new CI jobs needed; existing "Run Python Tests" gate is sufficient)

## Component Map

### REQ-009-01, REQ-009-02: Pagination Contract Test

**Component:** `tests/skills/github/test_get_unresolved_review_threads.py`

**Responsibility:** Stub the GitHub GraphQL endpoint and assert the script's pagination behavior at two boundary conditions.

**Interface:**
- Uses `unittest.mock.patch` to replace the HTTP call inside `get_unresolved_review_threads.py`.
- Stub provides two response shapes: multi-page (hasNextPage=true on page 1, false on page 2) and single-page (hasNextPage=false).
- Assertions: all 101 IDs returned (multi-page); exactly one HTTP call made (single-page).

**Exit codes:** Test harness returns pytest standard codes. The script under test must return exit code 0 on success (ADR-035).

### REQ-009-03: canonical-source-mirror.md applyTo Glob

**Component:** `.claude/rules/canonical-source-mirror.md` (frontmatter only) + `tests/build_scripts/test_canonical_source_mirror.py`

**Responsibility:** The rule's `applyTo` field must cover `.claude/review-axes/**` and `.github/prompts/**`. The contract test parses the frontmatter and asserts glob coverage via `fnmatch`.

**Interface:** YAML frontmatter field `applyTo`. The test imports `yaml` and `fnmatch`. No runtime dependency; this is a static analysis check.

**Constraint:** Rule body prose is read-only per chestertons-fence guidance. Only `applyTo` changes.

### REQ-009-04, REQ-009-05: co-change-checklist in /spec

**Component:** `.claude/commands/spec.md`

**Responsibility:** Step 6 of the `/spec` command gains a conditional branch. When the user answers "yes" to "Is this a multi-site contract change?", the generated requirement file includes a `## Co-change checklist` section with one placeholder entry per identified site.

**Interface:** The section template is plain markdown prose in `spec.md`. No code runs. The agent reads the template and emits it into the generated file. Placeholder format:

```
- [ ] {file_path}:{line_or_section} -- {what changes}
```

**Placement:** The `## Co-change checklist` section is inserted after the last `### Acceptance Criteria` subsection and before `### Rationale` in each generated requirement.

### REQ-009-06: CI Gate Enforcement

**Component:** No new component. Existing "Run Python Tests" required check covers `tests/` by default.

**Responsibility:** New test files placed under `tests/` are auto-discovered by pytest. No workflow edits needed.

### REQ-009-07, REQ-009-08: Rework Warning (Implementation)

**Component:** `.claude/skills/session-end/scripts/complete_session_log.py`

**Responsibility:** A new function `check_rework_warning(base_branch: str) -> list[tuple[str, int]]` queries `git log --name-only` for the current branch vs. base. It returns a list of `(filepath, count)` tuples where count >= 6. The caller in `complete_session_log.py` emits warning lines and appends a `## Rework Warning` section to the session log.

**Interface:**

```python
def check_rework_warning(base_branch: str = "main") -> list[tuple[str, int]]:
    """Return files edited >= 6 times on current branch vs base_branch.

    Canonical source: git log --name-only --format="" {base}...HEAD
    Exit codes: 0=ok (ADR-035).
    Degrades to empty list if git is unavailable.
    """
```

Output format per file: `rework-warning: {file_path} edited {n} times`
Negative case output: `rework-warning: none`

### REQ-009-09: Rework Warning Contract Test

**Component:** `tests/skills/session-end/test_rework_warning.py`

**Responsibility:** Stubs `subprocess.run` to return a controlled `git log` output. Asserts threshold behavior at the 6-commit boundary.

**Interface:** Uses `unittest.mock.patch("subprocess.run")`. No live git access.

## Data Flow

### Pagination Test Flow

`test_get_unresolved_review_threads.py` patches the HTTP layer used by `get_unresolved_review_threads.py`. On the first stub call, the mock returns a GraphQL page of 100 threads with `pageInfo.hasNextPage=true` and a `endCursor` value. On the second call, it returns 1 thread with `pageInfo.hasNextPage=false`. The test calls the script's main function (or equivalent public entry point) and asserts the returned list contains exactly 101 entries. A second test case stubs a single response with `hasNextPage=false` and asserts the HTTP client was called exactly once, confirming the script does not over-paginate on short PRs.

### applyTo Glob Check Flow

`test_canonical_source_mirror.py` opens `.claude/rules/canonical-source-mirror.md`, splits on the `---` YAML fence, and parses the frontmatter with `yaml.safe_load`. It extracts the `applyTo` value (a string or list of strings). For each candidate path (`.claude/review-axes/analyst.md`, `.github/prompts/pr-quality-gate-analyst.md`), it calls `fnmatch.fnmatch(candidate, glob)` for each glob pattern and asserts at least one pattern matches. The rule file edit that adds `.claude/review-axes/**` and `.github/prompts/**` to `applyTo` makes the assertions pass. If `applyTo` is later narrowed or removed, the test fails, blocking the PR via the "Run Python Tests" gate.

### Rework Warning Flow

At session-end, `complete_session_log.py` calls `check_rework_warning(base_branch)`. The function runs `git log --name-only --format="" {base_branch}...HEAD`, splits the output into lines, filters empty lines, and counts occurrences per file path using a `collections.Counter`. Files with count >= 6 are returned as `(path, count)` tuples sorted descending by count. The caller iterates the list and emits one `rework-warning:` line per file, or `rework-warning: none` if the list is empty. The session log's `## Rework Warning` section is appended atomically with the rest of the log. If `subprocess.run` raises `FileNotFoundError` (git not found), the function logs `rework-warning: git unavailable` and returns an empty list.

## Trade-offs Considered

### Why test-only for get_unresolved_review_threads.py

The PRD explicitly excludes refactoring the script. The test adds a regression contract that will catch the bug if the script is later patched. If the script is fixed independently, the multi-page test will continue to pass (it will start passing instead of failing). This ordering is safe.

Alternative considered: fix the pagination bug in the same PR. Rejected because the PRD scope is "contract test only" and mixing a script fix with test infrastructure violates AGENTS.md atomic commit rules (it would require a separate commit for the fix vs. the test, increasing the per-task file count and review surface).

### Why frontmatter glob rather than a prose-only rule

The `applyTo` field is the standard Claude Code mechanism for path-scoping rules. Adding a prose instruction without a machine-readable glob means the rule is only advisory. A glob that fails a contract test is enforceable. The alternative (removing the `applyTo` restriction and relying on maintainer discipline) was rejected as unenforceable.

### Why a template in spec.md rather than a separate skill

A separate skill would require a new SKILL.md, new tests, and a Skill tool invocation. The co-change-checklist is a simple template expansion that fits naturally into the existing `/spec` Step 6 prose. Adding it as a skill would violate the YAGNI principle for a one-sentence conditional.

### Why 6 as the rework threshold

PR #1965 had scan.py touched 56 times. The retrospective identifies 6+ as the boundary between "iterative development" and "rework loop". This is a soft signal, not a hard block, so false positives are low-cost. The threshold is a named constant in the implementation to support future tuning.

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Script under test has no importable entry point; test cannot call it without subprocess | Medium | High | Use `subprocess.run` with mock to call script as a process; or add `if __name__ == "__main__"` guard and import the module directly. TASK-009-01 resolves at implementation time. |
| `applyTo` field does not exist in current frontmatter | Low | Medium | TASK-009-02 adds the field if absent. Test will catch absence. |
| session-end skill does not have a Python script layer | Low | High | TASK-009-04 first step is to confirm or create the script file. Session-end skill exists; script path is known. |
| Git log format varies across git versions | Low | Medium | Use `--name-only --format=""` which is stable across git >= 2.0. |
| co-change-checklist section placed incorrectly by agent | Low | Low | The template in spec.md is explicit about placement. A future linter (deferred) can enforce it. |

## Test Strategy

| Test file | What it pins |
|-----------|-------------|
| `tests/skills/github/test_get_unresolved_review_threads.py` | Pagination contract: all threads returned on multi-page response; exactly one HTTP call on single-page response. |
| `tests/build_scripts/test_canonical_source_mirror.py` | `applyTo` glob coverage: both axis and prompt paths match after the rule edit. |
| `tests/skills/session-end/test_rework_warning.py` | Rework threshold: 6-commit file appears in warning; 3-commit file does not; format is `rework-warning: {path} edited {n} times`. |

All tests are discoverable by pytest without additional configuration. All tests run without live network or git access. All tests use standard library mocking (`unittest.mock`).

## References

- REQ-009: `.agents/specs/requirements/REQ-009-retro-fixes-pr-1965.md`
- Retro: `.agents/retrospective/2026-05-10-pr-1965-review-axes-convergence.md`
- PR #1887 retro: `.agents/retrospective/2026-05-05-pr-1887-iteration-paradox.md`
- ADR-035: `.agents/architecture/ADR-035-exit-code-standardization.md`
- ADR-042: `.agents/architecture/ADR-042-python-migration-strategy.md`
- canonical-source-mirror rule: `.claude/rules/canonical-source-mirror.md`
