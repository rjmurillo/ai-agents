# Script Path Reference Inventory

**Date**: 2026-03-01
**Search Type**: All `.claude/skills/github/scripts/` path references across codebase
**Status**: Complete comprehensive inventory

## Files Containing References: 31 files

### Documentation Files
1. **AGENTS.md** (1 ref)
   - PR: Get-PRContext

2. **SKILL-QUICK-REF.md** (3 refs)
   - PR: Get-UnaddressedComments, Post-PRCommentReply, Get-PRCheckLogs

### .claude/ Directory (11 files)

#### Skills SKILL.md Files
3. **.claude/skills/github/SKILL.md** (relative refs only - `scripts/pr/`, `scripts/issue/`, etc.)

4. **.claude/skills/github-url-intercept/SKILL.md** (4 refs)
   - PR: Get-PRContext, Get-PRChecks
   - Issue: Get-IssueContext
   - Full path prefix documented

5. **.claude/skills/pr-comment-responder/SKILL.md** (1 ref)
   - Utils: Extract-GitHubContext

#### Skills Reference Files
6. **.claude/skills/pr-comment-responder/references/workflow.md** (7 refs)
   - Utils: Extract-GitHubContext (2x)
   - PR: Get-PRReviewComments, Get-PRContext, Get-PRReviewers
   - Reactions: Add-CommentReaction
   - PR: Post-PRCommentReply, Get-PRReviewComments, Get-PRChecks

7. **.claude/skills/pr-comment-responder/references/templates.md** (3 refs)
   - PR: Post-PRCommentReply (3x with variations)

8. **.claude/skills/pr-comment-responder/references/gates.md** (3 refs)
   - PR: Resolve-PRReviewThread, Get-PRReviewComments, Get-PRChecks

9. **.claude/skills/github/fix-ci.md** (3 refs)
   - PR: Get-PRChecks (2x), Get-PRCheckLogs

10. **.claude/skills/github/references/copilot-synthesis-guide.md** (2 refs)
    - Issue: Invoke-CopilotAssignment (2x)

11. **.claude/skills/github/references/examples.md** (relative refs only)

12. **.claude/skills/github/references/patterns.md** (relative refs only)

13. **.claude/skills/github/references/copilot-prompts.md** (relative refs only)

#### Scripts Referencing Scripts
14. **.claude/skills/github/scripts/milestone/Set-ItemMilestone.ps1** (1 ref)
    - Issue: Set-IssueMilestone

15. **.claude/skills/github/scripts/milestone/Get-LatestSemanticMilestone.ps1** (1 ref)
    - Issue: Set-IssueMilestone

#### Commands
16. **.claude/commands/pr-comment-responder.md** (26 refs)
    - PR: Get-PRContext, Get-PRReviewComments, Get-PRReviewers, Post-PRCommentReply, Resolve-PRReviewThread, Get-UnaddressedComments, Get-PRChecks, Add-CommentReaction

17. **.claude/commands/push-pr.md** (2 refs)
    - PR: New-PR (powershell & bash variants)

18. **.claude/commands/pr-review.md** (13 refs)
    - PR: Get-PRContext, Test-PRMerged, Get-PRReviewThreads, Get-UnresolvedReviewThreads, Get-UnaddressedComments, Get-PRChecks, Post-PRCommentReply, Resolve-PRReviewThread

#### Agents
19. **.claude/agents/AGENTS.md** (1 ref)
    - PR: Get-PRContext

20. **.claude/agents/pr-comment-responder.md** (26 refs)
    - Same as commands/pr-comment-responder.md

21. **.claude/agents/analyst.md** (1 ref)
    - Issue: Get-IssueContext

#### Hooks
22. **.claude/hooks/PreToolUse/Invoke-SkillFirstGuard.ps1** (16 refs)
    - PR: Get-PRContext, Get-PullRequests, New-PR, Post-PRCommentReply, Merge-PR, Close-PR, Get-PRChecks
    - Issue: Get-IssueContext, New-Issue, Post-IssueComment, Get-Issues

23. **.claude/hooks/Invoke-UserPromptMemoryCheck.ps1** (doc comment refs, no direct calls)

#### Test Support
24. **.claude/skills/github-url-intercept/scripts/Test-UrlRouting.ps1** (2 refs)
    - PR: Get-PRContext
    - Issue: Get-IssueContext

### .github/ Directory (9 files)

25. **.github/prompts/pr-review.prompt.md** (13 refs)
    - PR: Get-PRContext, Test-PRMerged, Get-PRReviewThreads, Get-UnresolvedReviewThreads, Get-UnaddressedComments, Get-PRChecks, Post-PRCommentReply, Resolve-PRReviewThread

26. **.github/workflows/milestone-tracking.yml** (2 refs)
    - Milestone: Set-ItemMilestone (2x)

27. **.github/workflows/pr-maintenance.yml** (1 ref)
    - PR: Invoke-PRCommentProcessing

28. **.github/workflows/ai-pr-quality-gate.yml** (1 ref)
    - Issue: Post-IssueComment

29. **.github/workflows/ai-spec-validation.yml** (1 ref)
    - Issue: Post-IssueComment

30. **.github/workflows/pr-validation.yml** (2 refs)
    - Issue: Post-IssueComment (Test-Path + conditional call)

31. **.github/workflows/ai-session-protocol.yml** (1 ref)
    - Issue: Post-IssueComment

32. **.github/workflows/copilot-context-synthesis.yml** (2 refs)
    - Issue: Invoke-CopilotAssignment (2x)

33. **.github/workflows/ai-issue-triage.yml** (2 refs)
    - Issue: Post-IssueComment (2x)

34. **.github/scripts/AIReviewCommon.psm1** (5 refs - comments only)
    - PR: Post-PRCommentReply, Get-PRContext
    - Issue: Post-IssueComment, Set-IssueLabels
    - Reactions: Add-CommentReaction

35. **.github/scripts/AIReviewCommon.Tests.ps1** (commented out refs)

### .github/agents/ (2 files)
36. **.github/agents/pr-comment-responder.agent.md** (10 refs)
37. **.github/agents/pr-comment-responder.prompt.md** (10 refs)

### src/ Directory (4 files)
38. **src/copilot-cli/pr-comment-responder.agent.md** (10 refs)
39. **src/vs-code-agents/pr-comment-responder.agent.md** (10 refs)
40. **src/claude/AGENTS.md** (1 ref)
41. **src/claude/pr-comment-responder.md** (18 refs)
42. **src/claude/analyst.md** (1 ref)

### templates/ Directory
43. **templates/agents/pr-comment-responder.shared.md** (10 refs)

### .githooks/
44. **.githooks/pre-commit** (comment examples, 2 refs)
    - Illustrative examples referencing path pattern matching

## Script Existence Status: ALL VERIFIED PRESENT

All referenced scripts exist in `/home/richard/src/GitHub/rjmurillo/ai-agents2/.claude/skills/github/scripts/`:

**PR Scripts** (23 total):
- Post-PRCommentReply.ps1 ✓
- Get-ThreadConversationHistory.ps1 ✓
- Merge-PR.ps1 ✓
- Get-PullRequests.ps1 ✓
- Get-PRReviewThreads.ps1 ✓
- Test-PRMergeReady.ps1 ✓
- Get-PRChecks.ps1 ✓
- Get-UnresolvedReviewThreads.ps1 ✓
- Resolve-PRReviewThread.ps1 ✓
- Get-ThreadById.ps1 ✓
- Detect-CopilotFollowUpPR.ps1 ✓
- Close-PR.ps1 ✓
- Get-PRContext.ps1 ✓
- Unresolve-PRReviewThread.ps1 ✓
- Add-PRReviewThreadReply.ps1 ✓
- Set-PRAutoMerge.ps1 ✓
- Test-PRMerged.ps1 ✓
- New-PR.ps1 ✓
- Get-PRCheckLogs.ps1 ✓
- Get-UnaddressedComments.ps1 ✓
- Get-PRReviewers.ps1 ✓
- Invoke-PRCommentProcessing.ps1 ✓
- Get-PRReviewComments.ps1 ✓

**Issue Scripts** (6 total):
- Post-IssueComment.ps1 ✓
- Get-IssueContext.ps1 ✓
- Set-IssueAssignee.ps1 ✓
- Invoke-CopilotAssignment.ps1 ✓
- Set-IssueLabels.ps1 ✓
- New-Issue.ps1 ✓
- Set-IssueMilestone.ps1 ✓

**Milestone Scripts** (2 total):
- Set-ItemMilestone.ps1 ✓
- Get-LatestSemanticMilestone.ps1 ✓

**Reactions Scripts** (1 total):
- Add-CommentReaction.ps1 ✓

**Utils Scripts** (1 total):
- Extract-GitHubContext.ps1 ✓

**Top-level Scripts**:
- Test-WorkflowLocally.ps1 ✓

## Key Findings

1. **Path Reference Style Variations**:
   - Full path: `.claude/skills/github/scripts/pr/Get-PRContext.ps1`
   - Relative path (from skill): `scripts/pr/Get-PRContext.ps1`
   - Home-relative: `$HOME/.claude/skills/github/scripts/pr/Get-PRContext.ps1`

2. **Invocation Patterns**:
   - Standard: `pwsh .claude/skills/github/scripts/pr/Get-PRContext.ps1 -PullRequest 123`
   - NoProfile: `pwsh -NoProfile .claude/skills/github/scripts/pr/Get-PRContext.ps1 ...`
   - Direct invoke: `& ./.claude/skills/github/scripts/issue/Invoke-CopilotAssignment.ps1`
   - Conditional: `Test-Path ".claude/skills/github/scripts/issue/Post-IssueComment.ps1"` then call

3. **Documentation Frequency**:
   - Most frequently documented: `.claude/commands/pr-comment-responder.md` (26 refs)
   - Also in: `.claude/agents/pr-comment-responder.md` (duplicate, 26 refs)
   - Reference copies in: `src/claude/pr-comment-responder.md`, `templates/agents/pr-comment-responder.shared.md`

4. **No Python Scripts Found**:
   - All GitHub scripts are PowerShell (.ps1)
   - ADR-042 mentions "Python-first preference" but this is for NEW scripts
   - Existing scripts are grandfathered PowerShell

5. **Downstream Consumption Points**:
   - `.github/workflows/*.yml` directly invoke scripts
   - `src/` directory has platform-specific agent definitions (Copilot CLI, VS Code)
   - `templates/` contains shared templates for multi-platform distribution
