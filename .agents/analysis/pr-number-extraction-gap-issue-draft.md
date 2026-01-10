# Issue Draft: Agent Context Inference Gap - PR/Issue Number Extraction

## Summary

Agents prompt for PR/issue numbers when this information is already present in user input (text or URLs). This blocks autonomous execution workflows and violates the `autonomous-execution-guardrails` principle that autonomous execution requires STRICTER protocols, not looser ones.

## Problem Statement

**User Request**:

```text
Review PR 806 comments, evaluate items, plan and create fixes. 'runSubagent' as needed.
https://github.com/rjmurillo/ai-agents/pull/806
Do not stop until the PR is merged to main
```

**Expected**: Agent extracts PR number "806" from text or URL and proceeds automatically.

**Actual**: Agent prompted for PR number instead of inferring from provided context.

## Impact

- **Blocks autonomous PR workflows**: "Do not stop until merged" execution requires zero human intervention
- **Creates friction**: User must re-provide information already present
- **Violates guardrails**: Prompting for context contradicts autonomous execution principles
- **System-wide issue**: Affects all agents that accept GitHub context (PR, issue, repository)

## Root Cause

1. **Agent definitions lack context inference guidance**
   - pr-comment-responder has `argument-hint: Specify the PR number` but no extraction logic
   - No instruction to parse PR numbers from text patterns ("PR 806", "#806")
   - No instruction to extract from GitHub URLs (`github.com/owner/repo/pull/NNN`)

2. **No shared utility for GitHub context extraction**
   - Each agent would need to implement regex parsing independently
   - No reusable patterns for common GitHub URL formats

3. **Global instructions missing context inference requirements**
   - AGENTS.md has detailed protocol requirements but no context inference section
   - No guidance on "extract before prompt" principle

## Evidence

- Agent definition: `src/claude/pr-comment-responder.md` has 1,551 lines with ZERO lines on context extraction
- Codebase search: No regex patterns for `github.com/owner/repo/pull/\d+`
- Memory reference: `autonomous-execution-guardrails` states STRICTER protocols during autonomy

Full analysis: `.agents/analysis/pr-number-extraction-gap.md`

## Proposed Solution

### Phase 1: Immediate Fix (P0)

Add "Phase -1: Context Inference" to pr-comment-responder skill before memory initialization:

```bash
# Extract PR number from text patterns
PR_NUMBER=$(echo "$USER_INPUT" | grep -oE '(PR\s*#?\s*|#)([0-9]+)' | grep -oE '[0-9]+' | head -1)

# Extract from GitHub PR URL if present
if [ -z "$PR_NUMBER" ]; then
  PR_NUMBER=$(echo "$USER_INPUT" | grep -oE 'github\.com/[^/]+/[^/]+/pull/([0-9]+)' | grep -oE '[0-9]+$')
fi

# Error if no context found (no prompting during autonomous execution)
if [ -z "$PR_NUMBER" ]; then
  echo "[ERROR] No PR number found in input. Provide PR number or GitHub URL."
  exit 1
fi
```

### Phase 2: Shared Utility (P1)

Create `.claude/skills/github/scripts/utils/Extract-GitHubContext.ps1`:

```powershell
<#
.SYNOPSIS
Extracts GitHub context (PR/issue number, repository) from text or URLs.

.EXAMPLE
Extract-GitHubContext -InputText "Review PR 806"
# Returns: @{ Type='PR'; Number=806; Repository=$null }

.EXAMPLE
Extract-GitHubContext -InputText "https://github.com/owner/repo/pull/123"
# Returns: @{ Type='PR'; Number=123; Repository='owner/repo' }
#>
```

Benefits:

- Reusable across all agents
- Consistent parsing logic
- Testable with Pester
- Handles edge cases (repository inference, URL formats)

### Phase 3: System-Wide Guidance (P1)

Update AGENTS.md with "Context Inference Requirements" section:

- Extraction patterns for PR/issue text and URLs
- "Inference Before Clarification" rule
- Integration with Extract-GitHubContext.ps1 utility

## Acceptance Criteria

- [ ] pr-comment-responder extracts PR numbers from text ("PR 806", "#806")
- [ ] pr-comment-responder extracts PR numbers from GitHub URLs
- [ ] Extraction errors rather than prompts during autonomous execution
- [ ] Extract-GitHubContext.ps1 utility created with Pester tests
- [ ] Global guidance added to AGENTS.md
- [ ] All 3 platforms updated (Claude, VS Code, Copilot CLI)

## Non-Goals

- Issue number extraction (similar pattern, defer to separate implementation)
- Repository inference from non-URL context (may infer from current directory)
- Handling of shortened GitHub URLs (gh.io redirects)

## Open Questions

1. Should context extraction be global agent capability or skill-specific?
2. Error vs prompt when extraction fails - should this depend on execution mode?
3. Integration with Claude Code's Task tool argument passing?

## Related

- Memory: `autonomous-execution-guardrails` (STRICTER protocols during autonomy)
- Memory: `agent-workflow-scope-discipline` (document issues, don't expand scope)
- Analysis: `.agents/analysis/pr-number-extraction-gap.md`

## Priority

**P0** - Blocks autonomous PR workflows

## Estimated Effort

- Phase 1 (P0): 2 hours
- Phase 2 (P1): 4 hours
- Phase 3 (P1): 1 hour
- **Total**: ~7 hours

---

**Labels**: enhancement, agent-system, autonomous-execution, priority-high  
**Assignee**: TBD  
**Milestone**: TBD
