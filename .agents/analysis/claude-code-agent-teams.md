# Claude Code Agent Teams: Comprehensive Analysis

**Date**: 2026-02-07
**Source**: https://code.claude.com/docs/en/agent-teams
**Status**: Experimental (disabled by default)

## Executive Summary

Claude Code Agent Teams is an experimental feature enabling coordination of multiple Claude Code instances working together. Unlike subagents (which run within a single session), agent teams consist of independent Claude instances that can communicate with each other directly, share task lists, and self-coordinate.

**Key distinction from our current ai-agents system**: Our system uses subagents (Task tool with subagent_type) where results return to the caller. Agent teams are fully independent sessions that message each other directly.

## Core Concepts

### Architecture Components

| Component | Role |
|-----------|------|
| **Team Lead** | Main Claude Code session that creates the team, spawns teammates, and coordinates work |
| **Teammates** | Separate Claude Code instances that each work on assigned tasks |
| **Task List** | Shared list of work items that teammates claim and complete |
| **Mailbox** | Messaging system for communication between agents |

### Storage Locations

```text
~/.claude/teams/{team-name}/config.json  # Team configuration with members array
~/.claude/tasks/{team-name}/             # Task list storage
```

### Team Configuration

The team config contains a `members` array with each teammate's name, agent ID, and agent type. Teammates can read this file to discover other team members.

## When to Use Agent Teams vs Subagents

| Aspect | Subagents | Agent Teams |
|--------|-----------|-------------|
| **Context** | Own context window; results return to caller | Own context window; fully independent |
| **Communication** | Report results back to main agent only | Teammates message each other directly |
| **Coordination** | Main agent manages all work | Shared task list with self-coordination |
| **Best for** | Focused tasks where only result matters | Complex work requiring discussion/collaboration |
| **Token cost** | Lower: results summarized back | Higher: each teammate is separate Claude instance |

### Use Cases Favoring Agent Teams

1. **Research and review**: Multiple teammates investigate different aspects simultaneously, then share and challenge findings
2. **New modules/features**: Teammates each own separate pieces without stepping on each other
3. **Debugging with competing hypotheses**: Test different theories in parallel, converge faster
4. **Cross-layer coordination**: Changes spanning frontend, backend, tests, each owned by different teammate

### Use Cases Favoring Subagents

1. Sequential tasks
2. Same-file edits
3. Work with many dependencies
4. Tasks where only the result matters, not the process

## Enabling Agent Teams

### Via Environment Variable

```bash
export CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1
```

### Via settings.json

```json
{
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  }
}
```

## Display Modes

### In-Process Mode (Default)

All teammates run inside main terminal. Use Shift+Up/Down to select a teammate, type to message. Works in any terminal.

### Split-Pane Mode

Each teammate gets own pane. Requires tmux or iTerm2. Configuration:

```json
{
  "teammateMode": "tmux"  // or "in-process" or "auto"
}
```

Command line override:

```bash
claude --teammate-mode in-process
```

## Communication Patterns

### Automatic Message Delivery

When teammates send messages, they're delivered automatically. Lead doesn't need to poll.

### Idle Notifications

When teammate finishes and stops, they automatically notify the lead.

### Messaging Options

1. **message**: Send to one specific teammate
2. **broadcast**: Send to all teammates (use sparingly, costs scale with team size)

## Task Management

### Task States

1. **pending**: Not yet started
2. **in_progress**: Being worked on
3. **completed**: Finished

### Task Dependencies

Tasks can depend on other tasks. Pending task with unresolved dependencies cannot be claimed until dependencies complete. System manages this automatically.

### Task Claiming

Uses file locking to prevent race conditions when multiple teammates try to claim same task simultaneously.

### Claiming Modes

1. **Lead assigns**: Tell lead which task to give to which teammate
2. **Self-claim**: Teammate picks up next unassigned, unblocked task

## Plan Approval Workflow

For complex/risky tasks, require plan approval:

```text
Spawn an architect teammate to refactor the authentication module.
Require plan approval before they make any changes.
```

Workflow:
1. Teammate works in read-only plan mode
2. Teammate sends plan approval request to lead
3. Lead reviews and approves or rejects with feedback
4. If rejected, teammate revises and resubmits
5. Once approved, teammate exits plan mode and implements

The lead makes decisions autonomously. Influence judgment via prompt criteria: "only approve plans that include test coverage."

## Delegate Mode

Restricts lead to coordination-only tools: spawning, messaging, shutting down teammates, managing tasks. Prevents lead from implementing tasks itself.

Enable: Press Shift+Tab to cycle into delegate mode after team starts.

## Quality Gate Hooks

### TeammateIdle Hook

Runs when teammate about to go idle. Exit code 2 sends feedback and keeps teammate working.

### TaskCompleted Hook

Runs when task being marked complete. Exit code 2 prevents completion and sends feedback.

## Permissions Model

Teammates start with lead's permission settings. If lead runs with `--dangerously-skip-permissions`, all teammates do too.

Can change individual teammate modes after spawning, but cannot set per-teammate modes at spawn time.

## Context Loading

Teammates load same project context as regular session:
- CLAUDE.md files
- MCP servers
- Skills
- Spawn prompt from lead

Lead's conversation history does NOT carry over.

## Token Usage Considerations

Token usage scales with number of active teammates. Each teammate has own context window. For research, review, new features: usually worthwhile. For routine tasks: single session more cost-effective.

## Best Practices

### 1. Give Teammates Enough Context

Include task-specific details in spawn prompt since conversation history doesn't transfer:

```text
Spawn a security reviewer teammate with the prompt: "Review the authentication module
at src/auth/ for security vulnerabilities. Focus on token handling, session
management, and input validation. The app uses JWT tokens stored in
httpOnly cookies. Report any issues with severity ratings."
```

### 2. Size Tasks Appropriately

- **Too small**: Coordination overhead exceeds benefit
- **Too large**: Teammates work too long without check-ins
- **Just right**: Self-contained units producing clear deliverable (function, test file, review)

Guideline: 5-6 tasks per teammate keeps everyone productive.

### 3. Wait for Teammates to Finish

If lead starts implementing instead of waiting:

```text
Wait for your teammates to complete their tasks before proceeding
```

### 4. Avoid File Conflicts

Two teammates editing same file leads to overwrites. Break work so each teammate owns different files.

### 5. Monitor and Steer

Check in on progress, redirect approaches not working, synthesize findings as they come.

## Failure Modes and Anti-Patterns

### Failure Mode 1: Coordination Overhead Exceeds Benefit

**Symptom**: Sequential tasks split across teammates
**Correction**: Use subagents or single session for sequential work

### Failure Mode 2: File Conflict Race Conditions

**Symptom**: Two teammates editing same file, overwrites occur
**Correction**: Assign distinct file ownership per teammate

### Failure Mode 3: Lead Implements Instead of Delegating

**Symptom**: Lead starts coding instead of coordinating
**Correction**: Use delegate mode or explicit instruction to wait

### Failure Mode 4: Insufficient Context for Teammates

**Symptom**: Teammates ask clarifying questions or go wrong direction
**Correction**: Include detailed context in spawn prompts

### Failure Mode 5: Tasks Too Large

**Symptom**: Teammates work too long without check-ins, wasted effort on wrong approaches
**Correction**: Break into smaller tasks, 5-6 per teammate

### Failure Mode 6: Orphaned Resources

**Symptom**: tmux sessions persist after team ends
**Correction**: Always use lead to clean up, shut down teammates first

## Current Limitations

1. **No session resumption with in-process teammates**: `/resume` and `/rewind` don't restore teammates
2. **Task status can lag**: Teammates sometimes fail to mark tasks completed
3. **Shutdown can be slow**: Teammates finish current request before shutting down
4. **One team per session**: Lead manages only one team at a time
5. **No nested teams**: Teammates cannot spawn their own teams
6. **Lead is fixed**: Cannot promote teammate to lead or transfer leadership
7. **Permissions set at spawn**: All teammates start with lead's mode
8. **Split panes require tmux/iTerm2**: Not supported in VS Code terminal, Windows Terminal, Ghostty

## Applicability to ai-agents Project

### High-Value Integration Points

1. **Parallel PR Review**: Security, QA, and architect agents reviewing simultaneously with discussion capability
2. **Multi-faceted Investigation**: Analyst agents exploring competing hypotheses with debate
3. **Cross-concern Feature Implementation**: Frontend, backend, test implementation by separate teammates

### Current Architecture Alignment

Our current subagent system aligns well with agent teams' comparison:

| Our Subagents | Agent Teams |
|---------------|-------------|
| Task tool with subagent_type | Built-in team management |
| Results return to orchestrator | Direct teammate communication |
| Orchestrator coordinates | Shared task list, self-coordination |

### Migration Considerations

**If adopting agent teams:**
1. Evaluate token cost increase vs coordination benefit
2. Consider hybrid: subagents for focused work, teams for complex collaboration
3. Integrate hooks (TeammateIdle, TaskCompleted) with session protocol
4. Map existing agent roles to teammate specializations

### Recommended Use Cases for This Project

1. **ADR Review Debates**: Currently sequential agent reviews could become parallel with direct discussion
2. **PR Quality Gates**: Security, QA, analyst could review simultaneously and challenge each other
3. **Complex Refactoring**: Module owners implementing in parallel with coordination

## Action Items

### Immediate (No Implementation Required)

1. Document awareness of agent teams feature
2. Monitor experimental feature for stability updates
3. Consider for future ADR on multi-agent coordination evolution

### Future Consideration (When Stable)

1. Evaluate pilot with ADR review process
2. Measure token cost vs time savings
3. Integrate with session protocol for team session tracking

## Related Concepts

- **Subagents**: Existing mechanism for parallel work within single session
- **Git Worktrees**: Manual parallel sessions without automated coordination
- **ADR-009**: Parallel-safe multi-agent design (consensus mechanisms)
- **ADR-007**: Memory-first architecture (context sharing)

## Sources

1. Claude Code Documentation: https://code.claude.com/docs/en/agent-teams
2. Subagents Documentation: https://code.claude.com/docs/en/sub-agents
3. Hooks Documentation: https://code.claude.com/docs/en/hooks
4. Permissions Documentation: https://code.claude.com/docs/en/permissions

## Appendix: Example Prompts

### Research Team

```text
Create an agent team to research this architectural decision from different angles:
- One teammate on technical feasibility
- One on operational impact
- One on security implications
Have them challenge each other's assumptions before synthesizing.
```

### Parallel Code Review

```text
Create an agent team to review PR #142. Spawn three reviewers:
- One focused on security implications
- One checking performance impact
- One validating test coverage
Have them each review and report findings.
```

### Competing Hypotheses Investigation

```text
Users report the app exits after one message instead of staying connected.
Spawn 5 agent teammates to investigate different hypotheses. Have them talk to
each other to try to disprove each other's theories, like a scientific debate.
```
