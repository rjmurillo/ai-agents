---
type: task
id: TASK-009
title: Retro fixes from PR #1965 (rework + contract drift)
status: todo
priority: P1
complexity: M
related:
  - REQ-009
  - DESIGN-009
blocked_by: []
blocks: []
assignee: ~
created: 2026-05-10
updated: 2026-05-10
---

# TASK-009: Retro fixes from PR #1965 (rework + contract drift)

All tasks reference DESIGN-009 for interface contracts and REQ-009 for acceptance criteria. Tasks are ordered by dependency. Each task is atomic (5 files or fewer per commit, per AGENTS.md). Total estimated effort: 5.5h.

---

## TASK-009-01: Pagination Contract Test for get_unresolved_review_threads.py

**Complexity:** M (2h)

**Objective:** Add a pytest contract test that stubs the GitHub GraphQL endpoint and asserts `get_unresolved_review_threads.py` returns all threads across pagination boundaries. Pins REQ-009-01 and REQ-009-02.

**In scope:**
- Create `tests/skills/github/test_get_unresolved_review_threads.py`.
- Stub the HTTP layer (do not patch at OS level).
- Test multi-page case: 100 threads on page 1 (`hasNextPage=true`) + 1 thread on page 2 (`hasNextPage=false`) = 101 total.
- Test single-page case: all threads fit in one response (`hasNextPage=false`); assert HTTP called once.
- Both test cases share stub infrastructure in the same file.

**Out of scope:**
- Fixing the pagination bug in `get_unresolved_review_threads.py` itself.
- Testing other scripts in the same directory.

**Acceptance Criteria:**
- [ ] REQ-009-01: test asserts all 101 thread IDs returned for multi-page stub.
- [ ] REQ-009-02: test asserts exactly one HTTP call for single-page stub.
- [ ] No live network calls; all HTTP interactions are stubbed.
- [ ] `pytest tests/skills/github/test_get_unresolved_review_threads.py` exits 0.
- [ ] Test file imports follow ADR-042 (Python, standard library mock only).

**Files Affected:**

| File | Action | Description |
|------|--------|-------------|
| `tests/skills/github/test_get_unresolved_review_threads.py` | Create | Contract test for GraphQL pagination behavior |

**Implementation Notes:**
- Read `get_unresolved_review_threads.py` first to identify the HTTP call site and the return type.
- If the script has no importable entry point (only `if __name__ == "__main__"`), call it via `subprocess.run` with a mocked subprocess, or add a thin module-level function and patch that.
- Stub shape: `{"data": {"repository": {"pullRequest": {"reviewThreads": {"nodes": [...], "pageInfo": {"hasNextPage": bool, "endCursor": str}}}}}}`.
- Use `unittest.mock.patch` targeting the specific HTTP client used by the script.
- Each thread node needs at minimum an `id` field for the assertion to count IDs.

**Testing Requirements:**
- Self-testing: the new test file is its own test. Run `pytest tests/skills/github/test_get_unresolved_review_threads.py -v` to verify.

**Dependencies:** None.

**Done Definition:** `pytest tests/skills/github/test_get_unresolved_review_threads.py` passes; both test cases are present and named descriptively.

---

## TASK-009-02: Extend canonical-source-mirror.md applyTo Glob + Contract Test

**Complexity:** S (30min)

**Objective:** Extend the `applyTo` field in `.claude/rules/canonical-source-mirror.md` to cover `.claude/review-axes/**` and `.github/prompts/**`, and add a contract test that asserts coverage. Pins REQ-009-03.

**In scope:**
- Edit `.claude/rules/canonical-source-mirror.md`: add or extend `applyTo` frontmatter field.
- Create `tests/build_scripts/test_canonical_source_mirror.py`.
- Test parses frontmatter and asserts both `.claude/review-axes/analyst.md` and `.github/prompts/pr-quality-gate-analyst.md` match the glob.

**Out of scope:**
- Changing rule prose, rationale, anti-patterns, or any body section.
- Migrating existing axis files to comply with the rule (separate concern).

**Acceptance Criteria:**
- [ ] REQ-009-03: `applyTo` glob matches `.claude/review-axes/analyst.md` via Python `fnmatch`.
- [ ] REQ-009-03: `applyTo` glob matches `.github/prompts/pr-quality-gate-analyst.md` via Python `fnmatch`.
- [ ] Rule prose unchanged (diff shows only frontmatter changes).
- [ ] `pytest tests/build_scripts/test_canonical_source_mirror.py` exits 0.
- [ ] Test fails if `applyTo` is removed or narrowed to exclude either path.

**Files Affected:**

| File | Action | Description |
|------|--------|-------------|
| `.claude/rules/canonical-source-mirror.md` | Edit | Add/extend `applyTo` glob in frontmatter |
| `tests/build_scripts/test_canonical_source_mirror.py` | Create | Contract test asserting glob coverage |

**Implementation Notes:**
- Read `.claude/rules/canonical-source-mirror.md` before editing. Check if `applyTo` already exists.
- If `applyTo` is absent, add it after the last existing frontmatter key. Do not reorder existing keys.
- Glob patterns to add: `.claude/review-axes/**` and `.github/prompts/**`. Use a YAML list if multiple globs are needed.
- In the test: parse frontmatter with `yaml.safe_load` after splitting on `---`. Extract `applyTo` as a list (coerce to list if string). For each candidate path, assert `any(fnmatch.fnmatch(candidate, g) for g in globs)`.
- Honor chestertons-fence: read the rule body and confirm no sentence references the old glob before narrowing. Do not change any prose.

**Testing Requirements:**
- Run `pytest tests/build_scripts/test_canonical_source_mirror.py -v` to verify.

**Dependencies:** None.

**Done Definition:** Rule file edited (frontmatter only). Contract test passes. Diff shows no body prose changes.

---

## TASK-009-03: Add co-change-checklist Section Template to /spec Step 6

**Complexity:** S (1h)

**Objective:** Add a conditional Step 6 prompt and `## Co-change checklist` section template to `.claude/commands/spec.md`. Pins REQ-009-04 and REQ-009-05.

**In scope:**
- Edit `.claude/commands/spec.md`.
- Add to the Step 6 section: a conditional prompt asking "Is this a multi-site contract change? (y/n)".
- If yes: agent is instructed to emit a `## Co-change checklist` section in the generated requirement file with one placeholder entry per identified site.
- Document placeholder format: `- [ ] {file_path}:{line_or_section} -- {what changes}`.
- Document section placement: after the last `### Acceptance Criteria` subsection, before `### Rationale`.

**Out of scope:**
- Changing any other step in the `/spec` pipeline.
- Building an automated site-detection tool.
- Adding a linter for the checklist format.

**Acceptance Criteria:**
- [ ] REQ-009-04: Step 6 contains a conditional prompt "Is this a multi-site contract change? (y/n)".
- [ ] REQ-009-04: Instruction to emit `## Co-change checklist` section is present when answer is "yes".
- [ ] REQ-009-05: Placeholder format `- [ ] {file_path}:{line_or_section} -- {what changes}` is documented.
- [ ] REQ-009-05: Section placement rule is documented (after last AC, before Rationale).
- [ ] Section header is exactly `## Co-change checklist` (level-2, case-sensitive).
- [ ] All other spec steps are unchanged.

**Files Affected:**

| File | Action | Description |
|------|--------|-------------|
| `.claude/commands/spec.md` | Edit | Add Step 6 co-change-checklist conditional |

**Implementation Notes:**
- Read `.claude/commands/spec.md` in full before editing to identify the current Step 6 content and surrounding structure.
- Insert the new conditional after the existing Step 6 content, before Step 7 (or end of Step 6 block).
- The prompt and template are prose instructions to the agent, not executable code.
- Example placeholder row to include in the template documentation:

  ```
  - [ ] .claude/lib/ai_review_common/verdict.py:extract_verdict -- add NEW_TOKEN to pattern
  ```

- Note in the template that `{line_or_section}` may be a section name string when a precise line is unknown.

**Testing Requirements:**
- Manual verification: run `/spec` on a test scenario and confirm the prompt appears at Step 6. No automated test is required for this task (template is prose; behavior is agent-driven).

**Dependencies:** None.

**Done Definition:** `spec.md` edited. Step 6 contains the conditional prompt, section header, and placeholder format. Diff touches only the Step 6 area.

---

## TASK-009-04: Rework Warning in session-end Skill + Contract Test

**Complexity:** M (2h)

**Objective:** Add `check_rework_warning` function to the session-end skill's script layer, wire it into the session log append, and add a contract test pinning the 6-commit threshold. Pins REQ-009-07, REQ-009-08, REQ-009-09.

**In scope:**
- Edit `.claude/skills/session-end/scripts/complete_session_log.py` (or equivalent session-end script).
- Add `check_rework_warning(base_branch: str = "main") -> list[tuple[str, int]]`.
- Wire the function into the session log's `## Rework Warning` section append.
- Emit `rework-warning: {path} edited {n} times` per file, or `rework-warning: none`.
- Create `tests/skills/session-end/test_rework_warning.py`.
- Test stubs `subprocess.run`; asserts threshold behavior at the 6-commit boundary.

**Out of scope:**
- Changing any other session-end behavior.
- Making the warning a hard block (it is a warning only).
- Supporting non-git version control.

**Acceptance Criteria:**
- [ ] REQ-009-07: `check_rework_warning` returns files with 6+ commits; warning lines emitted to stdout.
- [ ] REQ-009-07: `## Rework Warning` section appended to session log.
- [ ] REQ-009-08: When no file exceeds threshold, output is exactly `rework-warning: none`.
- [ ] REQ-009-08: Section still present in session log (containing `rework-warning: none`).
- [ ] REQ-009-09: Test asserts 6-commit file appears; 3-commit file does not.
- [ ] REQ-009-09: Test asserts format `rework-warning: {file_path} edited {n} times`.
- [ ] `pytest tests/skills/session-end/test_rework_warning.py` exits 0.
- [ ] Git unavailability degrades gracefully: emits `rework-warning: git unavailable`, returns empty list.

**Files Affected:**

| File | Action | Description |
|------|--------|-------------|
| `.claude/skills/session-end/scripts/complete_session_log.py` | Edit | Add `check_rework_warning` function + session log wiring |
| `tests/skills/session-end/test_rework_warning.py` | Create | Contract test for rework threshold behavior |

**Implementation Notes:**
- Read the current `complete_session_log.py` before editing to understand existing structure and avoid side effects.
- Locate the section where other `##` blocks are appended to the session log. Insert `## Rework Warning` after the existing final section.
- `check_rework_warning` implementation sketch:

  ```python
  import subprocess
  from collections import Counter

  REWORK_THRESHOLD = 6  # named constant for tunability

  def check_rework_warning(base_branch: str = "main") -> list[tuple[str, int]]:
      try:
          result = subprocess.run(
              ["git", "log", "--name-only", "--format=", f"{base_branch}...HEAD"],
              capture_output=True, text=True, timeout=30
          )
          files = [line for line in result.stdout.splitlines() if line.strip()]
          counts = Counter(files)
          return sorted(
              [(f, c) for f, c in counts.items() if c >= REWORK_THRESHOLD],
              key=lambda x: x[1], reverse=True
          )
      except FileNotFoundError:
          return []  # git not available; caller handles gracefully
  ```

- Caller emits warning lines and appends to session log. If returned list is empty, emit `rework-warning: none`.
- In the test: patch `subprocess.run` to return a `CompletedProcess` with stdout set to a controlled multi-line string listing file paths (one per commit entry). Include `file_a.py` 6 times and `file_b.py` 3 times. Assert `file_a.py` in output, `file_b.py` not in output.
- The test file path `tests/skills/session-end/` assumes the directory exists. If not, create it (empty `__init__.py` is optional for pytest discovery).

**Testing Requirements:**
- `pytest tests/skills/session-end/test_rework_warning.py -v` must pass.
- Run `python3 scripts/validation/pre_pr.py` to confirm no pre-PR gate failures.

**Dependencies:** TASK-009-01, TASK-009-02, TASK-009-03 are independent. TASK-009-04 is independent of all three. All four tasks can proceed in parallel.

**Done Definition:** `complete_session_log.py` edited with `check_rework_warning` and session log wiring. Contract test passes. Session-end integration verified manually by running the skill against the current branch.

---

## Traceability Summary

| Task | REQ ACs covered | Hours |
|------|----------------|-------|
| TASK-009-01 | REQ-009-01, REQ-009-02, REQ-009-06 | 2h |
| TASK-009-02 | REQ-009-03, REQ-009-06 | 0.5h |
| TASK-009-03 | REQ-009-04, REQ-009-05 | 1h |
| TASK-009-04 | REQ-009-07, REQ-009-08, REQ-009-09, REQ-009-06 | 2h |
| **Total** | REQ-009-01 through REQ-009-09 | **5.5h** |

REQ-009-06 (CI gate enforcement) is satisfied by placement of all test files under `tests/` and is not an implementation task.
