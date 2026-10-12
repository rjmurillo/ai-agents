# Parallel agents that share one PR body directory overwrite each other's body

## What happened

The ship contract for the 2026-10-11 P2 sweep told parallel agents to write PR body files into one shared scratchpad directory. Same-named files such as `pr1.md` were overwritten across agents. PR #6315 first shipped with another agent's body and failed "Validate PR". The coordinator reported this; no artifact other than the PR itself records it.

## Why the private path avoids it

`new_pr.py --prepare-body-file` calls `prepare_pr_body.py`, which creates `pr-body-*.md` under `<repo root>/.project-toolkit/scratch/`. The directory is owner-only and the body file must match `pr-body-[A-Za-z0-9_-]+\.md` (`prepare_pr_body.py` lines 18 and 72 to 81). Each agent works in its own worktree, so each repo root has its own scratch directory and the names cannot collide.

The sweep fix was one prepared body file per PR inside each worktree.

## Sources

- `.claude/skills/github/scripts/pr/prepare_pr_body.py` lines 1, 18, and 72 to 81.
- PR #6315, whose first body belonged to another agent.
- Retrospective `.project-toolkit/retrospective/2026-10-12-v070-p2-sweep-resource-and-contract.md` (PR #6334), Five Whys item 8.
- Related: `pr-review/pr-validator-needs-prepare-body-file-and-diff-backed-paths`.
