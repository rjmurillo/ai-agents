---
type: requirement
id: REQ-014
category: unwanted-behavior
status: draft
priority: P1
created: 2026-05-03
updated: 2026-05-03
---

# REQ-014: PR description file-mention extraction must respect extension boundaries

## Problem statement

`scripts/validation/pr_description.py` extracts file paths from PR
descriptions to detect "claimed but not changed" mismatches. The current
`FILE_MENTION_PATTERNS` use a greedy character class followed by
`\.(_EXT_GROUP)`, so the regex engine backtracks across longer real
extensions and produces a known short extension as a false positive
(`runs.jsonl` → `runs.json`, `app.tsx` → `app.ts`, `module.pyc` →
`module.py`, `script.bashrc` → `script.bash`). This blocks any PR whose
description mentions such extensions in inline code, bold, list items, or
markdown links. Reproduced against PR #1873.

## Source

- Issue rjmurillo/ai-agents#1874
- Affected file: `scripts/validation/pr_description.py:46,73-81`
- Tests: `tests/test_validation_pr_description.py`

## Requirement Statement

IF a PR description contains a token that ends in an extension not listed
in `_EXT_GROUP` but whose suffix coincides with one that is
THEN THE PR description validator SHALL NOT extract the truncated
form as a mentioned file.

## Rationale

The validator gates merges. A false-positive CRITICAL on a description
that uses `.jsonl`, `.tsx`, `.jsx`, `.pyc`, `.pyx`, `.bashrc`, etc.
forces authors to apply `description-validation-bypass`, which in turn
hides legitimate description-vs-diff defects.

## Acceptance Criteria

Each criterion is independently testable as pass/fail by calling
`extract_mentioned_files(description)` from
`scripts.validation.pr_description`.

1. **AC-1 (jsonl)**: WHEN description contains `` `- `runs.jsonl` (60 records)` ``
   THE extractor SHALL NOT return `runs.json`.
2. **AC-2 (tsx)**: WHEN description contains `` `app.tsx` ``
   THE extractor SHALL NOT return `app.ts`.
3. **AC-3 (pyc)**: WHEN description contains `` `module.pyc` ``
   THE extractor SHALL NOT return `module.py`.
4. **AC-4 (bashrc)**: WHEN description contains `` `script.bashrc` ``
   THE extractor SHALL NOT return `script.bash`.
5. **AC-5 (json regression)**: WHEN description contains `` `foo.json` ``
   THE extractor SHALL return `foo.json`.
6. **AC-6 (md regression)**: WHEN description contains `` `bar.md` ``
   THE extractor SHALL return `bar.md`.
7. **AC-7 (list-item regression)**: WHEN description contains a list item
   `- foo.json`
   THE extractor SHALL return `foo.json`.
8. **AC-8 (downstream gate)**: WHEN PR #1873 (or any PR whose only
   description-validator failure was extension prefix matching) rebases
   on `main`
   THE description-vs-diff check SHALL pass without
   `description-validation-bypass`.
9. **AC-9 (boundary across all four patterns)**: WHEN the description
   contains the same mismatch token in inline-code, bold, list-item, and
   markdown-link forms
   THE extractor SHALL apply the boundary rule uniformly across all four
   patterns.
10. **AC-10 (underscore continuation)**: WHEN description contains
    `` `foo.json_schema` ``
    THE extractor SHALL NOT return `foo.json`. Added during PR #1882
    review to guard against identifier-shaped continuations such as
    `_schema`, `_old`, `_v2`.
11. **AC-11 (path-separator continuation)**: WHEN description contains
    a list item `- path/to/file.py/extra`
    THE extractor SHALL NOT return `path/to/file.py`. Added during PR
    #1882 review to guard against partial path matches when the
    extension is followed by an additional path component.
12. **AC-12 (path-separator regression)**: WHEN description contains a
    list item `- packages/orders/processor.py`
    THE extractor SHALL return `packages/orders/processor.py`. Locks
    down that the boundary widening does not regress real multi-segment
    paths.

## Out of scope

- Adding new extensions to `_EXT_GROUP` (`.jsonl`, `.tsx`, `.jsx`,
  `.pyc`, `.pyx`, `.bashrc`). Separate governance decision.
- Other parts of `pr_description.py`: commit-count check, contextual
  section stripping, `<details>` filtering.
- Refactoring the four-pattern structure into a single combined regex.

## Deferred

None.

## Open questions

None. Issue body specifies fix mechanism; downstream PR #1873 verifies
the regression.

## Traceability

- Design: `DESIGN-004-pr-description-extension-boundary.md`
- Tasks: `TASK-004-pr-description-extension-boundary.md`
