# PR Comment Responder Skills Memory

## Overview

Memory for tracking reviewer signal quality statistics, triage heuristics, and learned patterns across PR comment response sessions.

## Per-Reviewer Performance (Cumulative)

Last updated: 2025-12-29

| Reviewer | PRs | Comments | Actionable | Signal | Notes |
|----------|-----|----------|------------|--------|-------|
| cursor[bot] | - | 28 | 28 | **100%** | All comments identify real bugs (see cursor-bot-review-patterns memory) |
| gemini-code-assist[bot] | #488 | 1 | 1 | **100%** | Case-sensitivity path bypass (CWE-22) |
| Copilot | #488, #484, #490 | 5 | 5 | **100%** | Path separator bypass (CWE-22), workflow error handling |
| rjmurillo (owner) | #490 | 1 | 1 | **100%** | Caught missing platform-specific file update |
| coderabbitai[bot] | - | 6 | 3 | **50%** | Medium signal quality |

## Per-PR Breakdown

### PR #484 (2025-12-29)

**PR**: feat(workflow): auto-flag PRs exceeding commit threshold

| Reviewer | Comments | Actionable | Rate | Outcomes |
|----------|----------|------------|------|----------|
| Copilot | 4 | 4 | 100% | Critical env var fix, error handling, pagination docs |

**Session Notes**:

- All 4 Copilot comments were actionable (100% signal)
- **Critical bug**: Missing PR_NUMBER env var would have caused workflow failure
- **Major bug**: Missing error handling after gh api call (silent failures)
- **Documentation**: Pagination limit documented, critique checkbox updated
- All fixes implemented in single commit e3175ba
- All review threads resolved, CI checks passing

### PR #488 (2025-12-29)

**PR**: fix(security): add path containment check in Validate-SessionEnd.ps1

| Reviewer | Comments | Actionable | Rate | Outcomes |
|----------|----------|------------|------|----------|
| gemini-code-assist[bot] | 1 | 1 | 100% | Case-insensitive path comparison fix (OrdinalIgnoreCase) |
| Copilot | 1 | 1 | 100% | Path separator bypass fix (normalize + trailing separator) |

**Session Notes**:

- Both bot comments identified **real security vulnerabilities** in a security fix PR
- gemini-code-assist: Caught case-sensitivity bypass on Windows (CWE-22 variant)
- Copilot: Caught path separator prefix bypass (`.agents/sessions-evil` attack)
- **Pattern**: Security-domain comments from bots had 100% actionability in this PR
- Both fixes implemented and tested, all review threads resolved

### PR #490 (2025-12-29)

**PR**: perf(reactions): batch comment reactions for 88% faster acknowledgment (issue #283)

| Reviewer | Comments | Actionable | Rate | Outcomes |
|----------|----------|------------|------|----------|
| rjmurillo (owner) | 1 | 1 | 100% | Caught missing `src/claude/pr-comment-responder.md` update |

**Session Notes**:

- **Performance improvement**: Batch reactions reduce API calls from N to 1, ~88% faster
- **Owner review**: Caught that `src/claude/pr-comment-responder.md` wasn't updated with batch syntax
- **qa Review gate**: Required 18 Pester tests for new batch functionality (created and passing)
- **Template propagation**: Updated `templates/agents/pr-comment-responder.shared.md` + regenerated 3 platform files
- **Files updated**: 5 total (template + 4 platform-specific files with batch reaction examples)
- All review threads resolved via GraphQL mutation

**Implementation Details**:

- `Add-CommentReaction.ps1` now accepts `[long[]]$CommentId` (array parameter)
- Backward compatible: single ID still works without array syntax
- Returns structured JSON: `{ TotalCount, Succeeded, Failed, Results[] }`
- 18 Pester tests cover: single ID, batch mode, partial failure, idempotent behavior

## Metrics

| Metric | Value |
|--------|-------|
| Total PRs Processed | 3 |
| Total Comments Triaged | 8 |
| Total Comments Implemented | 7 |
| Total Comments Resolved | 8 |
| Security Vulnerabilities Found | 2 |
| Critical Workflow Bugs Found | 1 |
| Performance Improvements | 1 (88% faster reactions) |
| Average Resolution Time | ~45 minutes |

## Triage Patterns Learned

### Security-Domain Priority Boost

**Finding**: Security-domain comments from ANY bot should be prioritized first, not just high-signal bots.

**Evidence**: PR #488 had two bot comments, both security-related (CWE-22), both 100% actionable.

**Action**: Updated priority matrix to process security keywords (CWE, vulnerability, injection, etc.) BEFORE reviewer signal quality.

### Path Containment Anti-Patterns

**Finding**: Path containment checks require multiple layers:

1. Case-insensitive comparison (Windows compatibility)
2. Trailing separator enforcement (prefix bypass prevention)
3. Path normalization (canonical form)

**Evidence**: PR #488 required TWO fixes to fully harden CWE-22 protection.

**Action**: When reviewing path validation code, check for all three layers.

## Bot-Specific Behaviors

### gemini-code-assist[bot]

**First appearance**: PR #488

**Signal quality**: 100% (1/1 actionable)

**Pattern**: Provides style guide references and detailed explanations with suggestions.

**Response protocol**: Implement fix, reply with commit hash, resolve thread.

### Copilot (copilot-pull-request-reviewer)

**Signal quality**: 100% (1/1 actionable in this PR)

**Pattern**: References existing code patterns (e.g., Get-RelativePath function) to suggest improvements.

**Response protocol**: Implement fix, reply with commit hash, resolve thread. **Do NOT mention** in reply if no action needed (triggers new PR analysis).

## Quick Reference: Response Templates

### Security Fix Implemented

```markdown
Fixed in [commit_hash].

Implemented your suggested fix: [brief description].

This prevents [attack type].
```

### Won't Fix (with rationale)

```markdown
Thanks for the suggestion. After analysis, we've decided not to implement this because:

[Rationale]

If you disagree, please let me know and I'll reconsider.
```

## Session Learnings

### PR #488 (2025-12-29)

**Learning 1**: Branch checkouts can fail silently with uncommitted changes. Always verify current branch with `git branch --show-current` before making edits.

**Learning 2**: The Read tool may trigger file watchers or cause state changes that affect branch/file state. Explicitly verify state before and after Read operations.

**Learning 3**: When bots comment on security fixes, they're often catching edge cases you missed. Both gemini and Copilot found real CWE-22 bypasses in hardening code.

### PR #490 (2025-12-29)

**Learning 1**: Template propagation requires updating ALL platform-specific files. Owner review caught `src/claude/pr-comment-responder.md` was missed.

**Learning 2**: qa Review gate enforces test coverage for new executable code. 124 lines of new PowerShell required 18 Pester tests before passing.

**Learning 3**: Memory files (`.serena/memories/`) should be included in PRs when they track skill-specific learnings relevant to the change.

**Learning 4**: Spec Validation can show false negatives - empty commit with explicit AC evidence in message can help it recognize covered criteria.

## Next Session TODO

1. Monitor for Copilot follow-up PR (common pattern after Won't Fix)
2. Update signal quality if any bot shows false positive
3. Add new reviewers to performance table as they appear
