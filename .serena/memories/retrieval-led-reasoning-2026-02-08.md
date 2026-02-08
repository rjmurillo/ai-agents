# Retrieval-Led Reasoning Directive Injection (2026-02-08)

**Date**: 2026-02-08
**Session**: 1192
**Type**: Implementation

## Summary

Implemented comprehensive retrieval-led reasoning directive injection strategy based on Vercel research showing 100% pass rate for passive context vs 53-79% for active skill invocation.

## Problem

Agents rely on pre-training (potentially outdated, no project context) instead of retrieving from authoritative sources (current, accurate, project-specific). This causes:
- Outdated framework knowledge
- Bypassing tested skills for inline code
- Ignoring documented patterns
- Violating project constraints

## Solution

Inject "prefer retrieval-led reasoning over pre-training" directives at 7 strategic points with inline indexes showing WHERE to retrieve from. This eliminates the decision point that causes failures.

## Implementation

### Phase 1: High-Traffic Auto-Loaded Files
1. **CRITICAL-CONTEXT.md** (line 6): Added retrieval-first directive with inline index covering ALL decision types
2. **SKILL-QUICK-REF.md** (line 8): Moved directive higher, added concrete failure mode examples (✗ vs ✓)
3. **AGENTS.md** (line 31): Added "librarians not oracles" section explaining two information sources

### Phase 2: Session Start Hooks  
4. **ADR-007 hook** (.claude/hooks/Invoke-SessionStartMemoryFirst.ps1): Enhanced with memory index quick reference table
5. **Branch warning hook** (.claude/hooks/SessionStart/Invoke-SessionInitializationEnforcer.ps1): Added skill-first reminder
6. **.claude/settings.json**: Updated hook injection logic

### Phase 3: Protocol Documents
7. **SESSION-PROTOCOL.md** (line 93): Added retrieval-first principle before memory loading protocol
8. **PROJECT-CONSTRAINTS.md** (line 13): Added "single source of truth" preamble

### Analysis Document
- Created .agents/analysis/retrieval-led-reasoning-injection-points.md with complete strategy and text recommendations

## Key Pattern: Inline Indexes

Each injection point includes an inline index showing WHERE to retrieve from:

```markdown
**Retrieval Sources Index**:
- Constraints: `.agents/governance/PROJECT-CONSTRAINTS.md`
- Session protocol: `.agents/SESSION-PROTOCOL.md`
- Memory index: Serena [memory-index](memory-index.md)
- Architecture: `.agents/architecture/ADR-*.md`
- Skills: `.claude/skills/{skill-name}/SKILL.md`
```

This eliminates the decision point by making the lookup path obvious.

## Evidence Base

**Vercel Research Results**:
- Baseline (no docs): 53% pass rate
- Active skill invocation: 53-79% pass rate  
- **Passive context (AGENTS.md): 100% pass rate**

**Key insight**: When information is present every turn without requiring a decision point, agents use it reliably.

## Team Coordination

Used TeamCreate to spawn specialized agents:
- **doc-editor**: Implemented Phase 1 & 3 (documentation files)
- **hook-engineer**: Implemented Phase 2 (session start hooks)
- **qa-validator**: Validated changes and ran PR workflow

All 9 tasks completed successfully in parallel.

## Files Modified

- CRITICAL-CONTEXT.md (+23 lines)
- SKILL-QUICK-REF.md (+27 lines, directive moved higher)
- AGENTS.md (+42 lines)
- .agents/SESSION-PROTOCOL.md (+19 lines)
- .agents/governance/PROJECT-CONSTRAINTS.md (+20 lines)
- .claude/hooks/Invoke-SessionStartMemoryFirst.ps1 (+25 lines)
- .claude/hooks/SessionStart/Invoke-SessionInitializationEnforcer.ps1 (+13 lines)
- .claude/settings.json (hook configuration)
- .agents/analysis/retrieval-led-reasoning-injection-points.md (new, 449 lines)

Total: 616 insertions across 9 files

## Success Metrics

### Leading Indicators (5 sessions):
- % sessions with memory-index read before code changes
- % GitHub operations using skills vs raw commands
- % framework questions with doc retrieval

### Lagging Indicators (20 sessions):
- Reduction in "outdated API" corrections
- Reduction in "there's a skill for that" corrections
- Reduction in constraint violations

## Next Steps

1. Monitor agent behavior for 5 sessions (qualitative)
2. Measure leading indicators  
3. Adjust directive text if needed
4. Document in retrospective after 20 sessions

## Related Memories

- usage-mandatory: Skill-first enforcement pattern
- memory-index: Keyword → memory mapping
- ADR-007: Memory-first architecture
- skills-implementation-index: Implementation patterns
- skills-agent-workflow-index: Team coordination patterns
