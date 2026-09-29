## Constraints

- Every `.md` under `agents/` needs a non-empty `description:`; the loader registers any file there as a subagent regardless. Pre-PR `Agent Tree Frontmatter (.claude/agents)` fails on a miss, no allowlist. Fix the template, never here.
- Every direct child of `skills/` must be a directory with a `SKILL.md`; the loader registers a loose file there as a skill (`CLAUDE.md` registered as `CLAUDE`, issue #5503). Pre-PR `Skill Tree Layout (.claude/skills)` fails on a miss, no allowlist. Skill conventions live in `skills/skillforge/references/skill-development-conventions.md`.
- Adding a per-call event (`PreToolUse`, `PostToolUse`, `PermissionRequest`, `PostToolUseFailure`): clear every MUST in `tool-use-hook-bar.md` (auto-loads for `settings.json`). The four session-boundary entries are outside it.
