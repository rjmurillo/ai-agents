# Claude Code Instructions

@AGENTS.md

## Claude Code Specifics

For non-trivial tasks, delegate to specialized agents via Task tool:

- `Task(subagent_type="orchestrator")` for multi-step coordination
- `Task(subagent_type="Explore")` for codebase exploration
- Specialized agents (implementer, architect, analyst, etc.) for focused work

### Installation Locations

| Type | Agents | Commands |
|------|--------|----------|
| Global | `~/.claude/agents/` | `~/.claude/commands/` |
| Per-repo | `.claude/agents/` | `.claude/commands/` |

### Default Behavior

For non-trivial tasks: `Task(subagent_type="orchestrator", prompt="...")`

## Memory Interface Decision Matrix

| Scenario | Use | Why |
|----------|-----|-----|
| Quick CLI search | `/memory-search` slash command | Instant, no agent overhead |
| Deep exploration | `exploring-knowledge-graph` skill | Graph traversal, artifact reading |
| Script automation | `search_memory.py` | Python CLI, testable, structured output |
| Direct MCP (last resort) | `mcp__serena__read_memory` | Full control when abstractions fail |

Start with cheapest option. Escalate only when cheaper option lacks capability.

## Path-scoped instructions

Before editing any file, read matching rules in `.claude/rules/*.md`. Each file's `applyTo` frontmatter targets a path glob. Universal rules live in `.claude/rules/universal.md`.

Planned build extension ships Copilot-compatible copies to `.github/instructions/` from same source.

## Skill routing

If the user explicitly names an available skill or uses that skill's slash trigger, ALWAYS invoke via Skill tool as FIRST action. Do not answer directly, do not use other tools first. Skills have specialized workflows that beat ad-hoc answers.

`/autoplan` is the canonical intent router for concrete requests that name no skill, per ADR-078. It routes to skills, lifecycle commands, and agent handoffs (for example orchestrator for multi-step work), not skills alone. Keep the routing table in `.claude/skills/autoplan/SKILL.md`; do not duplicate it here.

Explicit routing rules not owned by autoplan:
- Weekly retro → invoke reflect skill

## Lifecycle commands

Dev lifecycle phases, use slash commands (not skills):
- Define requirements, "what should we build" → /spec
- Plan work, break down tasks, estimate → /plan
- Implement, code, build features → /build
- Test, prove it works, debug failures → /test
- Review code, check my diff, architecture review → /review
- Ship, deploy, push, create PR → /ship