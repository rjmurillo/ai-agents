# Skill-Session-Init-003: Branch Declaration

**Statement**: Require branch declaration in session log header

**Context**: At session initialization, after creating session log file

**Evidence**: PR #669 analysis - explicit branch tracking creates accountability and prevents confusion

**Atomicity**: 82% | **Impact**: 6/10

## Pattern

**Session Log Header Template**:

```markdown
# Session YYYY-MM-DD-NN

## Branch
**Current**: feat/issue-XXX
**Created**: [YYYY-MM-DD HH:MM] (if new)
**Base**: main

## Issues in Scope
- #XXX: [Description]
```

**Verification at Each Commit**:
1. Read session log branch declaration
2. Run `git branch --show-current`
3. Confirm match before commit

## Anti-Pattern

```markdown
# WRONG: Missing branch declaration
# Session 2025-12-31-01

## Issues in Scope
- #123: Fix bug

# Problem: No explicit branch tracking
# Agent must infer or remember - prone to error
```

## Related Skills

- [git-004-branch-verification-before-commit](git-004-branch-verification-before-commit.md): Runtime verification
- [session-scope-002-multi-issue-limit](session-scope-002-multi-issue-limit.md): Scope management
- [protocol-template-enforcement](protocol-template-enforcement.md): Template compliance

## Related

- [session-109-export-analysis-findings](session-109-export-analysis-findings.md)
- [session-110-agent-upgrade](session-110-agent-upgrade.md)
- [session-111-investigation-allowlist](session-111-investigation-allowlist.md)
- [session-112-pr-712-review](session-112-pr-712-review.md)
- [session-113-pr-713-review](session-113-pr-713-review.md)
