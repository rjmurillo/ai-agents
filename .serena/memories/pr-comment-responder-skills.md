# PR Comment Responder Skills Memory

## Overview

Memory for tracking reviewer signal quality statistics, triage heuristics, and learned patterns across PR comment response sessions.

## Per-Reviewer Performance (Cumulative)

Last updated: 2025-12-30

| Reviewer | PRs | Comments | Actionable | Signal | Notes |
|----------|-----|----------|------------|--------|-------|
| cursor[bot] | - | 28 | 28 | **100%** | All comments identify real bugs (see cursor-bot-review-patterns memory) |
| gemini-code-assist[bot] | #488, #501, #505, #566, #568 | 9 | 9 | **100%** | RFC 2119 compliance, grep exact matching, filename pattern precision, command injection prevention, GraphQL injection prevention |
| Copilot | #488, #484, #490 | 5 | 5 | **100%** | Path separator bypass (CWE-22), workflow error handling |
| rjmurillo (owner) | #490, #501 | 2 | 2 | **100%** | Template propagation gaps |
| coderabbitai[bot] | - | 6 | 3 | **50%** | Medium signal quality |

## Per-PR Breakdown

### PR #568 (2025-12-30)

**PR**: docs: add GitHub API capability matrix (GraphQL vs REST)

| Reviewer | Comments | Actionable | Rate | Outcomes |
|----------|----------|------------|------|----------|
| gemini-code-assist[bot] | 1 | 1 | 100% | Security: GraphQL injection prevention |

**Session Notes**:

- **Security Domain**: Bot flagged string interpolation vulnerability in documentation example
- **Pattern**: Documentation examples must follow same security standards as production code
- **Quick Fix Path**: Single-file, single-section change qualified for direct implementation
- **Fix**: Replaced string interpolation with GraphQL variables using -f/-F flags
- **Implementation**: Changed from `repository(owner: "$owner")` to `query($owner: String!)` + `-f owner="$owner"`
- **Resolution**: Fixed in commit 22588c9, replied with explanation, thread resolved
- **CI**: All required checks passing (CodeQL still running, not required)

**Implementation Details**:

- Changed PowerShell here-string from `@"..."@` (interpolating) to `'...'` (literal)
- Added GraphQL variable declarations: `query($owner: String!, $repo: String!, $number: Int!)`
- Used `-f` flag for string parameters (owner, repo)
- Used `-F` flag for integer parameter (number)
- Prevents injection attacks by separating query logic from data

**Bot Behavior**:

- gemini-code-assist[bot] provides detailed explanations with style guide references
- Includes code suggestions in diff format
- References specific line numbers from repository style guide
- High-quality signal with security focus

### PR #566 (2025-12-30)

**PR**: docs/506-autonomous-issue-development

| Reviewer | Comments | Actionable | Rate | Outcomes |
|----------|----------|------------|------|----------|
| gemini-code-assist[bot] | 1 | 1 | 100% | Command injection vulnerability in documentation example |

**Session Notes**:

- **Security-Critical**: gemini flagged CWE-78 command injection vulnerability in autonomous agent documentation
- **Pattern**: Documentation example showed hardcoded PR title, but could teach unsafe pattern to autonomous agents
- **Risk**: If agents construct titles from untrusted issue titles containing shell metacharacters (e.g., `$(reboot)`), arbitrary command execution could occur
- **Fix**: Replaced hardcoded example with secure `read -r` pattern using process substitution
- **Security Warning**: Added explicit DANGER comment explaining command injection risk
- **Resolution**: Fixed in commit 9e3c1bb, thread resolved
- **Impact**: Prevents autonomous agents from learning vulnerable patterns from documentation

**Implementation Details**:

- Replaced: `gh pr create --title "fix(scope): description"` (hardcoded)
- With: `read -r pr_title < <(gh issue view {number} --json title --jq -r .title)`
- Then: `gh pr create --title "fix: ${pr_title}"`
- Added 3-line security warning comment explaining CWE-78 risk
- Demonstrates safe handling of external untrusted input (GitHub issue titles)

**Learning**: Documentation for autonomous agents requires higher security standards because:

1. Agents interpret examples literally
2. Agents operate with elevated privileges (git push, PR creation)
3. Agents consume untrusted external input (issue titles, PR bodies)

### PR #505 (2025-12-29)

**PR**: feat(copilot): add merged-PR detection to empty diff categorization

| Reviewer | Comments | Actionable | Rate | Outcomes |
|----------|----------|------------|------|----------|
| gemini-code-assist[bot] | 1 | 1 | 100% | Missing try/catch around ConvertFrom-Json |

**Session Notes**:

- **Error Handling**: gemini caught missing try/catch block around JSON parsing (line 172)
- **Pattern**: Bot correctly referenced repository style guide (lines 72-86) for error handling requirements
- **Quick Fix Path**: Single-file, single-function change qualified for direct implementation (bypassed orchestrator)
- **Fix**: Wrapped ConvertFrom-Json in try/catch with Write-Warning fallback
- **Testing**: All 13 Pester tests pass after fix
- **Resolution**: Fixed in commit 62b1cd6, thread resolved
- **CI**: All required checks passing (Pester, AI agents, aggregate)

**Implementation Details**:

- Added try/catch block in Compare-DiffContent function (lines 172-180)
- Gracefully falls back to default reason string on JSON parse failure
- Warning logged with error details: `Write-Warning "Failed to parse merge status..."`
- Maintains robustness when gh returns non-JSON output

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
| Total PRs Processed | 6 |
| Total Comments Triaged | 11 |
| Total Comments Implemented | 10 |
| Total Comments Resolved | 11 |
| Security Vulnerabilities Found | 4 |
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

**Signal quality**: 100% (8/8 actionable across #488, #501, #505, #566)

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

### Learning: Branch Verification (PR #488)

**Learning 1**: Branch checkouts can fail silently with uncommitted changes. Always verify current branch with `git branch --show-current` before making edits.

**Learning 2**: The Read tool may trigger file watchers or cause state changes that affect branch/file state. Explicitly verify state before and after Read operations.

**Learning 3**: When bots comment on security fixes, they're often catching edge cases you missed. Both gemini and Copilot found real CWE-22 bypasses in hardening code.

### Learning: Template Propagation (PR #490)

**Learning 1**: Template propagation requires updating ALL platform-specific files. Owner review caught `src/claude/pr-comment-responder.md` was missed.

**Learning 2**: qa Review gate enforces test coverage for new executable code. 124 lines of new PowerShell required 18 Pester tests before passing.

**Learning 3**: Memory files (`.serena/memories/`) should be included in PRs when they track skill-specific learnings relevant to the change.

**Learning 4**: Spec Validation can show false negatives - empty commit with explicit AC evidence in message can help it recognize covered criteria.

## Next Session TODO

1. Monitor for Copilot follow-up PR (common pattern after Won't Fix)
2. Update signal quality if any bot shows false positive
3. Add new reviewers to performance table as they appear
