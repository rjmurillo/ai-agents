## Constraints

- Every `.md` under `agents/` needs a non-empty `description:`; the loader registers any file there as a subagent regardless. Pre-PR `Agent Tree Frontmatter (.claude/agents)` fails on a miss, no allowlist. Fix the template, never here.
- Adding a per-call event (`PreToolUse`, `PostToolUse`, `PermissionRequest`, `PostToolUseFailure`): clear every MUST in `tool-use-hook-bar.md` (auto-loads for `settings.json`). The four session-boundary entries are outside it.
