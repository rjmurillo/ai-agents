# Skill support files are sourced in .claude/skills/<name>/, and src/ copies are pruned

## The source of truth

Every skill file except `SKILL.md` is hand-maintained under `.claude/skills/<name>/`. `SKILL.md` renders from `templates/skills/<name>.SKILL.md.tmpl`. `build/scripts/skill_support_mirror.py` states this in its module docstring.

## What the build does to the copies

`build_all.py` mirrors support files (scripts, references, tests) into `src/claude/skills/<name>/` and the Copilot tree. For the Claude tree, `_prune_stale_support_files` (called at lines 478 and 482) removes any file that exists only under `src/`. In check mode it reports the extra file as drift without deleting it.

So a file created only under `src/claude/skills/<name>/` disappears on the next build, and an edit to a mirrored file is overwritten. `src/claude/AGENTS.md` says the same: edit the `.claude/skills/<name>/` source.

## Sources

- `build/scripts/skill_support_mirror.py`: module docstring, `_prune_stale_support_files` (line 291), call sites at lines 478 and 482.
- `src/claude/AGENTS.md`, the `skills/<name>/` line under Matters.
- Verified for the Claude tree only. The Copilot tree pruning was not read.
- Related: `generator-skill-references-mirror-only-through-build-all`, which covers the Copilot copy and the missed-rebuild cost.
