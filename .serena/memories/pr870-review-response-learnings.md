# PR #870 Review Response Session Learnings

**Date**: 2026-01-11
**Context**: Review comment response workflow

## Key Learnings

1. **AI Reviewer Quality Variance**: ChatGPT reviewer caught incomplete exit code documentation that other reviewers (Copilot, CodeRabbit) missed. The script used exit codes 3 and 4 but only documented code 0.

2. **Thread Resolution Protocol**: GitHub review thread replies do NOT automatically resolve threads. Thread resolution requires explicit GraphQL mutation via `Resolve-PRReviewThread.ps1` after posting reply.

3. **PowerShell Help Structure**: `.NOTES` section must come before `.OUTPUTS` section in PowerShell comment-based help. This was already fixed by Copilot SWE agent in commits eb04e93 and 3ba94ae before our session.

4. **Exit Code Documentation Principle**: Documentation must match actual script behavior per ADR-035. Document what the code does, not what you wish it did. Grep for `Write-ErrorAndExit` and `exit ` to find actual exit codes.

## Workflow Patterns

**PR Review Response**:
1. Verify PR not merged: `Test-PRMerged.ps1`
2. Get comprehensive status: `Get-PRReviewThreads.ps1`, `Get-UnresolvedReviewThreads.ps1`, `Get-PRChecks.ps1`
3. Address each comment with fix
4. Post reply: `Post-PRCommentReply.ps1`
5. Resolve thread: `Resolve-PRReviewThread.ps1` (separate step!)
6. Wait 45s and re-check for new comments
7. Verify all completion criteria before claiming done

## Tools Used

- `.claude/skills/github/scripts/pr/Test-PRMerged.ps1` - Check merge state (GraphQL source of truth)
- `.claude/skills/github/scripts/pr/Get-PRReviewThreads.ps1` - List all threads with resolution status
- `.claude/skills/github/scripts/pr/Post-PRCommentReply.ps1` - Reply to review comments
- `.claude/skills/github/scripts/pr/Resolve-PRReviewThread.ps1` - Resolve thread via GraphQL
- `.claude/skills/github/scripts/pr/Get-PRChecks.ps1` - Get CI check status

## Related

- ADR-035: Exit Code Standardization
- pr-review-007-merge-state-verification: GraphQL merge state verification
- pr-review-004-thread-resolution-single: Thread resolution protocol
