# Issue #2666: programming-advisor missing top-level frontmatter version

## Problem
`.claude/skills/programming-advisor/SKILL.md` frontmatter had `version` only nested
under `metadata:` (alongside `model`). The skill frontmatter standard
(`.claude/skills/CLAUDE.md`, `.claude/rules/claude-agents.md` MUST-2) requires a
top-level `version` field. SkillForge gotcha: `version` and `model` MUST be
top-level YAML keys, not nested under `metadata:`.

## Fix
Added one line, top-level `version: 1.0.0`, to the canonical SKILL.md, matching
the existing nested `metadata.version: 1.0.0`. Did NOT touch nested `model`
(issue scope was version only, "no other change").

## Generator behavior
`programming-advisor` HAS a copilot mirror at
`src/copilot-cli/skills/programming-advisor/SKILL.md` (no vs-code-agents mirror).
`build/scripts/build_all.py` propagated the top-level version to the mirror
deterministically; the only changed mirror file was programming-advisor. The
follow-up PR maintenance pass bumped both project-toolkit manifests to 0.5.212
because the plugin skill sources changed, main already carried 0.5.211, and
installs must re-sync.

## Validation
- `scripts/validation/skill_frontmatter.py --changed-files <canonical>`: PASS.
- `pre_pr.py`: 25 passed, 0 failed, 4 skipped, All validations passed.
- Skill SKILL.md paths are markdownlint-config-ignored (`!.claude/skills/**`,
  `!src/copilot-cli/skills/**`); pre_pr Markdown Linting validation still PASSED.

## Branch / commits
fix/2666-programming-advisor-frontmatter-version off origin/main eff30e3ab4.
Canonical edit + generated mirror committed separately (generated-output
commits separate per AGENTS boundaries).
