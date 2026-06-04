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
| Script automation | `Search-Memory.ps1` | PowerShell, testable, structured output |
| Direct MCP (last resort) | `mcp__serena__read_memory` | Full control when abstractions fail |

Start with cheapest option. Escalate only when cheaper option lacks capability.

## Path-scoped instructions

Before editing any file, read matching rules in `.claude/rules/*.md`. Each file's `applyTo` frontmatter targets a path glob. Universal rules live in `.claude/rules/universal.md`.

Planned build extension ships Copilot-compatible copies to `.github/instructions/` from same source.

## Skill routing

If user request matches available skill, ALWAYS invoke via Skill tool as FIRST action. Do not answer directly, do not use other tools first. Skills have specialized workflows that beat ad-hoc answers.

Key routing rules:
- Bugs, errors, "why is this broken" → invoke analyze skill
- PRs, issues, GitHub operations → invoke github skill
- PR review threads, comment triage → invoke pr-comment-responder skill
- Weekly retro → invoke reflect skill
- Save progress, checkpoint → invoke session-end skill
- Code quality, health check → invoke quality-grades skill
- New capability proposed (Context, new module/scanner/validator/pipeline component) → invoke buy-vs-build-framework skill (Quick tier minimum) BEFORE /spec generates artifacts. Skip for pure bug fixes, doc-only changes, refactors with no new capability surface, or extensions of an already-approved capability that add no new tool/scanner/validator.

## Lifecycle commands

Dev lifecycle phases, use slash commands (not skills):
- Define requirements, "what should we build" → /spec
- Plan work, break down tasks, estimate → /plan
- Implement, code, build features → /build
- Test, prove it works, debug failures → /test
- Review code, check my diff, architecture review → /review
- Ship, deploy, push, create PR → /ship