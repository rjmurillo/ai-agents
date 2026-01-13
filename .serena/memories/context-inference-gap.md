# Context Inference Gap - GitHub PR/Issue Extraction

**Date**: 2026-01-08  
**Issue**: Agents prompt for PR/issue numbers when already present in user input  
**Impact**: Blocks autonomous execution, violates autonomous-execution-guardrails  
**Status**: IDENTIFIED - Implementation pending

## Problem

Agents lack guidance and utilities for extracting GitHub context (PR numbers, issue numbers, repository names) from:

1. Natural language text ("PR 806", "#806", "Issue 42")
2. GitHub URLs (`https://github.com/owner/repo/pull/123`)

This causes agents to prompt users for information already provided, blocking autonomous workflows.

## Root Cause

**Triple Gap**:

1. **Agent Definitions**: No context inference phase in agent workflows
   - pr-comment-responder: 1,551 lines, ZERO on context extraction
   - `argument-hint: Specify PR number` but no extraction logic

2. **Shared Utilities**: No reusable GitHub context extraction patterns
   - No regex patterns for `github.com/owner/repo/pull/\d+`
   - No shared PowerShell function for parsing

3. **Global Guidance**: AGENTS.md missing "extract before prompt" principle
   - Has protocol requirements, constraint lists, command references
   - MISSING: Context inference requirements section

## Evidence

**User Request**:
```text
Review PR 806 comments, evaluate items, plan and create fixes.
https://github.com/rjmurillo/ai-agents/pull/806
Do not stop until the PR is merged to main
```

**Agent Behavior**: Prompted for PR number (WRONG)

**Expected**: Extract "806" from text or URL automatically (RIGHT)

## Solution Architecture

### Phase -1: Context Inference (Agent-Level)

Add pre-flight context extraction to agents that accept GitHub context:

```bash
# Extract PR number from text or URL
PR_NUMBER=$(echo "$USER_INPUT" | grep -oE '(PR\s*#?\s*|#)([0-9]+)' | grep -oE '[0-9]+' | head -1)
if [ -z "$PR_NUMBER" ]; then
  PR_NUMBER=$(echo "$USER_INPUT" | grep -oE 'github\.com/[^/]+/[^/]+/pull/([0-9]+)' | grep -oE '[0-9]+$')
fi

# Error if no context (no prompting during autonomous execution)
if [ -z "$PR_NUMBER" ]; then
  echo "[ERROR] No PR number found. Provide PR number or GitHub URL."
  exit 1
fi
```

**Rationale**: Autonomous execution requires STRICTER protocols (no user prompts)

### Shared Utility: Extract-GitHubContext.ps1

**Location**: `.claude/skills/github/scripts/utils/Extract-GitHubContext.ps1`

**Capabilities**:
- Extract PR/issue numbers from text patterns
- Parse GitHub URLs for number and repository
- Return structured PSCustomObject: Type, Number, Repository, URL
- Handle edge cases (multiple matches, invalid input)

**Test Coverage**: Pester tests for all extraction patterns

### Global Guidance: AGENTS.md Context Inference Requirements

New section after "Commands (Essential Tools)":

**GitHub Context Patterns**:

| Pattern | Example | Regex |
|---------|---------|-------|
| PR text | "PR 806", "#806" | `PR\s*#?\s*(\d+)` |
| PR URL | `github.com/owner/repo/pull/123` | `github\.com/([^/]+)/([^/]+)/pull/(\d+)` |
| Issue text | "Issue 42", "#42" | `Issue\s*#?\s*(\d+)` |
| Issue URL | `github.com/owner/repo/issues/42` | `github\.com/([^/]+)/([^/]+)/issues/(\d+)` |

**Rule**: Extract BEFORE prompting. If extraction fails, THEN error or prompt.

## Implementation Priority

| Task | Priority | Effort | Status |
|------|----------|--------|--------|
| Add Phase -1 to pr-comment-responder | P0 | 2h | PENDING |
| Create Extract-GitHubContext.ps1 | P1 | 4h | PENDING |
| Update AGENTS.md | P1 | 1h | PENDING |
| Update agent frontmatter | P2 | 15m | PENDING |
| Add pre-commit validation | P3 | 2h | PENDING |

**Total Effort**: ~9 hours

## Related Memories

- [autonomous-execution-guardrails](autonomous-execution-guardrails.md): STRICTER protocols during autonomy
- [agent-workflow-scope-discipline](agent-workflow-scope-discipline.md): Document issues, don't expand scope
- [session-320-pr806-review](session-320-pr806-review.md): PR #806 review (different context issue)

## Analysis Artifacts

- `.agents/analysis/pr-number-extraction-gap.md`: Full root cause analysis
- `.agents/analysis/pr-number-extraction-gap-issue-draft.md`: GitHub issue draft

## Open Questions

1. Should extraction be global agent capability or skill-specific?
2. Error vs prompt when extraction fails - depends on execution mode?
3. Integration with Claude Code's Task tool argument passing?

## Pattern: Inference Before Clarification

**Anti-Pattern**: Prompt for information when context is discoverable

```python
# WRONG
def handle_pr_request(user_input):
    pr_number = prompt_user("What PR number?")
    process_pr(pr_number)
```

**Correct Pattern**: Extract, THEN prompt only if extraction fails

```python
# RIGHT
def handle_pr_request(user_input):
    pr_number = extract_pr_number(user_input)
    if not pr_number:
        pr_number = prompt_user("No PR number found. Provide number or URL:")
    process_pr(pr_number)
```

**Autonomous Mode**: Error instead of prompt

```python
# AUTONOMOUS MODE
def handle_pr_request(user_input, autonomous=False):
    pr_number = extract_pr_number(user_input)
    if not pr_number:
        if autonomous:
            raise ValueError("No PR number found in input")
        else:
            pr_number = prompt_user("Provide PR number or URL:")
    process_pr(pr_number)
```
