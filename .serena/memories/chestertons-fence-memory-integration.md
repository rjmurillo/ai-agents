# Chesterton's Fence Principle - Memory Integration

**Created**: 2026-01-03
**Related**: ADR-007 (Memory-First), Issue #748, `.agents/analysis/chestertons-fence.md`

## Core Connection

Memory-first architecture implements Chesterton's Fence principle for AI agents:

> "Do not remove a fence until you know why it was put up" - G.K. Chesterton

**Translation**: Do not change code/architecture/protocol until you search memory for why it exists.

## Why This Works

**Chesterton's Fence requires**: Investigation of historical context before changes
**Memory system provides**: Historical context (Tier 1 facts, Tier 2 episodes, Tier 3 patterns)

**Result**: Memory search IS the investigation mechanism Chesterton's Fence demands.

## Concrete Applications

### Past Incidents Prevented by Memory Search

1. **ADR-037 P0-3 (Recursion Guard)**: If agent searched memory for "git hooks call git commands", would find pattern absence → investigate why before breaking it

2. **Skills-first violations**: If agent searched memory for "why skills exist", would find:
   - `usage-mandatory.md`: Testability, consistency, reuse
   - Past incidents from raw CLI usage
   - Protocol enforcement rationale

3. **Session protocol drift**: If agent searched memory for "BLOCKING gates", would find:
   - `protocol-blocking-gates.md`: <50% compliance before, 100% after
   - Evidence for why enforcement pattern works

### Investigation Protocol

When changing existing systems:

| Change Type | Memory Search |
|-------------|---------------|
| Remove ADR constraint | `Search-Memory.ps1 -Query "[constraint name]"` |
| Bypass protocol | `Search-Memory.ps1 -Query "[protocol name] why"` |
| Delete >100 lines | `Search-Memory.ps1 -Query "[component] purpose"` |
| Refactor complex code | `Search-Memory.ps1 -Query "[component] edge case"` |
| Change workflow | `Search-Memory.ps1 -Query "[workflow] rationale"` |

## Memory as Git Archaeology

**Tier 1 (Semantic)**: Why does X exist?
- ADRs document original rationale for constraints
- Serena memories contain incident reports
- Forgetful memories link related decisions

**Tier 2 (Episodic)**: What happened when we tried Y?
- Session logs show past attempts
- Failure episodes document edge cases encountered
- Success episodes show what worked

**Tier 3 (Causal)**: What patterns led to Z outcome?
- Causal graph shows decision → outcome paths
- Success patterns show what to repeat
- Failure patterns show what to avoid

## Enforcement (BLOCKING Gate)

Added to memory skill: Memory-first gate for changes to existing systems.

**Before changing existing code/architecture/protocol, you MUST**:

1. Run `Search-Memory.ps1 -Query "[topic]"`
2. Review results for historical context
3. If insufficient, escalate to Tier 2/3
4. Document findings in decision rationale
5. Only then proceed with change

**Why BLOCKING**: Same pattern as session protocol gates - guidance achieves <50% compliance, BLOCKING gates achieve 100%.

**Verification**: Session logs must show memory search BEFORE decisions.

## Implementation Status

- [x] Deep analysis written: `.agents/analysis/chestertons-fence.md`
- [x] GitHub issue created: #748 (agent integration plan)
- [x] Memory skill updated: Added "Memory-First as Chesterton's Fence" section
- [ ] Agent prompts updated: Add investigation requirement (per Issue #748 plan)
- [ ] ADR template updated: Add "Prior Art Investigation" section
- [ ] Pre-commit hook: Detect deletions >100 lines, require investigation

## Agent Integration (from Issue #748)

**analyst**: Primary investigator, uses memory search for "why does this exist?"
**architect**: Requires "Prior Art Investigation" section in ADRs proposing changes
**critic**: Validates plans include memory search before changes
**implementer**: Refuses deletion/refactoring without investigation evidence
**planner**: Includes Phase 0 investigation in plans for existing system changes

## Key Principle

**Memory IS the investigation tool**. It contains the "why" that Chesterton's Fence requires you to discover.

When you search memory and find rationale, you're doing Chesterton's investigation. When you skip memory search, you're removing fences without knowing why they exist.

## References

- Full analysis: `.agents/analysis/chestertons-fence.md` (13 sections, decision framework, examples)
- Issue #748: Implementation plan for agent integration
- ADR-007: Memory-first architecture (original mandate)
- Memory skill: `.claude/skills/memory/SKILL.md` (updated with Chesterton's Fence section)
- `protocol-blocking-gates.md`: Enforcement pattern achieving 100% compliance
