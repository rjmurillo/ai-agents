# src/claude/

31 hand-maintained Claude Code agent prompts; the `claude-agents` plugin source in the `rjmurillo/ai-agents` repository, installed by Claude Code as `.claude/agents/<name>.md`.

## Matters

- 31 agent files (`<name>.md`), plus `claude-instructions.template.md` (no frontmatter, not an agent) and `security/references/` (docs the `security` agent points at). None of it is generated: the drift checker's own comment states "Claude agents have unique content and are NOT generated from templates."
- `name`, `description`, `argument-hint` appear in all 31 files. `metadata.role` in 25 of 31. A `tools:` frontmatter list in only 2 of 31 (`analyst`, `security`). A `model:` pin in exactly 1 of 31 (`code-reviewer: haiku`, with a required `model-rationale:` line, per ADR-080).
- No enforced section structure. Measured across the 31 files: `## Core Identity` appears in 17, `## Constraints` in 10, `## Memory Protocol` in 13, `## Handoff Options` in 13, `## Output Format` in 7. Grep the specific file before assuming a heading exists.
- Changing shared agent behavior means editing this file AND, in the `rjmurillo/ai-agents` repository, `templates/agents/<name>.shared.md`, `.claude/agents/<name>.md`, and `.github/agents/<name>.agent.md` in the same change, then regenerating. The automated co-change check only confirms the diff touched the required siblings; nothing compares their text.
- All 31 files are byte-identical to their `.claude/agents/` installed copies today (verified by diff). That is upheld by convention plus the co-change check, not a content gate, so re-diff rather than assume it still holds.

## Entry points

- `<name>.md`: edit directly for Claude-only behavior (MCP tool ids, Serena calls, `Task` syntax).
- `Task(subagent_type="<name>", prompt="...")`: how another Claude Code agent invokes one of these.
- In the `rjmurillo/ai-agents` repository: `uv run python build/generate_agents.py`, run after any shared-behavior edit to refresh the generated Copilot CLI and VS Code mirrors.

## Where to look

| Path | Why |
|---|---|
| `<name>.md` | One agent's full prompt: frontmatter plus body |
| `claude-instructions.template.md` | Shared preamble text, not an agent; carries no frontmatter and no template counterpart |
| `security/references/` | Threat-model and checklist references the `security` agent's prompt points to |
| `merge-resolver.md`, `pr-comment-responder.md`, `quality-auditor.md` | The three agents that hard-code a `${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/...` script path (merge-resolver uses the older single-variable form; see Dangerous assumptions) |

## Skip

- Nothing under this tree is generated, so there is no output copy to avoid editing here; the trap runs the other way (see Dangerous assumptions).
- `.claude/agents/<name>.md`, `.github/agents/<name>.agent.md` (in the `rjmurillo/ai-agents` repository): sibling installed copies, edited alongside this tree, never instead of it.

## Constraints

- Cross-harness behavior: read `agent-harness-reference` first; hook, event, or generated-Copilot changes run through `ai-agents-portability-campaign`.
- An agent file here MUST NOT reference `.agents/`, `build/`, or `scripts/` paths that will not exist for a downstream installer of this plugin.
- A `model:` field MUST NOT be added without an ADR-080 `KEEP_PIN` manifest entry, or the `haiku` cost exception plus a `model-rationale:` line.
- Changing shared behavior MUST also touch `templates/agents/<name>.shared.md` in the repository; the repository's parity check fails a solo template edit but does not fail a solo edit to this file alone, so the discipline is on the author, not the gate.
- A script path built from `${CLAUDE_PLUGIN_ROOT:-.claude}` resolves correctly only two ways: unset, falling back to `.claude/` (in-repo dev use), or set to a plugin root that itself ships a `skills/` directory. `src/claude/` ships none, so this pattern only works when the `project-toolkit` plugin (`.claude/`) is also installed alongside `claude-agents`.
- GitHub operations should route through a `skills/github/scripts/...` script rather than raw `gh`, and memory search through a `skills/memory/scripts/search_memory.py` script, subject to the availability constraint above.

## Dangerous assumptions

- Assuming a passing drift check means an agent here agrees with its `src/vs-code-agents/` counterpart is wrong: the check is a word-set similarity floor over an allowlist of section names, not equality, and several comparisons score a hardcoded 100.0 when the agent has none of the allowlisted sections at all.
- Assuming the shared-template "required sections" list (`templates/README.md`: Core Identity, Core Mission, Key Responsibilities, Constraints, Memory Protocol, Handoff Options; Activation Profile is common but not on that list) holds for files in this tree is wrong: none of those headings appears in more than 17 of the 31 files, and nothing enforces the list here.
- Assuming `${CLAUDE_PLUGIN_ROOT:-.claude}/skills/...` always resolves for a `claude-agents`-only install is wrong: this plugin ships no `skills/` directory of its own (see Constraints).
- Assuming a solo edit here is safe because "the agent still works" ignores that no automated check requires the matching template edit in the same change; only the co-change diff check runs, and it does not require this direction.

## Dependencies

- Feeds `.claude/agents/<name>.md` (hand-copy, currently identical content) and is read, by filename only, by the repository's drift checker for the `src/claude` vs `src/vs-code-agents` comparison.
- The repository's parity check (co-change gate, blocks a solo template edit) and drift checker (similarity floor, weekly cron) are the only two automated checks over this tree; neither proves content agreement.
- Consumed by the `claude-agents` marketplace plugin entry, whose source is exactly this directory; nothing above it (docs, governance, build tooling) ships to an installer.

## Architecture

- This tree is a hand-maintained fork of the shared template body, not a generated copy: the shared source lives in a separate file per agent in the repository, and the two are kept in step by author discipline plus the co-change check, never by a tool that compares their content.
- Every one of the 31 agent files has a `templates/agents/<name>.shared.md` counterpart; `claude-instructions.template.md` has none, and the drift checker's skip list (`_NON_AGENT_FILENAMES`) covers only `AGENTS` and `CLAUDE`, so it is reported as `NO COUNTERPART`.

## Commands

```bash
# All of the following run from the rjmurillo/ai-agents repository root, not from an installed plugin.
uv run python build/generate_agents.py                                              # refresh Copilot CLI + VS Code mirrors after a shared edit
uv run python build/scripts/validate_install_parity.py --files src/claude/<name>.md  # check the co-change requirement
uv run python build/scripts/detect_agent_drift.py --changed src/claude/<name>.md     # scope the similarity check to one agent
```
