# Measure a detector widening over the corpus before choosing its design

Source: issue #4635 / PR #5455 on 2026-09-01, widening `scripts/validation/check_push_lock_paths.py` from fenced-only to unfenced Markdown.

Current behavior: a gate that widens what it inspects will fire on tracked content that was previously invisible to it. The corpus test `test_the_shipped_corpus_has_no_violation` catches this only *after* the design is written, which is the expensive order.

Cheap probe: import the checker's own scanning helpers, run the candidate rule over `tracked_markdown(repo_root)`, and count newly flagged files per candidate before writing anything. Roughly 30 lines, runs in seconds over 3518 files.

Evidence:

- Two candidate designs for the unfenced unit. Reporting the "names no canonical path" finding on unfenced runs flagged 13 tracked files that only *mention* `flock`, including the checker's own rule mirror. Suppressing it flagged 1. The 13-to-1 count selected the design.
- The count inverted the approach the issue's auto-generated PRD proposed (delegate unfenced runs straight to `_scan_block`), which would also have contradicted an existing test.
- A later widening, reporting `flock "$VAR"` that reaches no readable path, was probed the same way and measured 0 of 3518 before landing, so it merged without corpus triage.

Decision: for any change that widens a detector's input surface or its firing condition, probe the corpus and record the count in the PR body before implementing. Treat a plan's design section as a hypothesis; the count is the measurement. Prefer the design whose over-reporting is visible and clearable (this repo's escape hatch is a marker token such as `push-lock-historical`) over one whose misses are silent.

Related: `.claude/rules/push-lock.md` documents the resulting two-unit scan contract and its residual limitation.
