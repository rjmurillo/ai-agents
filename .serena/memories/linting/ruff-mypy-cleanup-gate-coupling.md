# Ruff/Mypy Cleanup Gate Coupling (issue #2993 burndown)

**Statement**: A ruff or mypy cleanup PR in this repo is not "just run --fix". Touching any file drags a stack of local gates onto that file's PRE-EXISTING debt. Build each batch from files that clear ALL of them, or the push fails.

**Context**: The #2993 ruff burndown (457+ violations across 126 files). These are repo-specific behaviors of this repo's `.githooks/` and `scripts/ci/` gates, verified on PRs #3035 (failed) and #3036 (landed).

**Source**: Session 2026-07-11. `scripts/ci/ruff_ratchet.py`, `.githooks/pre-push` Phase 7, `.githooks/pre-commit`.

## The gates that fire on any touched file

1. **CI ruff ratchet matches violations by file+line** (`scripts/ci/ruff_ratchet.py`, runs under the "Run Python Tests" CI job, `ignore=[]` so E501 fires). A safe autofix that removes a blank line or an import SHIFTS subsequent line numbers, so the file's PRE-EXISTING E501 lines register at new line numbers and count as new violations. The push fails even though your edit added nothing. Only files that are **0-violation under the full ratchet ruleset** after `--fix` can ride a mechanical batch. Verify per file: `uv run ruff check <f> --select E,F,W,I,N,UP,B,ANN` must print nothing.

2. **Pre-push mypy runs as one batch with follow-imports, no MYPYPATH** (`.githooks/pre-push` Phase 7, `mypy "${PY_FILES_UNIQUE[@]}"`). Touching a file pulls its whole import graph into mypy, so pre-existing type debt in imported modules (or untyped third-party deps like `python-frontmatter`) blocks the push. Per-file `MYPYPATH=scripts/validation mypy <f>` UNDER-reports and is misleading. Validate the real gate with:
   `uv run mypy $(git diff --name-only main..HEAD | grep '\.py$' | grep -v '^src/copilot-cli/')`.

3. **Pre-commit re-applies `ruff --fix` on staged files.** You cannot stage a file "unfixed" to dodge its gate stack, and you cannot revert a ruff change by committing the old content (the hook re-applies the fix, producing an empty commit). To exclude a file, never stage it; rebuild the branch without it (`git reset --hard main` then re-apply `--fix` to only the safe set).

4. **Cascade on `.claude` / `.agents` / sync-source edits:**
   - `.claude/**` source edit -> lockstep plugin bump (`.claude` + `src/copilot-cli` `plugin.json` to identical version) AND `build/scripts/build_all.py` mirror regen, both committed.
   - `.agents/**` edit -> a staged session log is required (session-protocol pre-commit gate).
   - sync-source files (`ai_review_common`, `github_core`, `hook_utilities`) -> the sync workflow, not a direct edit.

5. **E501 (the majority of remaining violations) is mostly in strings/comments/URLs**, not reflow-fixable. `ruff format` is NOT the repo standard (1179 of ~1625 files would reformat), so it is not an option for bulk E501.

## Recipe for a landable batch

1. `ruff check <candidates> --fix`.
2. Keep only files that are 0-violation under `ruff check <f> --select E,F,W,I,N,UP,B,ANN` (ratchet-clean; line-shift safe).
3. Confirm the batch mypy command in gate 2 is clean for the whole committed set.
4. If `.claude` sources are touched: bump both `plugin.json` to the same new version, run `build_all.py`, commit the regenerated `src/copilot-cli` mirrors.
5. Split into <=5-file commits; push detached (pre-push ~9-10 min).

## Fix, do not suppress

The idiomatic fix is the goal (proper annotations, wrapped lines, renames), not blanket ignores. Suppression is a last resort and must carry a mini-ADR comment. See `.claude/rules/code-quality.md` "Suppressions Are a Last Resort".
