# Skill Sidecar Learnings: Copilot CLI Hooks

**Last Updated**: 2026-06-02
**Sessions Analyzed**: 1

## Constraints (HIGH confidence)

- Copilot CLI event name casing is load-bearing for payload field names. camelCase events send `toolName`/`toolArgs`, PascalCase events send `tool_name`/`tool_input`. Always use PascalCase in `eventRemap` to get snake_case payloads matching what hook scripts expect. (Session fix/2290, 2026-06-02)
- Verify stdin payload format empirically (probe plugin) before implementing shim dispatch logic. ADR-071 (formerly ADR-063, renumbered per #2228) verified env vars and cwd but NOT stdin field names. The cost of a probe is 15 minutes; the cost of assumption is a P0. (Session fix/2290, 2026-06-02)
- Never use raw `gh` commands in Claude Code sessions. Use `.claude/skills/github/scripts/` instead. `invoke_skill_first_guard` blocks raw `gh` calls. (Session fix/2290, 2026-06-02)

## Edge Cases (MED confidence)

- `toolArgs` in camelCase payloads is a raw JSON string, not a parsed dict. Must `json.loads()` before passing to `_shim_normalize_args`. PascalCase `tool_input` is already a parsed dict. (Session fix/2290, 2026-06-02)
- Exit code 143 from a hook = SIGTERM (timeout kill), not a payload crash. 30+ hooks running sequentially on Windows with Python process startup exceeds the timeout budget. Separate issue from payload format. (Session fix/2290, 2026-06-02)
- Runtime contract test `test_every_bash_command_resolves_to_an_existing_script` always fails on Windows due to bash env var pass-through bug. Linux CI is authoritative for this test. Pre-existing. (Session fix/2290, 2026-06-02)

## Preferences (MED confidence)

- When debugging Copilot CLI hook crashes, check the process log for exit code before assuming payload format. Code 143=timeout, 1=logic, 2=config. Different root causes need different fixes. (Session fix/2290, 2026-06-02)
- Dual-format defense (try snake_case then camelCase) is cheap insurance for any shim crossing a wire boundary where the producer format is not controlled by this repo. One extra `.get()` call, zero performance cost. (Session fix/2290, 2026-06-02)
