---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-14-session-14705-b2c958770-fix-4956-doc-accuracy-exit-code.json
qaCommit: 90d417da80f4002b02a40b81b4b509bbf671d3d1
---

# PR 4956 exit-code documentation validation

## Result

PASS. The canonical documentation, portable generated mirror, and executable
behavior agree on exit codes 0, 1, 2, 3, and 10.

## Evidence

- Six focused tests passed in 10.81 seconds. They cover:
  - exit 0 for a valid empty diff
  - exit 1 for an inconclusive docs-only scan
  - exit 2 for an invalid diff base
  - exit 3 for a Git object database failure
  - exit 10 for an unresolved symbol finding
  - exact agreement between the canonical module contract and skill docs
  - the plugin-relative `scripts/doc_accuracy.py` source citation
- `uv run ruff check .claude/skills/doc-accuracy/scripts/doc_accuracy.py
  tests/skills/doc-accuracy/test_doc_accuracy.py` exited 0.
- `uv run python .claude/skills/SkillForge/scripts/quick_validate.py
  .claude/skills/doc-accuracy` reported `Skill is valid`.
- `uv run python build/scripts/build_all.py --check` exited 0 and left the
  worktree unchanged.

## Broader validation

A full Windows run of the 89-test file passed 84 tests. Five existing
platform-specific cases failed because they require newline filenames or
native fsmonitor behavior that Windows does not provide. The focused tests
exercise every documented exit code and pass on Windows.
