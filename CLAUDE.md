# Claude Code Instructions

@AGENTS.md

## Claude Code Specifics

For non-trivial tasks, delegate to specialized agents using the Task tool:

- `Task(subagent_type="orchestrator")` for multi-step coordination
- `Task(subagent_type="Explore")` for codebase exploration
- Specialized agents (implementer, architect, analyst, etc.) for focused work

### Installation Locations

| Type | Agents | Commands |
|------|--------|----------|
| Global | `~/.claude/agents/` | `~/.claude/commands/` |
| Per-repo | `.claude/agents/` | `.claude/commands/` |

### Default Behavior

For any non-trivial task: `Task(subagent_type="orchestrator", prompt="...")`

## Memory Interface Decision Matrix

| Scenario | Use | Why |
|----------|-----|-----|
| Quick CLI search | `/memory-search` slash command | Instant, no agent overhead |
| Deep exploration | `context-retrieval` agent | Graph traversal, artifact reading |
| Script automation | `Search-Memory.ps1` | PowerShell, testable, structured output |
| Direct MCP (last resort) | `mcp__serena__read_memory` | Full control when abstractions fail |

Start with the cheapest option. Escalate only when the cheaper option lacks capability.

## Skill routing

When the user's request matches an available skill, ALWAYS invoke it using the Skill
tool as your FIRST action. Do NOT answer directly, do NOT use other tools first.
The skill has specialized workflows that produce better results than ad-hoc answers.

Key routing rules:
- Bugs, errors, "why is this broken" → invoke analyze skill
- PRs, issues, GitHub operations → invoke github skill
- PR review threads, comment triage → invoke pr-comment-responder skill
- Weekly retro → invoke reflect skill
- Save progress, checkpoint → invoke session-end skill
- Code quality, health check → invoke quality-grades skill

## Lifecycle commands

For development lifecycle phases, use these slash commands (not skills):
- Define requirements, "what should we build" → /spec
- Plan work, break down tasks, estimate → /plan
- Implement, code, build features → /build
- Test, prove it works, debug failures → /test
- Review code, check my diff → /review
- Ship, deploy, push, create PR → /ship
