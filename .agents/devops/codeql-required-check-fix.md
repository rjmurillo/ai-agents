# Fix: CodeQL Required Check Not Reporting

## Problem

The `CodeQL` required status check (integration_id 57789) is never created when no scannable files are changed in a PR. This blocks merging even when all other checks pass.

## Root Cause

The `github/codeql-action/analyze` action creates the `CodeQL` check via the Code Scanning integration (app_id 57789). When analysis is skipped due to no scannable file changes, this action never runs, so the required check is never created.

The workflow correctly:

1. Runs the `analyze` job unconditionally
2. Skips the actual analysis steps when no scannable files changed
3. Creates a `CodeQL Analysis Report` via dorny/test-reporter

But the `CodeQL` check from app 57789 is only created by the actual CodeQL action.

## Solution

Update the GitHub ruleset to replace the `CodeQL` (integration 57789) check with the `Analyze (python)` and `Analyze (actions)` checks (integration 15368) which always run.

## Steps to Apply (GitHub UI)

1. Go to: <https://github.com/rjmurillo/ai-agents/settings/rules>
2. Click on **"Copilot review for default branch"** ruleset
3. Scroll to **Required status checks**
4. **Remove**: `CodeQL` (integration_id: 57789)
5. **Add**: `Analyze (python)` (integration_id: 15368)
6. **Add**: `Analyze (actions)` (integration_id: 15368)
7. Save the ruleset

## Verification

After applying the fix:

1. PR #975 should show all required checks passing
2. Future PRs without scannable files will not be blocked
3. PRs with scannable files still get full CodeQL analysis (results appear in Security tab)

## References

- Ruleset ID: 11104075
- PR blocked: #975
- Session: 2026-01-18-session-07-release-plan
