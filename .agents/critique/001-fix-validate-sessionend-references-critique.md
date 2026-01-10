# Plan Critique: Fix Validate-SessionEnd.ps1 Documentation References

## Verdict

**NEEDS REVISION**

## Summary

The plan correctly identifies 4 changes in AGENTS.md (already in working tree). The plan scope is too narrow. The plan does not account for 186 additional incorrect references across the codebase. Most critically, the plan treats historical documentation as errors when they are accurate historical records.

## Critical Issues (Must Fix)

### 1. Historical Context Ignored

**Issue**: Plan treats all `Validate-SessionEnd.ps1` references as errors.

**Evidence**:
- Git commit a4c58192 renamed `Validate-SessionEnd.ps1` to `Validate-SessionProtocol.ps1` on 2025-12-23
- Commit 4a00fca3 shows `Validate-SessionEnd.ps1` was a real, functional script
- 19 session logs in `.agents/sessions/` correctly reference the script name that existed when sessions occurred
- 23 memory files in `.serena/memories/` correctly document historical patterns

**Problem**: Changing historical records introduces anachronism. Session logs MUST reflect the actual commands run during that session.

**Required Action**: Define scope boundaries:
- **DO UPDATE**: Current documentation (AGENTS.md, CLAUDE.md, CRITICAL-CONTEXT.md, SESSION-PROTOCOL.md, ADRs)
- **DO NOT UPDATE**: Historical records (session logs before 2025-12-23, memories documenting historical sessions)
- **EVALUATE**: Skills, analysis docs, architecture docs based on context

### 2. Incomplete Scope Analysis

**Issue**: Plan states "4 references in AGENTS.md" but grep shows 190 total references.

**Evidence**:
```bash
grep -r "Validate-SessionEnd" --include="*.md" --include="*.ps1" | wc -l
# Output: 190
```

**Breakdown by directory**:
- `.claude/skills/`: 2 files (CURRENT documentation - must fix)
- `.serena/memories/`: 23 files (HISTORICAL records - preserve)
- `.agents/sessions/`: 19 files (HISTORICAL logs - preserve)
- `.agents/analysis/`: 15+ files (MIXED - evaluate by date)
- `.agents/planning/`: 10+ files (HISTORICAL - preserve)
- `.agents/architecture/`: 3 files (CURRENT - must fix):
  - ADR-007-memory-first-architecture.md
  - ADR-011-session-state-mcp.md
  - ADR-019-script-organization.md
- `.agents/security/`: Files (MIXED - evaluate by date)

**Required Action**: Expand scope to include current documentation while explicitly excluding historical records.

### 3. Missing File Type Prioritization

**Issue**: Plan does not establish priority order for corrections.

**Required Priority**:
1. **P0 (BLOCKING)**: Architecture Decision Records (ADRs) - canonical source of truth
2. **P1 (CRITICAL)**: Skills documentation - used in active workflows
3. **P2 (IMPORTANT)**: Current process documentation (CLAUDE.md, CRITICAL-CONTEXT.md)
4. **P3 (DO NOT MODIFY)**: Historical session logs, historical memories, completed planning docs

**Required Action**: Add explicit priority tiers to plan.

### 4. No Verification Strategy

**Issue**: Plan does not specify how to verify all current references are updated.

**Required Action**: Add verification steps:
```bash
# After changes, verify no current docs have old references
grep -r "Validate-SessionEnd" \
  --include="*.md" \
  --exclude-dir=".agents/sessions" \
  --exclude-dir=".serena/memories" \
  /home/richard/ai-agents/.agents/architecture/ \
  /home/richard/ai-agents/.claude/skills/ \
  /home/richard/ai-agents/AGENTS.md \
  /home/richard/ai-agents/CLAUDE.md \
  /home/richard/ai-agents/CRITICAL-CONTEXT.md
# Expected: 0 results
```

## Important Issues (Should Fix)

### 5. Missing Risk Assessment

**Issue**: Plan does not assess risks of modifying historical documentation.

**Risks**:
- **Traceability loss**: Future debugging cannot match session logs to actual commands run
- **Audit trail corruption**: Session logs document what actually happened
- **Memory invalidation**: Updating memories about past sessions creates false records

**Recommendation**: Document preservation strategy for historical records.

### 6. No Rollback Plan

**Issue**: If mass updates introduce errors, no documented rollback strategy exists.

**Recommendation**: Add rollback section:
- Use feature branch (already exists: `docs/fix-validate-sessionend-script-refs`)
- Commit current docs separately from any other changes
- Test `Validate-SessionProtocol.ps1` still works after updates

## Questions for Planner

1. What is the cutoff date for historical vs current documentation? (Suggest: 2025-12-23 based on commit a4c58192)
2. Should analysis docs be updated if they reference historical sessions?
3. Are there any downstream systems or CI workflows that depend on these reference patterns?
4. Should we add a migration note to SESSION-PROTOCOL.md documenting the rename?

## Verified Facts

| Fact | Value | Source |
|------|-------|--------|
| Rename commit | a4c58192 | git log --all --oneline -S "Validate-SessionEnd.ps1" |
| Rename date | 2025-12-23 | git show a4c58192 --format=%ci |
| Total incorrect refs | 190 | grep -r "Validate-SessionEnd" --include="*.md" --include="*.ps1" |
| AGENTS.md changes | 4 lines (already staged) | git diff HEAD AGENTS.md |
| Session log refs | 19 files | grep -r "Validate-SessionEnd" .agents/sessions/ |
| Memory refs | 23 files | grep -r "Validate-SessionEnd" .serena/memories/ |
| ADR refs | 3 files | grep -r "Validate-SessionEnd" .agents/architecture/ |
| Skill refs | 2 files | grep -r "Validate-SessionEnd" .claude/skills/ |

## Recommendations

### Revised Scope

**Phase 1: Current Documentation (P0-P1)**
1. Architecture Decision Records (3 files):
   - `.agents/architecture/ADR-007-memory-first-architecture.md`
   - `.agents/architecture/ADR-011-session-state-mcp.md`
   - `.agents/architecture/ADR-019-script-organization.md`
2. Skills documentation (2 files):
   - `.claude/skills/merge-resolver/SKILL.md`
3. AGENTS.md (already in working tree - verify only)
4. Verify CLAUDE.md, CRITICAL-CONTEXT.md, SESSION-PROTOCOL.md (already correct)

**Phase 2: Historical Documentation (DO NOT MODIFY)**
- Session logs before 2025-12-23
- Memory files documenting historical sessions
- Completed planning documents

**Phase 3: Analysis Documentation (Evaluate)**
- Review each analysis doc
- Update only if it represents current process documentation
- Preserve if it documents historical analysis

### Implementation Steps

1. **Verify current state**:
   ```bash
   git status
   git diff HEAD AGENTS.md  # Confirm 4 changes staged
   ```

2. **Update P0 files** (ADRs):
   - Use Edit tool for exact replacements
   - Verify no other changes introduced

3. **Update P1 files** (Skills):
   - Update `.claude/skills/merge-resolver/SKILL.md`

4. **Verification**:
   ```bash
   # Verify no current docs have old reference
   grep -r "Validate-SessionEnd" \
     --include="*.md" \
     --exclude-dir=".agents/sessions" \
     --exclude-dir=".serena/memories" \
     --exclude-dir=".agents/planning" \
     /home/richard/ai-agents/.agents/architecture/ \
     /home/richard/ai-agents/.claude/skills/ \
     /home/richard/ai-agents/AGENTS.md
   # Expected: 0 results
   ```

5. **Documentation**:
   - Add migration note to SESSION-PROTOCOL.md or ADR documenting the rename
   - Update HANDOFF.md if it references validation scripts

## Approval Conditions

Plan will be APPROVED when:

1. **Scope boundaries defined**: Clear policy on historical vs current documentation
2. **Priority tiers added**: P0 (ADRs), P1 (Skills), P2 (Current docs), P3 (Historical - DO NOT MODIFY)
3. **Verification strategy added**: Post-change grep to confirm all current docs updated
4. **Historical preservation policy**: Explicit statement that session logs and historical memories MUST NOT be modified
5. **Rollback plan documented**: Feature branch strategy, separate commits

## Impact on Session Protocol

This is a **documentation-only change**. No functional impact on:
- Session validation logic
- CI/CD workflows
- Script execution

The script rename (a4c58192) already occurred. This plan only updates documentation to match reality.

## Estimated Effort

- **Current scope (AGENTS.md only)**: 5 minutes (already done)
- **Revised scope (ADRs + Skills)**: 15 minutes
- **Verification**: 5 minutes
- **Total**: 25 minutes

## Next Steps

1. Planner revises plan with:
   - Historical preservation policy
   - Expanded scope (5 additional files)
   - Verification strategy
   - Rollback plan
2. Critic re-reviews revised plan
3. If approved, implementer executes with verification

---

**Critique saved**: 2026-01-04
**Reviewer**: critic agent
**Recommendation**: Return to planner for revision
