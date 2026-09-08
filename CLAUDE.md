# Claude Code Instructions

@AGENTS.md

## Claude Code Specifics

For non-trivial tasks, delegate to specialized agents via Task tool:

- `Task(subagent_type="orchestrator")` for multi-step coordination
- `Task(subagent_type="Explore")` for codebase exploration
- Specialized agents (implementer, architect, analyst, etc.) for focused work

### Installation Locations

| Type | Agents | Skills |
|------|--------|--------|
| Global | `~/.claude/agents/` | `~/.claude/skills/` |
| Per-repo | `.claude/agents/` | `.claude/skills/` |

ADR-064 retired `.claude/commands/`. Skills are the single user-invocable
surface, and a blocking validator refuses a command file under any plugin root.

### Default Behavior

For non-trivial tasks: `Task(subagent_type="orchestrator", prompt="...")`

## Memory Interface Decision Matrix

| Scenario | Use | Why |
|----------|-----|-----|
| Quick CLI search | `/memory-search` slash command | Instant, no agent overhead |
| Deep exploration | `context-gather` skill | Multi-source gather, artifact reading |
| Script automation | `search_memory.py` | Python CLI, testable, structured output |
| Direct MCP (last resort) | `mcp__serena__read_memory` | Full control when abstractions fail |

Start with cheapest option. Escalate only when cheaper option lacks capability.

## Path-scoped instructions

Before editing any file, read matching rules in `.claude/rules/*.md`. Each file's `paths` frontmatter targets a path glob; that is the key Claude Code reads, and `scripts/validation/check_rule_scope_keys.py` refuses any other. Universal rules live in `.claude/rules/universal.md`.

Planned build extension ships Copilot-compatible copies to `.github/instructions/` from same source.

## Skill routing

Explicit skill invocations still win: when the request names an available skill or uses that skill's slash command, invoke that skill first. Concrete requests that name no skill go through `/autoplan` below.

`/autoplan` is the canonical intent router for concrete requests that name no skill, per ADR-078. It routes to skills, lifecycle commands, and agent handoffs (for example orchestrator for multi-step work), not skills alone. Keep the routing table in `.claude/skills/autoplan/SKILL.md`; do not duplicate it here.

Explicit routing rules not owned by autoplan:
- Weekly retro → invoke reflect skill

## Lifecycle skills

Dev lifecycle phases. ADR-064 retired `.claude/commands/`, so these are skills
like every other user-invocable surface; `/spec` and the rest still type the same
because Claude Code fires a `user-invocable` skill by name:
- Define requirements, "what should we build" → spec
- Plan work, break down tasks, estimate → plan
- Implement, code, build features → build
- Test, prove it works, debug failures → test
- Review code, check my diff, architecture review → review
- Ship, deploy, push, create PR → ship