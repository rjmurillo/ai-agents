# Serena Skills Index

**Purpose**: Master index of all Serena token efficiency skills
**Created**: 2025-12-20
**Source**: SERENA-BEST-PRACTICES.md

## Skills by Category

### Token Efficiency (Mandatory)

| Skill ID | Skill Name | Impact | Status |
|----------|------------|--------|--------|
| skill-serena-001 | Symbolic tools first | High (95%) | Mandatory |
| skill-serena-002 | Avoid redundant reads | High (100% waste prevention) | Mandatory |
| skill-serena-003 | Read memories first | Critical (90% caching) | Mandatory |

### Search Optimization (Recommended)

| Skill ID | Skill Name | Impact | Status |
|----------|------------|--------|--------|
| skill-serena-004 | find_symbol patterns | Medium (50%) | Recommended |
| skill-serena-005 | Restrict search scope | High (70%) | Recommended |
| skill-serena-007 | Limit tool output | Medium (30-50%) | Recommended |

### Setup & Configuration

| Skill ID | Skill Name | Impact | Status |
|----------|------------|--------|--------|
| skill-serena-006 | Pre-index projects | Medium (50% faster) | Recommended |
| skill-serena-008 | Configure global limits | High (30% reduction) | Recommended |
| skill-serena-009 | Use claude-code context | Medium (avoids conflicts) | Mandatory for CLI |

### Session Management

| Skill ID | Skill Name | Impact | Status |
|----------|------------|--------|--------|
| skill-serena-010 | Session continuation | Critical (enables continuation) | Mandatory at limit |
| skill-serena-011 | Cache worktree sharing | Medium (avoids re-index) | Recommended |

## Quick Reference

### Start of Session

1. Read `skill-serena-003-read-memories-first`
2. Load relevant memories for caching benefit

### Code Exploration

1. Read `skill-serena-001-symbolic-tools-first`
2. Read `skill-serena-002-avoid-redundant-reads`
3. Read `skill-serena-004-find-symbol-patterns`
4. Read `skill-serena-005-restrict-search-scope`

### Large Codebases

1. Read `skill-serena-007-limit-tool-output`
2. Read `skill-serena-008-configure-global-limits`

### Initial Setup

1. Read `skill-serena-006-pre-index-projects`
2. Read `skill-serena-008-configure-global-limits`
3. Read `skill-serena-009-use-claude-code-context`

### Session Limits

1. Read `skill-serena-010-session-continuation`

### Worktree Workflows

1. Read `skill-serena-011-cache-worktree-sharing`

## Combined Impact

When all mandatory + recommended skills applied:
- Token reduction: 80-95% on code exploration tasks
- Speed improvement: 50% faster symbol lookups (pre-indexed)
- Cost reduction: 90% via prompt caching (memory-first)

## Evidence Base

All skills extracted from:
- `.agents/governance/SERENA-BEST-PRACTICES.md`
- Lines 298-405 (Token-Efficient Patterns section)
- Lines 209-227 (Configuration section)
- Official Serena documentation references

## Validation Status

All skills: 0 validations (newly extracted 2025-12-20)

Next: Apply in real sessions and track effectiveness.
