# Skill support files: shipped skills are edited in src/claude/skills/<name>/

Correction, verified 2026-10-19: this note once said support files are sourced in `.claude/skills/<name>/` and pruned from `src/`. ADR-119 (PR #6718) reversed that. The filename keeps the old wording so existing links resolve.

## The source of truth

A shipped skill keeps its support files (scripts, references, tests) in `src/claude/skills/<name>/`, hand-maintained. `.claude/skills/<name>` is a git symlink to that directory. `SKILL.md` renders from `templates/skills/<name>.SKILL.md.tmpl`.

Repo-local skills are the exception. A skill flagged `distribution: repo-local` keeps real files in `.claude/skills/<name>/` and appears in no plugin tree. The flag decides this, not the name prefix: `ai-agents-external-claims` is shipped and is a symlink, while most other `ai-agents-*` skills and the `repository-*` skills are repo-local. `repo_local_names` in `build/scripts/skill_distribution.py` computes the set.

## What the build does

There is no mirror of support files into the Claude tree. `prune_stale_claude_skill_support` in `build/scripts/skill_support_mirror.py` only removes a leftover `src/claude/skills/<name>/` copy after a skill becomes repo-local. It refuses while `.claude/skills/<name>` is still a symlink.

So edit shipped support files in `src/claude/skills/<name>/`, and never replace a link with a real file. A file created under `src/claude/skills/<name>/` survives the build.

## Sources

- `build/scripts/skill_support_mirror.py`: module docstring and `prune_stale_claude_skill_support`.
- `build/scripts/skill_distribution.py`: `repo_local_names`.
- Verified for the Claude tree only. The Copilot tree mirror was not re-read.
- Related: `generator-skill-references-mirror-only-through-build-all`, which covers the Copilot copy and the missed-rebuild cost.
