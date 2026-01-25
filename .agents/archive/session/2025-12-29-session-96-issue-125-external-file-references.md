# Session 96: Issue #125 - Remove External File References from Agent Templates

**Date**: 2025-12-29
**Issue**: #125 - fix(security): Remove external file references from agent templates
**Branch**: fix/125-external-file-references
**PR**: #528
**Type**: Security/Bug Fix

## Session Protocol Compliance

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Serena initialized | [PASS] | `mcp__serena__initial_instructions` output |
| HANDOFF.md read | [PASS] | Read-only reference reviewed |
| Session log created | [PASS] | This file |
| Skills listed | [PASS] | `.claude/skills/github/scripts/` listed |
| `skill-usage-mandatory` read | [PASS] | Memory content reviewed |
| PROJECT-CONSTRAINTS read | [PASS] | Content reviewed |

## Problem Statement

The security agent template (`templates/agents/security.shared.md`) contains references to external files that may not exist on end-user machines:

- `../.agents/security/static-analysis-checklist.md`
- `../.agents/security/secret-detection-patterns.md`
- `../.agents/security/code-quality-security.md`
- `../.agents/security/architecture-security-template.md`
- `../.agents/security/security-best-practices.md`

This violates the agent self-containment principle documented in memory `deployment-001-agent-self-containment`.

## Solution

Remove external file references from all security agent files. The inline capability descriptions already provide sufficient guidance without external dependencies.

## Work Log

### Phase 1: Analysis

- [x] Examined `templates/agents/security.shared.md` - found 5 external file references
- [x] Checked if referenced files exist in source repository - they do exist in `.agents/security/`
- [x] Determined solution: Remove references since inline descriptions are sufficient

### Phase 2: Implementation

- [x] Removed 5 external references from template and all 6 deployment targets:
  - `templates/agents/security.shared.md`
  - `src/claude/security.md`
  - `src/copilot-cli/security.agent.md`
  - `src/vs-code-agents/security.agent.md`
  - `.claude/agents/security.md`
  - `.github/agents/security.agent.md`
- [x] Verified no remaining external file references with grep

### Phase 3: Review

- [x] Security review: Not required (removing broken references, no security-sensitive logic)
- [x] Critic review: Simple bug fix, no plan needed
- [x] QA verification: Validated no remaining patterns, markdown lint clean

## Decisions

1. **Remove rather than embed**: The inline bullet points in each capability section already provide sufficient guidance. Embedding the full external files would bloat the agent prompt unnecessarily.

2. **Consistent fix across all targets**: Applied the fix to all 6 deployment targets to ensure consistency.

## Outcome

[COMPLETE] - PR #528 opened

- 6 files changed, 30 lines deleted (5 references removed from each file)
- All agent templates now self-contained
- Issue #125 will be closed when PR merges

## Session End Checklist

- [x] All changes committed (871cffa)
- [x] Session log complete
- [x] Serena memory updated (using existing `deployment-001-agent-self-containment`)
- [x] Markdown lint clean
- [x] PR opened (#528)
