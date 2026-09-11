# src/claude/

31 hand-maintained Claude Code agents (`<name>.md`) plus `claude-instructions.template.md` and
`security/references/`. Not generated. Installed copy lands at `.claude/agents/<name>.md`; edit
here, never the install. Rules: `claude-agents.md`, `plugin-self-containment.md`, `plugin-version-bump.md`.

## Change protocol

| Change | Edit |
|---|---|
| Claude-only (MCP tool names, Serena, `Task` syntax) | `src/claude/<agent>.md` only |
| Shared behavior | `src/claude/<agent>.md` + `templates/agents/<agent>.shared.md` + `.claude/agents/<agent>.md` + `.github/agents/<agent>.agent.md`, then `uv run python build/generate_agents.py`; one commit |

Parity gate checks the four moved together, not that text agrees. Drift gate scores this tree
against `src/vs-code-agents/` at 80% weekly. Paths other than this tree exist in the
`rjmurillo/ai-agents` repository, not in an installed plugin. ADR-036 procedure runs; ADR-052 is
accepted target state, not implemented.

## File contract

- Frontmatter: `name`, `description` (drives `Task` routing), `metadata.role`, `argument-hint`, `tools` (block list). `model:` omitted unless `haiku` with `model-rationale:` (ADR-080).
- Sections: Core Identity, Activation Profile, Claude Code Tools, Core Mission, Key Responsibilities, Constraints, Memory Protocol, Handoff Options, Output Format.
- Tool syntax `mcp__<server>__<tool>`. Memory search: `"${CLAUDE_PLUGIN_ROOT:-.claude}/skills/memory/scripts/search_memory.py"`.
- GitHub operations through `"${CLAUDE_PLUGIN_ROOT:-.claude}/skills/github/scripts/..."`, never raw `gh` when a script exists.
- MUST NOT cite `.agents/` or other upstream-only paths without a `vendor-portability` declaration.
- Invoke: `Task(subagent_type="<name>", prompt="...")`.

Backporting from an installed `.claude/agents/` copy: diff first; installed copies can lose blocking sections (ADR review enforcement, security gates).
