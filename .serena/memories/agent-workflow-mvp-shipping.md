# Ship MVP Over Perfect

**Statement**: Choose "working and shippable" over "perfect" when time-constrained, documenting enhancements as technical debt

**Context**: Implementation decisions under time pressure

**Evidence**: Simple validation script shipped vs. sophisticated parser with code fence detection (deferred to Phase 3)

**Atomicity**: 88%

**Impact**: 8/10

## Decision Framework

1. Does it solve the immediate problem? → Yes = ship
2. Are known limitations documented? → Must be yes
3. Is there a path to enhancement? → Document in backlog
4. Does shipping create tech debt? → Acceptable if tracked

## Anti-Patterns

- Gold-plating features that aren't required
- Delaying ship for edge cases
- Perfect being enemy of good
- Undocumented shortcuts
