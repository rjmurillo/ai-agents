# Retrospective: Parallel Agent Execution Learnings (2025-12-24)

**Session**: 04
**Context**: Launched 4 parallel pr-comment-responder agents via worktrees

## Critical Misses

### MISS-001: Token Explosion

- Agent a16199b consumed 4.2M+ tokens reviewing 25 comments
- No budget enforcement, no early termination
- **Fix**: Add "500K token budget" to agent prompts with checkpoint behavior

### MISS-002: Worktree Location

- Created at `/home/claude/worktree-pr-N` (home directory pollution)
- Should use dedicated parent: `/home/claude/ai-agents-worktrees/pr-N`
- **Fix**: Mkdir parent first, standardize location

### MISS-003: Detached HEAD

- `git worktree add ../path origin/branch` creates detached HEAD
- Agents had to checkout branch explicitly
- **Fix**: Use `git worktree add -b local-branch ../path origin/remote-branch`

### MISS-004: No Rate Limit Check

- Launched 4 agents making parallel API calls
- No budget reservation or coordination
- **Fix**: `gh api rate_limit --jq '.rate.remaining'` before parallel ops

### MISS-005: Duplicate Tool Calls

- Agents showing many duplicate consecutive commands
- Indicates retry logic or uncertainty
- **Fix**: Investigate cause, add idempotency hints

## Patterns Extracted

### Skill-Parallel-001: Worktree Isolation

```bash
mkdir -p /home/claude/ai-agents-worktrees
git worktree add -b pr-N ../ai-agents-worktrees/pr-N origin/branch
```

### Skill-Parallel-002: Rate Limit Pre-Check

```bash
remaining=$(gh api rate_limit --jq '.rate.remaining')
[[ $remaining -lt $required ]] && exit 1
```

### Skill-Agent-003: Token Budget

Add to agent prompts: "Complete within 500K tokens. If approaching limit: save state, emit summary, list remaining, exit cleanly."

## Statistics

- 4 agents launched in parallel
- 2 completed, 2 running long
- PR #300: 5 comments, 1 fix commit
- PR #285: 86 comments (all pre-addressed)
- Token cost: 4M+ on single agent (excessive)

## Cross-Reference

- Retrospective: `.agents/retrospective/2025-12-24-session-04-10-iteration-retrospective.md`
- Memory: `automation-priorities-2025-12` (memory-index proposal)
- Memory: `velocity-analysis-2025-12-23` (bot signal quality)
