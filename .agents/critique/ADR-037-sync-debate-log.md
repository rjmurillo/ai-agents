# ADR-037 Synchronization Strategy: Debate Log

**Date**: 2026-01-03
**Round**: 1
**Status**: NEEDS-REVISION
**Consensus**: 4 NEEDS-REVISION, 2 ACCEPT

---

## Summary

The synchronization strategy section (lines 286-437) in ADR-037 was reviewed by 6 specialized agents. The design is directionally correct but has critical implementation gaps.

**Final Verdict**: NEEDS-REVISION

---

## Agent Reviews

### Architect

**Rating**: NEEDS-REVISION

**P0 Issues**:
1. **Schema mapping undefined**: Serena memory format not mapped to Forgetful schema (title, content, context, keywords, tags, importance, project_ids)
2. **Pre-commit should be post-commit**: Hook runs on staged changes, not committed state
3. **No recursion guard**: Git hook may trigger git commands causing infinite loop

**P1 Issues**:
- Missing error handling policy
- Soft delete audit trail gap

**Recommendation**: Add schema mapping table, change to post-commit hook, add environment variable recursion guard.

---

### Critic

**Rating**: NEEDS-REVISION

**P0 Issues**:
1. **Hook installation mechanism undefined**: `.git/hooks/` is untracked, developers won't have hook
2. **Helper function locations unspecified**: Get-ContentHash, Parse-MemoryFrontmatter locations unclear
3. **YAML parsing via regex is fragile**: Fails for multiline values, nested structures
4. **Query-by-title collision risk**: Semantic search may return wrong memory

**P1 Issues**:
- Performance targets unvalidated
- Orphan cleanup policy undefined
- Batch processing details missing
- Integration tests underspecified

**Recommendation**: Add Install-GitHooks.ps1, specify module locations, adopt powershell-yaml, add source_file metadata.

**Output**: `.agents/critique/ADR-037-sync-strategy-critique.md`

---

### Independent-Thinker

**Rating**: NEEDS-REVISION

**Challenged Assumptions**:
1. **"Git hook is non-blocking"**: No circuit breaker for persistent slowness, cumulative latency grows unbounded
2. **"Soft delete preserves audit trail"**: Creates unbounded garbage, no cleanup strategy, pollutes semantic graph
3. **"Unidirectional sync is sufficient"**: Discards Forgetful enrichments (usage patterns, semantic clusters)

**Alternative Approaches Suggested**:
- Event-driven sync (systemd/launchd) to eliminate commit latency
- Hard delete with tombstone table for audit trail
- Hybrid sync with metadata-only reverse sync (Forgetful annotations → Serena frontmatter)
- Lazy sync on read (sync when memory first accessed after Serena change)

**Recommendation**: Add batching implementation, define orphan cleanup policy, add sync health dashboard.

---

### Security

**Rating**: ACCEPT

**Risk Score**: 3/10 (Low)

**Assessment**:
1. Git hook attack surface: [PASS] - No code execution, content as data only
2. SHA-256 usage: [PASS] - Cryptographically secure
3. Forgetful HTTP endpoint: [PASS] - Localhost-only valid
4. Soft delete persistence: [PASS] - Appropriate for non-PII
5. Sync drift exploitation: [PASS] - Serena-first prevents exploitation

**Low-Priority Recommendations**:
- Add sync event logging (1 hour)
- Add CI drift detection (1 hour)
- Document data retention policy (30 min)

**Output**: `.agents/security/ADR-037-synchronization-security-review.md`

---

### Analyst

**Rating**: NEEDS-REVISION

**Evidence Gathered**:
- Forgetful `mark_memory_obsolete` API exists (verified)
- SHA-256 hashing: 0.03ms per memory (not a bottleneck)
- Parallel processing: 12,000x slower than sequential (measured)
- 473 Serena memories currently exist
- No pre-commit git hook installed (greenfield)

**Evidence Gaps**:
- Forgetful API latency (create, update, query) - CRITICAL
- Network overhead for localhost:8020
- Git hook execution baseline
- Batch sync end-to-end time

**Feasibility Assessment**:
- Technical: HIGH (all APIs exist)
- Performance: MEDIUM (targets reasonable but unvalidated)
- Timeline: MEDIUM (3 weeks aggressive, needs buffer)

**Recommendation**: Measure Forgetful API latency, add 1-week timeline buffer, mark targets as "to be validated in Milestone 1".

**Output**: `.agents/analysis/130-adr037-sync-evidence-review.md`

---

### High-Level-Advisor

**Rating**: ACCEPT (with priority adjustment)

**Strategic Assessment**:
1. Does this solve the right problem? Yes, but scope is larger than Phase 2B warrants
2. Is scope appropriate? Yes for unidirectional; bidirectional deferral correct
3. Phase 2B alignment? Partial - sync is infrastructure, not performance
4. Cost-benefit? 3:1 (costs outweigh realized benefits until Forgetful adoption increases)
5. Should this block Phase 2B? No, run in parallel

**Priority Recommendation**:
- Current: P1
- Recommended: P2

**Critical Finding**: Issue #743 (health check bug) must be fixed first. Sync depends on Test-ForgetfulAvailable which may have same 406 error.

**Recommendation**: Proceed with design, defer implementation to P2, fix #743 first, validate Forgetful adoption before investing 3 weeks.

---

## Consolidated Findings

### P0 Issues (Must Fix Before Accept)

| ID | Issue | Owner |
|----|-------|-------|
| P0-1 | Serena→Forgetful schema mapping undefined | Planner |
| P0-2 | Pre-commit should be post-commit hook | Planner |
| P0-3 | No recursion guard for git hook | Planner |
| P0-4 | Hook installation mechanism undefined | Planner |
| P0-5 | Helper function locations unspecified | Planner |
| P0-6 | YAML parsing via regex is fragile | Planner |
| P0-7 | Query-by-title collision risk | Planner |
| P0-8 | Performance targets lack baseline | Analyst |

### P1 Issues (Should Fix)

| ID | Issue | Owner |
|----|-------|-------|
| P1-1 | Missing error handling policy | Planner |
| P1-2 | Soft delete audit trail gap | Planner |
| P1-3 | Orphan cleanup policy undefined | Planner |
| P1-4 | Batch processing not implemented | Planner |
| P1-5 | Integration tests underspecified | Planner |
| P1-6 | Timeline needs 1-week buffer | Planner |
| P1-7 | Fix Issue #743 before sync | Implementer |

### P2 Issues (Nice to Have)

- Add sync event logging
- Add CI drift detection
- Document data retention policy
- Consider lazy sync on read
- Consider event-driven sync

---

## Consensus Vote

| Agent | Vote | Notes |
|-------|------|-------|
| Architect | NEEDS-REVISION | 3 P0 issues |
| Critic | NEEDS-REVISION | 4 P0 issues |
| Independent-Thinker | NEEDS-REVISION | Assumptions challenged |
| Security | ACCEPT | No security blockers |
| Analyst | NEEDS-REVISION | Evidence gaps |
| High-Level-Advisor | ACCEPT | Strategic P2 priority |

**Result**: 4 NEEDS-REVISION, 2 ACCEPT = **NEEDS-REVISION**

---

## Next Steps

1. **Route to planner** for ADR-037 revision addressing P0 issues
2. **Fix Issue #743** (Test-MemoryHealth.ps1 406 error)
3. **Measure Forgetful API latency** before finalizing performance targets
4. **Re-run adr-review** after revisions complete
5. **Defer implementation** to P2 priority

---

## Revision Checklist

Before next review round, ADR-037 sync section must have:

- [ ] Schema mapping table (Serena fields → Forgetful parameters)
- [ ] Changed "pre-commit" to "post-commit" throughout
- [ ] Recursion guard specification (environment variable pattern)
- [ ] Hook installation procedure (Install-GitHooks.ps1)
- [ ] Helper function module locations specified
- [ ] YAML parsing approach justified or replaced
- [ ] Query collision mitigation (source_file metadata)
- [ ] Performance targets marked "to be validated in Milestone 1"
- [ ] Error handling policy documented
- [ ] Orphan cleanup policy defined
- [ ] Batch processing implementation clarified
- [ ] Timeline extended to 4 weeks

---

**Debate Log Created**: 2026-01-03
**Related**: Issue #747, PR #746, ADR-037
