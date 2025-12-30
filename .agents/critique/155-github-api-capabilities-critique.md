# Critique: GitHub API Capability Matrix Documentation (Issue #155)

**Document**: `docs/github-api-capabilities.md`
**Verdict**: [NEEDS_REVISION]
**Confidence**: 95%
**Review Date**: 2025-12-30

---

## Verdict Rationale

The document comprehensively addresses all 5 acceptance criteria with strong structure and clarity. However, one critical factual error regarding skill file naming prevents approval. The error must be corrected before publication, as it will mislead developers integrating with project skills.

---

## Summary

[PASS] Content coverage: All acceptance criteria met
[PASS] Markdown quality: Zero linting errors
[PASS] Structure: Well-organized 10-section layout
[PASS] Examples: Three working code samples provided
[PASS] Readability: Grade 9 level, active voice, no hedging
[FAIL] Factual accuracy: Skill file naming error on line 199

---

## Strengths

1. **Comprehensive Decision Matrix**: Lines 14-25 provide a quick-reference table that lets developers instantly see which API to use for 8 common scenarios.

2. **Three-Tier Capability Matrix**: Lines 27-58 clearly categorize all GitHub operations into GraphQL-only, both APIs, and REST-preferred groups. This prevents the common mistake of assuming every operation is available in both.

3. **Concrete Code Examples**: Three bash examples (lines 82-162) show actual `gh api` syntax:
   - Example 1 proves REST cannot resolve threads (the core use case requiring GraphQL)
   - Example 2 demonstrates REST over-fetching vs GraphQL single query efficiency
   - Example 3 covers Projects v2 (GraphQL-only)

4. **Trade-offs Section**: Lines 164-189 honestly compare both APIs with specific advantages/disadvantages. Developers understand GraphQL's steeper learning curve vs REST's simplicity.

5. **Project Integration**: Lines 191-207 link to actual project skills (`Resolve-PRReviewThread.ps1`, `Get-PRReviewThreads.ps1`, etc.), grounding theory in implementation.

6. **Related Resources**: Lines 242-246 reference GraphQL Explorer and memory nodes, supporting further research.

---

## Critical Issues

### [CRITICAL] Skill File Naming Error (Line 199)

**Location**: Line 199, REST API Skills table
**Issue**: Document lists `Add-Reaction.ps1` but actual file is `Add-CommentReaction.ps1`

**Evidence**:
```bash
$ ls /home/richard/ai-agents/.claude/skills/github/scripts/reactions/
Add-CommentReaction.ps1
```

**Impact**: Developers copying the skill reference will fail to find the file. This breaks trust in the document as a reliable reference.

**Fix Required**: Change line 199 from:
```markdown
| `Add-Reaction.ps1` | `.claude/skills/github/scripts/reactions/` | Add emoji reactions |
```

To:
```markdown
| `Add-CommentReaction.ps1` | `.claude/skills/github/scripts/reactions/` | Add emoji reactions |
```

**Rationale**: Skill names must match filesystem exactly for documentation to be actionable. This is a data entry error, not a content design issue.

---

## Acceptance Criteria Verification

| Criterion | Status | Location | Assessment |
|-----------|--------|----------|------------|
| Document which operations require GraphQL vs REST | [PASS] | Lines 29-58 | Three distinct tables clearly separate GraphQL-only, both, REST-preferred |
| Provide capability matrix | [PASS] | Lines 27-58 | 16 operations documented across GraphQL, both APIs, and REST categories |
| Include when to use each API | [PASS] | Lines 60-78 | Six REST use cases, six GraphQL use cases listed |
| Show implementation examples | [PASS] | Lines 82-162 | Three complete bash examples: thread resolution, nested queries, projects v2 |
| Document trade-offs | [PASS] | Lines 164-189 | Four trade-off categories (GraphQL advantages/disadvantages, REST advantages/disadvantages) |

---

## Questions for Clarification

None at this time. The document is clear enough to proceed once the skill name is corrected.

---

## Recommendations

1. **Correct line 199** to reference actual `Add-CommentReaction.ps1` file name
2. **Verify all six skill references** exist on filesystem (recommend spot-check):
   - `Get-PRContext.ps1` in `.claude/skills/github/scripts/pr/` - [VERIFIED ✓]
   - `Set-IssueLabels.ps1` in `.claude/skills/github/scripts/issue/` - [VERIFIED ✓]
   - `Add-CommentReaction.ps1` in `.claude/skills/github/scripts/reactions/` - [VERIFIED ✓ after fix]
   - `Resolve-PRReviewThread.ps1` in `.claude/skills/github/scripts/pr/` - [VERIFIED ✓]
   - `Get-PRReviewThreads.ps1` in `.claude/skills/github/scripts/pr/` - [VERIFIED ✓]
   - `Get-UnresolvedReviewThreads.ps1` in `.claude/skills/github/scripts/pr/` - [VERIFIED ✓]

---

## Approval Conditions

This document requires ONE change before approval:

- [ ] Line 199: Fix `Add-Reaction.ps1` → `Add-CommentReaction.ps1`

After this correction:

- All acceptance criteria met
- No critical issues remaining
- All skill references verified accurate
- Document ready for publication

---

## Style Compliance

- [PASS] No sycophancy or AI filler phrases detected
- [PASS] Active voice used throughout ("Document which", "Use REST For", "Check REST First")
- [PASS] Data-backed statements (3 examples, 16 operations, 6 use cases each)
- [PASS] No em dashes
- [PASS] No emojis
- [PASS] Text-based status indicators present in recommendations
- [PASS] Short sentences (15-20 words maintained)
- [PASS] Grade 9 reading level

---

## Cross-Domain Impact

This documentation supports multiple project goals:

1. **Developer Onboarding**: Quick reference table enables new contributors to pick correct API immediately
2. **Skill Library Integration**: Direct references to project skills (6 files) reduce friction when implementing GitHub operations
3. **Architecture Alignment**: GitHub API choice decisions align with project patterns documented in ADRs
4. **Cost Management**: Guidance on GraphQL's single-query efficiency supports rate-limit optimization

---

## Summary for Orchestrator

**Verdict**: NEEDS_REVISION
**Blocker**: 1 critical issue (skill file naming)
**Effort to Fix**: < 5 minutes (single line change)
**Recommended Next Step**: Return to implementer with specific correction required on line 199, then approve.

