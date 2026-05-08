# Pre-push staleness check

**Confidence**: MED — preference, captured 2026-05-08

## Rule

Run `python3 build/scripts/build_all.py --check` locally as the last gate before pushing. If it reports `STALENESS DETECTED`, regen with `python3 build/scripts/build_all.py` and commit the regen output before pushing.

## Why

The CI workflow "Validate Generated Files" runs the same `--check` command and fails the PR when a generated file's committed copy diverges from what the generator emits. CI runs after push, takes ~60-90s to surface the failure, and triggers a follow-up commit that re-fires every other bot reviewer (Copilot, CodeRabbit, semgrep). Catching staleness locally costs ≤5s and zero bot rounds.

Common drivers of staleness on this codebase:
- A canonical template under `templates/` was edited and `build_all.py` not run (forgets to propagate to `src/copilot-cli/`, `src/vs-code-agents/`).
- A `.claude/rules/*.md` was edited and the corresponding `.github/instructions/*.instructions.md` is now stale (rules → instructions generator strips internal-only globs).
- A `templates/agents/*.shared.md` was edited and only one of three platform copies was regenerated.

## How to apply

1. After all code edits and before `git push`, run `build_all.py --check`.
2. On staleness, run `build_all.py` (no `--check`) to regenerate.
3. `git status` to see what was re-touched. If only the expected files moved, stage them and amend or add a new commit (per the project's atomic-commit rule).
4. Re-run `--check` to confirm clean.
5. Then `git push`.

## When this fails to help

- Pre-existing drift unrelated to your change (e.g. agent-drift on `merge-resolver`). Note in the PR description and let the existing follow-up issue track it; do not bundle into the current PR.
- Generators that depend on dynamically discovered inputs (e.g. plugin manifests). Run the relevant validator (`validate_marketplace_counts.py --fix`) instead of `build_all.py`.
