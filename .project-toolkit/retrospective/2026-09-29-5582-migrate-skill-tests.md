# Retrospective: Migrate colocated skill tests to tests/skills (issue #5582)

**Date**: 2026-09-29
**Scope**: Move 55 test modules from `.claude/skills/<name>/tests/` to `tests/skills/<name>/`.
**Outcome**: Local gates pass. CI results are on the pull request.

## What happened

The issue counted 121 tracked files across two trees. Main had moved. A third mirror, `src/claude/skills/`, now held 61 more test files. Measured total: 182 files (61 authored, 61 in `src/claude`, 60 in `src/copilot-cli`).

A plain `build_all.py` run pruned `src/claude/skills/`. It left `src/copilot-cli/skills/` alone. `build_all.py --clean` then a plain run removed the rest.

Two files in `tests/skills/` were CI shims. They imported colocated test files by path. Deleting the colocated files broke their collection. The moved modules replace both shims.

The skillforge packaging test failed because `package_skill.py` guards paths against HOME and cwd. The fixture now sets both. The guards did not change.

## Evidence

- 1394 tests from the moved files pass at `tests/skills/`.
- `ruff check .` passes and the ruff count ratchet reports zero.
- Two baselines needed edits: `skill_portability_baseline.json` and `guard_corpus_baseline.json`.
- Two rule fixtures under `tests/build_scripts/fixtures/rule_templates_b2/expected/` needed the new rule text.
- The context output for `tests/AGENTS.md` needed regeneration.

## Findings

- `tests/test_plugin_path_resolution.py` filters paths containing the word "tests". A worktree named `chore-5582-migrate-skill-tests` empties its selection. The test passes in a worktree without that word.
- `tests/test_pr_comment_responder_status_greps.py` and `tests/validation/test_effective_context_ratchet.py` fail on origin/main too. This change did not cause them.
- `scripts/skill_registry.py:200` reports has_tests from `<skill>/tests`. It now reports N for every skill.
- `tests/skills/test/test_dx_trigger.py:101` keeps a synthetic colocated path. It is test input, not a stale pointer.

## Learnings

- Search for tests that import other tests by path before deleting the imported file.
- Measure every generated mirror tree, not only the ones the issue names.
- Name worktrees without the word "tests" when the repo has path filters on that word.
