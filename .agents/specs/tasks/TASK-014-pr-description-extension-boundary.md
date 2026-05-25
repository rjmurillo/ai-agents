---
type: task
id: TASK-014
requirement: REQ-004
design: DESIGN-004
status: ready
priority: P1
created: 2026-05-03
updated: 2026-05-03
---

# TASK-014: Apply extension-boundary lookahead to PR description extractor

## Goal

Land the `_EXT_BOUNDARY` lookahead in `scripts/validation/pr_description.py`
and prove it with tests so PR descriptions mentioning `.jsonl`, `.tsx`,
`.pyc`, or `.bashrc` no longer trigger CRITICAL false positives.

## Subtasks

### T1. Code change (atomic, one commit)

- [ ] Edit `scripts/validation/pr_description.py`:
  - [ ] Add `_EXT_BOUNDARY = r"(?![A-Za-z0-9])"` directly under
        `_EXT_GROUP` (line 46).
  - [ ] Apply `{_EXT_BOUNDARY}` after `({_EXT_GROUP})` in all four
        `FILE_MENTION_PATTERNS` entries (lines 73-81).
  - [ ] Update the docstring on `FILE_MENTION_PATTERNS` to mention the
        boundary rule and link to issue #1874.

### T2. Tests (same commit as T1)

- [ ] Add a `TestExtensionBoundary` class to
      `tests/test_validation_pr_description.py` with these test
      methods (one per acceptance criterion):
  - [ ] `test_jsonl_does_not_extract_json` (AC-1)
  - [ ] `test_tsx_does_not_extract_ts` (AC-2)
  - [ ] `test_pyc_does_not_extract_py` (AC-3)
  - [ ] `test_bashrc_does_not_extract_bash` (AC-4)
  - [ ] `test_json_still_extracts` (AC-5 regression)
  - [ ] `test_md_still_extracts` (AC-6 regression)
  - [ ] `test_list_item_json_still_extracts` (AC-7 regression)
  - [ ] `test_boundary_applies_to_all_four_patterns` (AC-9; parametrize
        over inline-code, bold, list-item, markdown-link variants of the
        same `runs.jsonl` input)

### T3. Local verification

- [ ] `uv run pytest tests/test_validation_pr_description.py -v`
- [ ] `python3 scripts/validation/pre_pr.py`
- [ ] Manual smoke: feed PR #1873's description to
      `extract_mentioned_files`; confirm `runs.json` does NOT appear in
      the result.

### T4. PR + AC-8

- [ ] Open PR with title
      `fix(validation): anchor pr_description file-mention extraction to extension boundary`
      and body that links `Fixes #1874`.
- [ ] After merge, comment on #1873 to trigger a rebase; confirm the
      description-vs-diff check passes without the bypass label
      (AC-8).

## Done definition

- All acceptance criteria from REQ-004 pass.
- Test suite green locally and in CI.
- PR #1874 closed by merge.
- PR #1873 description-vs-diff check passes after rebase.

## Estimate

Single commit, ≤30 min including tests and CI wait.

## Risk

Low. Local change in one module, fully tested, reversible.

## Traceability

- Requirement: `REQ-004-pr-description-extension-boundary.md`
- Design: `DESIGN-004-pr-description-extension-boundary.md`
- Issue: rjmurillo/ai-agents#1874
- Downstream PR: rjmurillo/ai-agents#1873
