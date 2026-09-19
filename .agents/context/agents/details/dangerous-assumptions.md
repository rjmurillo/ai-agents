## Dangerous assumptions

- `hooks/hooks.yaml` retired, read by nothing; `hooks/README.md` misnames the live sources. ADR-109 B4: `templates/hooks/` is the source, `.claude/hooks/` and `.claude/settings.json` generated. Copilot map: `templates/platforms/copilot-cli.yaml`.
- Gate exemptions differ: `check_doc_interpreter_portability.py` `HISTORICAL_ROOTS` and `stale_script_refs.py` omit `metrics/`, `roadmap/`, `plans/`, `handoffs/`; a bare-interpreter call of a tracked script with a non-stdlib import, or a ref to a deleted `.ps1`, fails there.
- `AGENT-SYSTEM.md` stale: `**File**:` lines cite `src/claude/<stem>.md`; live is `src/claude/agents/<stem>.md` (generated, ADR-109 B1).
