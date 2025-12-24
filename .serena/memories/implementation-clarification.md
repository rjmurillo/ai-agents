# Skill-Implementation-004: Clarification Timing Optimization

**Statement**: Ask scope, authentication, and use case questions before planning starts, not during implementation.

**Context**: Requirements gathering for multi-file or infrastructure changes.

**Trigger**: Receiving implementation request with potential ambiguity.

**Evidence**: Session 03 (2025-12-18): All clarifications asked at T+5 (before planning). Result: zero mid-implementation pivots, zero wasted effort.

**Atomicity**: 97%

**Impact**: 9/10 - Prevents mid-stream pivots

## Questions to Ask Upfront

1. **Scope**: What's the boundary? This repo only? Which files?
2. **Authentication**: What credentials? Which secrets?
3. **Use Cases**: Which specific scenarios to support?
4. **Dependencies**: What external services/tools required?

## Anti-Pattern

Asking clarifications during implementation → causes rework and wasted tokens.
