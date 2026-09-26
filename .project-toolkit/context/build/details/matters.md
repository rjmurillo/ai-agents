## Matters

- `build_all.py --check`: drift gate over `_effective_owned_prefixes` (`OWNED_PREFIXES` plus each `.claude/skills/<name>/SKILL.md`).
- Per-class render map (agents, rules, skills, hooks, settings, prompts): `templates/AGENTS.md`.
- REQ-003-010: generators write under `.claude/` only via `binplace_manifest.claude_allowlist()`: agents, rules, skill `SKILL.md`, `hooks/` plus `hooks.json`, `settings.json`, `lib/<pkg>/`, `lib/bootstrap.py`, the review sidecar; `NO-REGEN` paths (`regen_guard.py`) excluded.
- `validate_install_parity.py` reports no violation ever; `validate-generated-agents.yml` still runs it (exit 2 on base-ref alone); `check_agent_content_parity.py` is the live byte gate.
- Lib renders inside the same run (`lib_mirror.py`, ADR-109 B5); `scripts/sync_plugin_lib.py` is a deprecated shim, never a prerequisite.
