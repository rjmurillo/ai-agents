# Claude Code Instructions

@AGENTS.md

## Claude Code Specifics

Non-trivial task, delegate to specialized agents via Task tool:

- `Task(subagent_type="orchestrator")` for multi-step coordination
- `Task(subagent_type="Explore")` for codebase exploration
- Specialized agents (implementer, architect, analyst, etc.) for focused work

### Installation Locations

| Type | Agents | Commands |
|------|--------|----------|
| Global | `~/.claude/agents/` | `~/.claude/commands/` |
| Per-repo | `.claude/agents/` | `.claude/commands/` |

### Default Behavior

Non-trivial task: `Task(subagent_type="orchestrator", prompt="...")`

## Memory Interface Decision Matrix

| Scenario | Use | Why |
|----------|-----|-----|
| Quick CLI search | `/memory-search` slash command | Instant, no agent overhead |
| Deep exploration | `context-retrieval` agent | Graph traversal, artifact reading |
| Script automation | `Search-Memory.ps1` | PowerShell, testable, structured output |
| Direct MCP (last resort) | `mcp__serena__read_memory` | Full control when abstractions fail |

Start cheapest. Escalate only when cheaper lack capability.

## Path-scoped instructions

Before edit any file, read matching rules in `.claude/rules/*.md`. Each file `applyTo` frontmatter target path glob. Universal rules live in `.claude/rules/universal.md`.

Planned build extension ship Copilot-compatible copies to `.github/instructions/` from same source.

## Skill routing

User request match available skill, ALWAYS invoke via Skill tool as FIRST action. No answer direct, no other tools first. Skill have specialized workflows beat ad-hoc answers.

Key routing rules:
- Bugs, errors, "why is this broken" → invoke analyze skill
- PRs, issues, GitHub operations → invoke github skill
- PR review threads, comment triage → invoke pr-comment-responder skill
- Weekly retro → invoke reflect skill
- Save progress, checkpoint → invoke session-end skill
- Code quality, health check → invoke quality-grades skill

## Lifecycle commands

Dev lifecycle phases, use slash commands (not skills):
- Define requirements, "what should we build" → /spec
- Plan work, break down tasks, estimate → /plan
- Implement, code, build features → /build
- Test, prove it works, debug failures → /test
- Review code, check my diff, architecture review → /review
- Ship, deploy, push, create PR → /ship