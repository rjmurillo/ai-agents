# Session 310: CLAUDE.md @imports Implementation

**Date**: 2026-01-04
**Branch**: feat/claude-md-token-optimization
**Issue**: #774
**Agent**: Claude Sonnet 4.5

## Objective

Implement the three phases from issue #774 to adopt Anthropic's @imports pattern for CLAUDE.md.

## Context

From Anthropic's official CLAUDE.md guidance, we identified opportunities to:
- Use @imports for automatic critical context loading
- Document /init and /clear usage
- Create hierarchical CLAUDE.md files for subdirectories

## Phase 1: Documentation (No Breaking Changes)

- [ ] Document /init usage in AGENTS.md
- [ ] Document /clear usage in AGENTS.md
- [ ] Add comment to CLAUDE.md explaining minimal approach

## Phase 2: @imports Implementation

- [x] Create CRITICAL-CONTEXT.md with blocking gates
- [x] Add @import to CLAUDE.md
- [x] Measure token impact

### Token Impact

**CRITICAL-CONTEXT.md**: 57 lines, ~400 tokens (auto-loaded each session)

**Expected Benefits**:
- Eliminates 2-4 tool calls per session for basic constraint retrieval
- Saves ~12,000 tokens when agents would otherwise read full documents
- Net positive for quick tasks (fewer tool calls > auto-load cost)

## Phase 3: Hierarchical Files

- [ ] Create .claude/skills/CLAUDE.md
- [ ] Create scripts/CLAUDE.md
- [ ] Evaluate .claude/rules/ structure

## Decisions

TBD

## Outcomes

TBD

## Next Steps

TBD
