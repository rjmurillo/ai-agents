---
qaCommit: 05e717f5b6343ab9e7e635cd5e1fae1be93db3bb
linkedIssue: 5043
qaSessionLog: .agents/sessions/2026-08-15-session-15002-fix-5043-section-reorder.json
qaVerdict: PASS
---

# QA Report: Issue #5043 - Section reorder detection

## Test Results

| Suite | Tests | Pass | Fail |
|-------|-------|------|------|
| test_install_parity_frontmatter_only.py | 11 | 11 | 0 |
| test_install_parity_torn_repair.py | 20 | 20 | 0 |
| tests/build_scripts/ (full) | 1654 | 1654 | 0 |

## Verification

- [x] Positive: section reorder correctly blocks bypass
- [x] Positive: frontmatter-only change still passes (regression)
- [x] Negative: body change still blocks
- [x] Edge: no frontmatter (identical body passes)
- [x] Edge: unclosed frontmatter treated as body
- [x] Regression: all existing torn-repair tests pass
- [x] mypy: 0 errors
- [x] ruff: clean

## Risk Assessment

Minimal. Change narrows the bypass (more restrictive). Uses same frontmatter-stripping logic as _split_document. Fails closed on any ambiguity.
