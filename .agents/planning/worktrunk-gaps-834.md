# Worktrunk Documentation Gaps - Issue #834

**Date**: 2026-01-08
**Status**: Ready for Implementation
**Related**: Issue #834, PR #835

## Executive Summary

Issue #834 acceptance criteria are **COMPLETE** (5/5). However, the PRD defines additional documentation requirements with **2 gaps** remaining.

| Requirement | Status | Gap |
|-------------|--------|-----|
| .worktreeinclude file created | ✓ COMPLETE | None |
| Post-create hook with copy-ignored | ✓ COMPLETE | None |
| Pre-merge hooks for validation | ✓ COMPLETE | None |
| Documentation updated in AGENTS.md | ✓ COMPLETE | None |
| Setup guide includes Worktrunk | ✓ COMPLETE | None (AGENTS.md lines 216-267) |
| **PRD FR-4.2**: docs/installation.md | ✗ MISSING | No Worktrunk section |
| **PRD FR-4.3**: CLAUDE.md integration notes | ✗ MISSING | No Worktrunk mention |

## Gap Analysis

### Gap 1: docs/installation.md Missing Worktrunk Setup (PRD FR-4.2)

**Current State:**
- docs/installation.md exists with AI agents installation guide
- No Worktrunk section or mention
- File is 299 lines covering installation, paths, troubleshooting

**Required:**
- Add Worktrunk setup section after "Post-Installation" (around line 212)
- Include installation commands (Homebrew, Cargo)
- Document shell integration requirement
- Reference Claude Code plugin
- Link to AGENTS.md for detailed workflow

**Effort**: S (Small) - 15 minutes
**Priority**: P2 (Medium)
**Rationale**: Issue acceptance criteria already met via AGENTS.md. This is documentation completeness.

### Gap 2: CLAUDE.md Missing Worktrunk Integration Notes (PRD FR-4.3)

**Current State:**
- CLAUDE.md is intentionally minimal (following Anthropic guidance to keep under 100 lines)
- Current content: 66 lines
- Focus: References to AGENTS.md, session protocol quick reference

**Required:**
- Add brief Worktrunk note to "Key Documents" or "Default Behavior" section
- Keep addition under 5 lines to maintain minimalism philosophy
- Reference AGENTS.md Worktrunk section for full details

**Effort**: XS (Extra Small) - 5 minutes
**Priority**: P3 (Low)
**Rationale**: CLAUDE.md is intentionally minimal. Worktrunk workflow is comprehensive in AGENTS.md. Brief mention sufficient.

## Implementation Plan

### Phase 1: docs/installation.md Enhancement (15 min)

**Location**: After line 212 (Post-Installation section)

**Content Structure**:

```markdown
### Worktrunk Setup (Optional)

For parallel agent workflows using git worktrees, install Worktrunk:

**Homebrew (macOS & Linux):**

```bash
brew install max-sixty/worktrunk/wt && wt config shell install
```

**Cargo:**

```bash
cargo install worktrunk && wt config shell install
```

**Shell integration** is required for `wt switch` command.

**Claude Code Plugin:**

```bash
claude plugin marketplace add max-sixty/worktrunk
claude plugin install worktrunk@worktrunk
```

The plugin provides visual status indicators in `wt list` output.

**Configuration:**

The repository includes `.config/wt.toml` with lifecycle hooks that:
- Configure git hooks automatically on worktree creation
- Copy dependencies (node_modules, .cache) from main worktree
- Run markdown linting before merge

**See**: [Worktrunk Documentation](https://worktrunk.dev/) and `.config/wt.toml` for complete workflow configuration.
```

**File Changes**:
- docs/installation.md: Insert section after line 212

### Phase 2: CLAUDE.md Brief Mention (5 min)

**Location**: After line 15 (Key Documents section)

**Content**:

```markdown
6. `.config/wt.toml` - Worktrunk configuration (see AGENTS.md for setup)
```

**Alternative Location**: Could add to "Default Behavior" as optional workflow note.

**File Changes**:
- CLAUDE.md: Add line to Key Documents section

## Acceptance Criteria

**Gap 1 (docs/installation.md):**
- [ ] Worktrunk section exists after Post-Installation
- [ ] Installation commands for Homebrew and Cargo included
- [ ] Shell integration requirement documented
- [ ] Claude Code plugin installation documented
- [ ] References AGENTS.md for full workflow

**Gap 2 (CLAUDE.md):**
- [ ] Worktrunk configuration file mentioned in Key Documents or Default Behavior
- [ ] Reference to AGENTS.md for full details
- [ ] Addition keeps CLAUDE.md under 100 lines

## Quality Gates

- [ ] Markdown linting passes (`npx markdownlint-cli2 --fix "**/*.md"`)
- [ ] No broken internal links
- [ ] Consistent terminology (use "Worktrunk" not "worktrunk" or "wt")
- [ ] Cross-references verified (CLAUDE.md → AGENTS.md → wt.toml)

## Verification Steps

1. Read docs/installation.md and confirm Worktrunk section exists
2. Read CLAUDE.md and confirm brief mention exists
3. Test internal links navigate correctly
4. Verify markdown linting passes
5. Check CLAUDE.md line count remains under 100

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| CLAUDE.md bloat exceeds 100 lines | Low | Medium | Keep addition to 1 line, prioritize minimalism |
| Documentation drift from code | Low | Low | Content references existing wt.toml, no duplication |
| Inconsistent workflow description | Low | Medium | Use AGENTS.md as canonical source, docs/installation.md refers to it |

## Out of Scope

- Modifying wt.toml configuration (already complete)
- Adding Worktrunk to README.md (not in PRD)
- Creating video tutorials (not in PRD)
- Documenting advanced Worktrunk features beyond what's configured

## Decision Log

**Decision 1**: Treat issue #834 acceptance criteria as satisfied
- **Rationale**: "Setup guide includes Worktrunk" is satisfied by AGENTS.md comprehensive section
- **Impact**: These gaps are enhancements beyond acceptance criteria

**Decision 2**: Implement PRD gaps for documentation completeness
- **Rationale**: PRD explicitly calls for docs/installation.md and CLAUDE.md updates
- **Impact**: More discoverable Worktrunk setup for users arriving via installation guide

**Decision 3**: Keep CLAUDE.md addition minimal (1 line)
- **Rationale**: File philosophy is <100 lines following Anthropic guidance
- **Impact**: Brief pointer only, full details in AGENTS.md

## References

- Issue #834: https://github.com/rjmurillo/ai-agents/issues/834
- PRD Comment: https://github.com/rjmurillo/ai-agents/issues/834#issuecomment-3725773016
- Current implementation: `.config/wt.toml`, `.worktreeinclude`, AGENTS.md lines 216-267
- Worktrunk documentation: https://worktrunk.dev/
