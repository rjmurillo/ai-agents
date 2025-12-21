# ADR-008: Protocol Automation via Lifecycle Hooks

## Status

Accepted

## Date

2025-12-20

## Context

The ai-agents system relies on SESSION-PROTOCOL.md for consistency, but compliance depends on agent discipline:

1. **Manual enforcement**: Agents must remember to create session logs, read HANDOFF.md, etc.
2. **Protocol drift**: Under time pressure, agents skip steps
3. **Inconsistent artifacts**: Some sessions have complete logs, others have none
4. **No verification**: No automated check that protocol was followed

Research into [ruvnet/claude-flow](https://github.com/ruvnet/claude-flow) revealed comprehensive lifecycle hooks:

- Pre/post task hooks for validation and cleanup
- Session start/end hooks for context management
- File modification hooks for format enforcement
- Auto-save middleware with 30-second intervals

These hooks achieve 10-20x faster batch agent spawning by automating setup that would otherwise be manual.

## Decision

**Lifecycle hooks MUST automate SESSION-PROTOCOL enforcement.**

Specifically:

1. **Pre-session hook**: Auto-create session log, verify HANDOFF.md exists
2. **Post-session hook**: Run markdown lint, update HANDOFF.md, commit artifacts
3. **Pre-commit hook**: Validate session log format, check for uncommitted memories
4. **File modification hooks**: Enforce consistent formatting on save

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Manual discipline | No tooling required | Unreliable, drift | Current pain point |
| CI-only validation | Catches issues eventually | Too late, no prevention | Feedback loop too slow |
| Lifecycle hooks | Prevents issues, automates | Implementation effort | **Chosen** |

### Trade-offs

- **Complexity**: Hook system adds moving parts
- **Flexibility reduction**: Hooks enforce patterns even when deviation might be appropriate
- **Debugging difficulty**: Automated actions harder to trace than manual ones

## Consequences

### Positive

- Protocol compliance becomes automatic, not aspirational
- Consistent artifact structure across all sessions
- Reduced cognitive load - agents focus on task, not bookkeeping
- Session checkpointing enables pause/resume (Issue #174)

### Negative

- Hook failures can block work
- Over-automation may mask understanding gaps
- Configuration complexity for hook customization

### Neutral

- Shifts protocol enforcement from runtime to configuration

## Implementation Notes

### Hook Types (from claude-flow research)

| Hook | Trigger | Action |
|------|---------|--------|
| `session.start` | Session begins | Create log, retrieve context |
| `session.end` | Session closes | Update HANDOFF, lint, commit |
| `task.pre` | Before task execution | Validate prerequisites |
| `task.post` | After task completion | Store learnings |
| `file.modify` | File saved | Format validation |
| `commit.pre` | Before git commit | Lint, artifact check |

### Phase 5A Implementation Order

1. Session start/end hooks (highest value)
2. Commit hooks (prevent broken artifacts)
3. Task hooks (advanced automation)

## Related Decisions

- ADR-007: Memory-First Architecture (hooks enforce retrieval)
- ADR-004: Pre-Commit Hook Architecture (existing foundation)
- SESSION-PROTOCOL.md (defines what hooks enforce)

## References

- Epic #183: Claude-Flow Inspired Enhancements
- Issue #170: Lifecycle Hooks
- Issue #174: Session Checkpointing
- [claude-flow hooks architecture](https://github.com/ruvnet/claude-flow)
- `.agents/analysis/claude-flow-architecture-analysis.md`

---

*Template Version: 1.0*
*Origin: Epic #183 closing comment (2025-12-20)*
