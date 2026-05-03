---
type: design
id: DESIGN-004
requirement: REQ-004
status: draft
created: 2026-05-03
updated: 2026-05-03
---

# DESIGN-004: Anchor file-mention extraction to extension token boundary

## Context

`scripts/validation/pr_description.py` defines four regex patterns
(inline code, bold, list item, markdown link) that share an extension
alternation `_EXT_GROUP = r"ps1|md|yml|yaml|json|cs|ts|js|py|sh|bash"`.
Every pattern matches a body group followed by `\.(_EXT_GROUP)`. The
body group uses a greedy non-anchored character class. When the input
ends in a longer real extension (`.jsonl`, `.tsx`, `.pyc`, `.bashrc`),
the engine backtracks the body group until `\.(_EXT_GROUP)` matches a
shorter known extension. The remainder of the input (`l`, `x`, `c`,
`rc`) is allowed because the pattern terminator is permissive (`` `?
``, `\*\*`, `\]`, end of token).

## Decision

Add a single negative lookahead `_EXT_BOUNDARY = r"(?![A-Za-z0-9])"`
immediately after the captured extension in every pattern. This rejects
any continuation character that would extend a real filename into a
longer extension or word boundary token.

```python
_EXT_BOUNDARY = r"(?![A-Za-z0-9])"

FILE_MENTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(rf"`([^`]+\.({_EXT_GROUP})){_EXT_BOUNDARY}`"),
    re.compile(rf"\*\*([^*]+\.({_EXT_GROUP})){_EXT_BOUNDARY}\*\*"),
    re.compile(
        rf"^\s*[-*+]\s+`?([^\s`]+\.({_EXT_GROUP})){_EXT_BOUNDARY}`?",
        re.MULTILINE,
    ),
    re.compile(rf"\[([^\]]+\.({_EXT_GROUP})){_EXT_BOUNDARY}\]"),
]
```

## Why this design

- **One change, four call sites, identical fix.** The four patterns
  share a single failure mode; one symbol applies it everywhere.
- **No new state.** The fix is local to one module; no schema, hook, or
  CI surface changes.
- **No semantic loss.** The lookahead only rejects continuations that
  would have produced a different real filename. Every legitimate
  extraction (file ends in a known extension, then a non-alphanumeric
  delimiter) still matches.
- **Reversible.** A single multi-line edit; rollback is one revert.

## Alternatives considered

1. **Enumerate longer extensions explicitly**
   `_EXT_GROUP = r"jsonl|jsonc|tsx|jsx|pyx|pyc|...|json|...|js|...|sh|bash"`.
   Rejected: requires keeping the list in sync with every new extension
   the team encounters; does not solve the underlying "extension is a
   prefix of another extension or word" problem (`bash` ↔ `bashrc`).

2. **Replace four patterns with one combined regex**
   Rejected: out of scope. Issue #1874 narrows the change to extension
   boundary handling. Consolidation is a separate refactor.

3. **Post-process extracted paths against a deny-list**
   Rejected: introduces a second authority for "what is a valid
   mention" and obscures the actual root cause.

## Components

- `scripts/validation/pr_description.py:46`. Add `_EXT_BOUNDARY` constant
  next to `_EXT_GROUP`.
- `scripts/validation/pr_description.py:73-81`. Apply `_EXT_BOUNDARY` to
  all four `FILE_MENTION_PATTERNS`.
- `tests/test_validation_pr_description.py`. Extend
  `extract_mentioned_files` test class with the boundary cases.

## Failure modes

- **Regex compilation error**: caught at import time. CI test suite
  exercises every pattern.
- **New false negative**: a legitimate path ending in `.json` followed
  immediately by an alphanumeric (no delimiter) would no longer match.
  This is the correct behavior; today's match would have been wrong.
- **Backtracking blowup**: not introduced. Lookahead is fixed-width and
  zero-cost per attempted position.

## Observability

No new logging. The validator already emits structured JSON with the
file path and severity. After the fix, the false-positive entries
disappear from CI output.

## Test plan

Add a dedicated test class `TestExtensionBoundary` in
`tests/test_validation_pr_description.py` covering AC-1 through AC-7.
Reuse the existing `extract_mentioned_files` import. AC-9 is satisfied
by parametrizing the same input across the four pattern wrappers
(inline code, bold, list item, markdown link). AC-8 is verified out of
band by rebasing #1873 after the fix lands.

## Rollout

Standard PR flow:

1. Branch off `main`.
2. Land code + test in a single commit (`fix(validation): anchor
   PR description file-mention extraction to extension boundary`).
3. CI runs the test suite; the new tests must pass.
4. Merge.
5. Rebase #1873 to verify AC-8.

## Risks

- Low. The change is local, additive (a lookahead per pattern), and
  guarded by tests. The only at-risk callers are description bodies
  that happen to depend on the old greedy behavior; none have been
  identified, and any such reliance was already a bug.

## Traceability

- Requirement: `REQ-004-pr-description-extension-boundary.md`
- Tasks: `TASK-004-pr-description-extension-boundary.md`
- Related: PR #1873, Issue #1874
