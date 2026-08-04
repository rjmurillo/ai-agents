# Ruff/Mypy Cleanup Gate Coupling (issue #2993 burndown)

**Statement**: A ruff or mypy cleanup PR in this repo is not "just run --fix". Touching any file drags local gates onto that file's PRE-EXISTING debt. Build each batch from files that clear ALL of them, or the push fails.

**Context**: The #2993 ruff burndown (hundreds of violations across the tree). These are repo-specific behaviors of this repo's `.githooks/` and `scripts/ci/` gates, verified on PRs #3035 (failed) and #3036 (landed).

**Source**: Session 2026-07-11. `scripts/ci/ruff_ratchet.py`, `.githooks/pre-push` Phase 7, `.githooks/pre-commit`.

## The gates that fire on any touched file

1. **CI ruff gate** (`scripts/ci/ruff_ratchet.py`; "ratchet" is a misnomer: no baseline, no line matching). It computes `git diff --name-only --diff-filter=ACMR <base>...HEAD`, keeps the `.py` files, then runs `ruff check --output-format=github -- <those files>` and fails if the exit code is non-zero. So it uses the **project ruff config** (`pyproject.toml`: `select = [E,F,W,I,N,UP,B,ANN]`, `ignore = []` so E501 fires at line-length 100, plus `[tool.ruff.lint.per-file-ignores]`). A touched file must be **fully 0-violation under the project config**. That is why #3035 failed: five touched files had pre-existing E501, so `ruff check` on them was non-zero. Verify a file the accurate way: `uv run ruff check <file>` (bare, uses the project config including per-file-ignores). Do NOT verify with `--select E,F,W,I,N,UP,B,ANN`; that bypasses per-file-ignores and can diverge from what CI enforces.

2. **Pre-push mypy** (`.githooks/pre-push` Phase 7, BLOCKING) is not one flat batch. It splits the changed `.py` files:
   - Most files go through a single batch `mypy "${PY_FILES_UNIQUE[@]}"` with **follow-imports**, so touching a file pulls its whole import graph in; pre-existing type debt in imported modules (or untyped deps like `python-frontmatter`) blocks the push.
   - `scripts/validation/*.py` are special-cased through a `MYPYPATH=scripts/validation` loop, one file per invocation (issue #2876: bare intra-package imports plus duplicate module names).
   - Files whose basename collides with another module are routed separately to avoid the "duplicate module named X" abort.
   Do not assume `MYPYPATH` is never involved. Validate the general case with the same batch mypy the hook runs on the changed set: `uv run mypy $(git diff --name-only <base>...HEAD | grep '\.py$' | grep -v '^src/copilot-cli/')`. Per-file `mypy <f>` under-reports for the batch case.

3. **Pre-commit re-applies `ruff --fix` on staged files.** You cannot stage a file "unfixed" to dodge its gate stack, and you cannot revert a ruff change by committing the old content (the hook re-applies the fix, producing an empty commit). To exclude a file, never stage it; rebuild the branch without it (`git reset --hard main`, then re-apply `--fix` to only the safe set).

4. **Cascade on `.claude` / `.agents` / sync-source edits:**
   - `.claude/**` source edit -> `build/scripts/build_all.py` mirror regen, committed. No plugin bump: ADR-092 removed the `version` field from every manifest, and re-adding one fails `build/scripts/validate_plugin_version_bump.py`.
   - `.agents/**` edit -> a staged session log is required (session-protocol pre-commit gate).
   - sync-source files (`ai_review_common`, `github_core`, `hook_utilities`) -> the sync workflow, not a direct edit.

5. **E501 (much of the remaining backlog) is mostly in strings/comments/URLs**, not reflow-fixable. `ruff format` is NOT the repo standard (most files would reformat), so it is not an option for bulk E501.

## Recipe for a landable batch

1. `ruff check <candidates> --fix`.
2. Keep only files that are 0-violation under bare `uv run ruff check <file>` (project config).
3. Confirm the batch mypy command in gate 2 is clean for the whole committed set.
4. If `.claude` sources are touched: run `build_all.py` and commit the regenerated `src/copilot-cli` mirrors. Leave `plugin.json` alone; the manifests carry no version.
5. Split into <=5-file commits; push detached (pre-push ~9-10 min).

## Fix, do not suppress

The idiomatic fix is the goal (proper annotations, wrapped lines, renames), not blanket ignores. Suppression is a last resort and must carry a mini-ADR comment. See `.claude/rules/code-quality.md` "Suppressions Are a Last Resort".
