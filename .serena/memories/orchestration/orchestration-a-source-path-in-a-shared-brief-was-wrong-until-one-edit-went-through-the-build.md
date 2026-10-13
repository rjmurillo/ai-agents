# A shared brief named the wrong source tree, and no one had pushed one edit through the build

## What happened

The ship contract for the 2026-10-11 P2 sweep told every agent that skill scripts live under `src/claude`. That tree is a build output. `build_all.py` mirrors skill support files into `src/claude/skills/<name>/` and prunes anything that exists only there, so agent edits to `src/` were reverted.

The contract later gained a "3b CORRECTION" line: skill support files are sourced in `.claude/skills/<name>/`, and `SKILL.md` renders from `templates/skills/<name>.SKILL.md.tmpl`. The module docstring of `build/scripts/skill_support_mirror.py` states the same direction.

## Why it reached every agent

One wrong line in a shared brief is copied into every agent's prompt. The retrospective found no record that anyone ran a single edit through `build_all.py` before the wave. The number of agents that lost edits is not recorded.

`.claude/AGENTS.md` line 3 opens by calling `.claude/` a binplaced copy of `src/claude/`. A reader who stops there infers the wrong direction. The same file lists each skill's non-`SKILL.md` files as hand-maintained.

## What the check looks like

Before a brief names a source path, make one real edit in a scratch worktree for each path class the brief names. Run `uv run python build/scripts/build_all.py` and see whether the edit survives. The cost is minutes, against a wave of reverted work.

## Sources

- `build/scripts/skill_support_mirror.py` module docstring.
- Ship contract step 3b, 2026-10-12.
- Retrospective `.project-toolkit/retrospective/2026-10-12-v070-p2-sweep-resource-and-contract.md` (PR #6334), Five Whys item 2.
- Related: `architecture/architecture-skill-support-files-are-sourced-in-claude-skills`, which records the correct tree.
