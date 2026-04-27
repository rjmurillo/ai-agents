Acknowledging but not changing. These matchers were ported verbatim from `.claude/settings.json`, which has been working in production for this repo across all 7 hook events for months. The same pattern style appears in production plugins:

- `caveman/plugin.json` uses `"matcher": "Bash(git commit*)"` style with no anchoring
- `context-mode/hooks/hooks.json` uses `"matcher": "Bash|Read|Write|Edit|..."` (unanchored alternation)
- `security-guidance/hooks/hooks.json` omits `matcher` entirely

Claude Code's hook matcher engine accepts the `Tool(args*)` glob-like form alongside regex-style `^(Edit|Write)$` patterns. Changing them now would diverge from `.claude/settings.json` and risk breaking the in-repo hooks the team already relies on. If Anthropic publishes a stricter matcher grammar later, we'll port both files together.
