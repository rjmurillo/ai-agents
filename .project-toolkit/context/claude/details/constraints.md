## Constraints

- Every `.md` under `agents/` needs a non-empty `description:`; the loader registers any file there as a subagent regardless. Pre-PR `Agent Tree Frontmatter (.claude/agents)` fails on a miss, no allowlist. Fix the template, never here.
- Adding a per-call event (`PreToolUse`, `PostToolUse`, `PermissionRequest`, `PostToolUseFailure`): clear every MUST in `rule-tool-use-hook-bar.md` (`skillforge` skill). The five session-boundary entries are outside it.
