# Claude Code Plugin Manifest Schema

Captured 2026-04-27 during P0 incident response (PR #1773 broke plugin install for all consumers; fixed in PR #1795).

## Authoritative shape (`.claude-plugin/plugin.json`)

| Field | Type | Notes |
|---|---|---|
| `name` | string | **Required.** Plugin identifier. |
| `version`, `description`, `author`, `homepage`, `repository`, `license`, `keywords` | various | Standard metadata. |
| `agents` | string OR array of strings | Path(s) to agent dir. **Must start with `./`**. Omit to auto-discover from `./agents/`. |
| `skills` | string OR array of strings | Same rules as `agents`. Auto-discovers `./skills/`. |
| `commands` | string OR array of strings | Same rules. Auto-discovers `./commands/`. |
| `hooks` | object OR string | If object, must be `{ EventName: [{ matcher?, hooks: [{type:'command', command:'...'}] }] }`. If string, must be path to `*.json` file starting with `./`. **Pointing to a directory is INVALID.** |
| `mcpServers` | object | MCP server definitions. |

## `hooks/hooks.json` shape

Auto-discovered by Claude Code v2.1+ when present. **Must wrap event names under a `"hooks"` key**:

```json
{
  "description": "...",
  "hooks": {
    "PreToolUse": [
      { "matcher": "Bash", "hooks": [{ "type": "command", "command": "..." }] }
    ]
  }
}
```

Without the `"hooks"` wrapper, Claude Code does not load any events. Verified against `~/.claude/plugins/cache/context-mode/.../hooks/hooks.json` and `claude-plugins-official/security-guidance/.../hooks/hooks.json`.

Use `${CLAUDE_PLUGIN_ROOT}` in command paths so hooks work regardless of install location.

## Documented hook events (verified)

`PreToolUse`, `PostToolUse`, `Stop`, `SessionStart`, `SessionEnd`, `UserPromptSubmit`, `SubagentStop`, `PermissionRequest`, `Notification`, `PreCompact`.

cursor[bot] suggested adding 19 more (`PostToolUseFailure`, `SubagentStart`, `UserPromptExpansion`, etc.) — none of those appear in any production plugin or Anthropic docs as of 2026-04-27. Reject with citation request.

## Common bug patterns (regression class from PR #1773)

1. **`hooks` as dict-of-directories** (`{ "PreToolUse": "./hooks/PreToolUse" }`): rejected by Claude Code with "Validation errors: hooks: Invalid input". Use inline matcher format or string ref to `*.json` file.
2. **`agents`/`skills`/`commands` as array of dir paths without `./`**: rejected with "Invalid input".
3. **Stripping `agents` from a plugin whose agents live at root**: install succeeds but exposes zero agents. Restore as `"agents": "./"` (NOT `"."`).
4. **`hooks/hooks.json` without `"hooks"` wrapper**: events silently never fire.

## Validator + CI gate

Lives at `build/scripts/validate_plugin_manifests.py` + `.github/actions/validate-plugin-manifests/action.yml`. Catches all 4 bug patterns above. Unit tests in `tests/build_scripts/test_validate_plugin_manifests.py` (run `pytest` for current count). Workflow `.github/workflows/validate-plugin-manifests.yml` gates PRs touching plugin.json.

## References

- Anthropic Claude Code plugin docs: https://code.claude.com/docs/en/plugins-reference
- Reference plugins (working): `caveman`, `context-mode`, `claude-plugins-official/security-guidance`
- Incident PIR: `.agents/incidents/2026-04-27-pir-plugin-manifest-schema-1773.md`
- Session log: `.agents/sessions/2026-04-27-session-1759-fix-plugin-manifest-schema-regression.json`
