# Skill Integration Plan

**Purpose**: Document HIGH confidence patterns from observation files that need integration into skill documentation to prevent repeated errors.

**Created**: 2026-01-18
**Status**: Planning phase

## Priority Classification

### P0 (Critical - Prevents Errors)

Patterns that, if not documented in skills, cause actual failures:

#### 1. github skill - GraphQL Thread Resolution
**Pattern**: Thread resolution requires explicit GraphQL mutation (pr-review-observations.md HIGH)
**Current State**: SKILL.md line 73 shows `Resolve-PRReviewThread.ps1` but doesn't emphasize that replies DON'T auto-resolve
**Action**: Add anti-pattern section warning about reply != resolution
**Impact**: Prevents "why aren't threads resolving?" confusion

#### 2. codeql-scan skill - Error Suppression Anti-Pattern  
**Pattern**: Never redirect stderr to Write-Verbose BEFORE checking $LASTEXITCODE (error-handling-observations.md HIGH)
**Current State**: Unknown (need to check script implementation)
**Action**: Add to script comments and skill anti-patterns section
**Impact**: Prevents silent failures in CodeQL execution

#### 3. session-log-fixer skill - Completion Verification
**Pattern**: Background work requires completion verification, not just format validation (validation-observations.md HIGH)
**Current State**: Unknown
**Action**: Add verification checklist to skill documentation
**Impact**: Prevents incomplete fixes that pass format but miss requirements

### P1 (Important - Improves Quality)

Patterns that improve workflow but don't cause failures:

#### 1. pr-comment-responder skill - Batch Response Pattern
**Pattern**: Single comprehensive commit for all comments cleaner than N individual commits (pr-review-observations.md HIGH)
**Current State**: Unknown
**Action**: Add workflow recommendation
**Impact**: Cleaner git history

#### 2. github skill - Bot False Positives
**Pattern**: Bot comments can reference stale commits - verify current branch state (pr-review-observations.md HIGH)
**Current State**: Not documented
**Action**: Add verification step to review workflow
**Impact**: Prevents unnecessary changes based on stale bot feedback

#### 3. All PowerShell skills - Array Handling Patterns
**Pattern**: Multiple HIGH learnings about @() wrapping, .ToLowerInvariant(), null filtering (powershell-observations.md)
**Current State**: Not consistently documented
**Action**: Create PowerShell best practices reference document
**Impact**: Prevents type errors and case-sensitivity bugs

### P2 (Nice to Have - Workflow Optimization)

Patterns that optimize but are not error-preventing:

- Memory-first before multi-step reasoning (pr-review)
- Parallel review agents pattern (pr-review)
- 4-phase integration planning (architecture)

## Implementation Strategy

### Phase 1: P0 Critical Patterns (COMPLETED 2026-01-18)
1. ✅ Update github skill with GraphQL thread resolution warning
   - Added to Anti-Patterns table: "Replying to thread expecting auto-resolve | Replies DON'T auto-resolve threads | Use `Resolve-PRReviewThread.ps1` after reply"
2. ✅ Audit codeql-scan for error suppression pattern
   - Added new anti-pattern section: "Don't: Suppress Errors Before Checking Exit Code" with correct/incorrect examples
3. ✅ Add completion verification to session-log-fixer
   - Already covered in existing Verification Checklist: "Job Summary shows COMPLIANT verdict"
   - Pattern implicitly enforced through Job Summary validation workflow

### Phase 2: P1 Important Patterns (Next Session)
1. Create central PowerShell best practices doc
2. Update pr-comment-responder with batch pattern
3. Add bot verification guidance to github skill

### Phase 3: P2 Optimizations (Future)
1. Extract workflow patterns to dedicated guides
2. Create skill development checklist

## Cross-Reference

- Source: All *-observations.md files in `.serena/memories/`
- Target: Skill SKILL.md files in `.claude/skills/*/`
- Validation: Update skill tests to enforce new patterns where applicable

## Next Steps

1. Execute Phase 1 (P0) integrations
2. Create PR with skill updates
3. Add skill pattern enforcement to quality gates
4. Use /reflect going forward to capture skill-specific learnings incrementally
