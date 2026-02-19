# Claude Code Agent Teams

**Status**: Experimental (disabled by default)
**Feature Flag**: `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`

## What It Is

Coordination of multiple Claude Code instances working together. One session acts as team lead, spawning and coordinating teammates. Each teammate is a separate Claude instance with its own context window.

## Key Difference from Subagents

| Subagents | Agent Teams |
|-----------|-------------|
| Results return to caller | Teammates message each other directly |
| Main agent manages all work | Shared task list, self-coordination |
| Lower token cost | Higher token cost (each teammate is separate instance) |

## Architecture

- **Team Lead**: Creates team, spawns teammates, coordinates
- **Teammates**: Independent Claude instances working on tasks
- **Task List**: Shared work items at `~/.claude/tasks/{team-name}/`
- **Mailbox**: Direct messaging between agents
- **Config**: `~/.claude/teams/{team-name}/config.json`

## Best Use Cases

1. Research/review with parallel investigation and discussion
2. New modules where each teammate owns separate files
3. Debugging competing hypotheses with scientific debate
4. Cross-layer changes (frontend/backend/tests)

## When NOT to Use

- Sequential tasks
- Same-file edits
- Work with many dependencies
- Routine tasks (single session more cost-effective)

## Display Modes

- **in-process**: All teammates in main terminal (Shift+Up/Down to select)
- **split-pane**: Each teammate gets own pane (requires tmux/iTerm2)

## Quality Gate Hooks

- `TeammateIdle`: Runs when teammate about to go idle. Exit 2 keeps them working.
- `TaskCompleted`: Runs when task marked complete. Exit 2 prevents completion.

## Project Applicability

Consider for:
- ADR review debates (parallel reviews with discussion)
- PR quality gates (security, QA, analyst reviewing simultaneously)
- Complex refactoring (module owners in parallel)

Current subagent system handles most cases well. Agent teams add value when teammates need to discuss and challenge each other.

## Limitations

- No session resumption with teammates
- One team per session
- No nested teams
- Lead is fixed (cannot transfer leadership)
- Split panes not in VS Code terminal

## Related

- ADR-009: Parallel-safe multi-agent design
- skills-orchestration-index
- Analysis: `.agents/analysis/claude-code-agent-teams.md`
