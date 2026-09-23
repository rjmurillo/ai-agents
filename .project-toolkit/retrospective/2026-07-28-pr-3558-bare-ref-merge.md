---
date: 2026-07-28
pr: 3558
issue: 3482
scope: scripts/validation/check_skill_md_portability.py
---

## Retrospective: PR #3558 bare portability directory refs

### Context

PR #3558 adds word-boundary detection (`\b` lookahead) to the portability
validator terminator pattern so that bare directory references like `.agents`
at sentence end are counted.

### Merge resolution learnings

Main evolved significantly since the PR was authored (commit `cc3a23ebc0`).
The anchoring logic was rewritten from a simple negative lookbehind
`(?<![\\\w.])` into a multi-component boundary system (`_ANCHOR`,
`_LABEL_ANCHOR`, `_ATTR_ANCHOR`, `_BOUNDARY`) addressing issues #3459 and
#3489. The PR's terminator fix remains orthogonal: it addresses what comes
AFTER the path segment, while main's anchor addresses what comes BEFORE.

Resolution strategy: keep main's anchor, add PR's terminator as a shared
`_UPSTREAM_REF_TERMINATOR` constant applied to all five patterns.

### Baseline drift

The stricter anchor caused the three previously-baselined files to drop to 0
counted refs (their references are preceded by characters not in the anchor
set). `security-review/SKILL.md` has 4 raw refs but self-declares via
`<!-- vendor-portability: ... -->` marker, so `count_file_refs` returns 0.
The baseline correctly reflects 0 files / 0 refs.

### Learnings captured

1. When a PR branch is far behind main, check whether the subsystem under
   change has been rewritten. Regex terminators and regex anchors are
   independent dimensions; a fix to one does not conflict with a rewrite of
   the other if the integration point (the compiled pattern) composes them.
2. The `--what-if` flag on `generate_skills.py` reports all managed files,
   not just drifted ones. Verify with `diff` before assuming drift.
