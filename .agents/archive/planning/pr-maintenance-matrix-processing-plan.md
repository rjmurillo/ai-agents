# Refactoring Plan: PR Maintenance Matrix Processing

## Goal

Transform `scripts/Invoke-PRMaintenance.ps1` from a monolithic script that does everything into a thin orchestration layer that:
1. Identifies which PRs need attention
2. Outputs PR list for GitHub Actions matrix to spawn parallel processing jobs

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Invocation method | GitHub Actions matrix | Parallel processing, workflow-native |
| AI agent invocation | `ai-review` composite action with Copilot CLI | Existing infrastructure, already works |
| Implementation execution | PowerShell scripts | Copilot CLI is read-only, scripts do mutations |
| Conflict resolution | Combine with merge-resolver skill | Already exists at `.claude/skills/merge-resolver/`, DRY |

## Architecture Constraint

**Critical**: The `ai-review` action uses GitHub Copilot CLI which is **read-only analysis only**. It returns verdicts, labels, and findings but **cannot make file changes, commits, or API calls**.

Therefore, the workflow must:
1. Use `ai-review` for **analysis/triage** (what needs to be done)
2. Use PowerShell scripts for **execution** (actually doing it)

## Current State

### Invoke-PRMaintenance.ps1 Responsibilities (5 areas, ~2000 lines)

| Area | Functions | Lines | Purpose |
|------|-----------|-------|---------|
| **PR Discovery** | Get-OpenPRs, Get-DerivativePRs, Get-PRsWithPendingDerivatives | 386-408, 1213-1361 | Find PRs needing attention |
| **Classification** | Get-BotAuthorInfo, Test-IsBotAuthor, Test-IsBotReviewer | 517-1000 | Categorize by activation trigger |
| **Comment Handling** | Get-PRComments, Get-UnacknowledgedComments, Get-UnaddressedComments, Add-CommentReaction | 410-782 | Acknowledge and track comments |
| **Synthesis** | Invoke-CopilotSynthesis | 784-850 | Generate @copilot prompts |
| **Conflict Resolution** | Resolve-PRConflicts, Test-SafeBranchName, Get-SafeWorktreePath | 82-211, 1015-1211 | Auto-resolve merge conflicts |

### pr-comment-responder Workflow (8 phases)

- Phase 0-1: Context gathering (uses github skill scripts)
- Phase 2: Comment map generation & acknowledgment
- Phase 3-4: Orchestrator analysis & task generation
- Phase 5-6: Reply & implementation
- Phase 7-8: PR update & verification

## Proposed Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│   pr-maintenance.yml (GitHub Actions Workflow)                              │
│                                                                             │
│   Job 1: discover-prs                                                       │
│   ├── Run Invoke-PRMaintenance.ps1 -OutputJson                              │
│   ├── Output: ActionRequired PR list as JSON                                │
│   └── Set matrix output for parallel jobs                                   │
│                                                                             │
│   Job 2: process-prs (matrix: pr-numbers from Job 1)                        │
│   ├── Checkout PR branch                                                    │
│   ├── Step: Resolve conflicts (PowerShell script, conditional)              │
│   ├── Step: Acknowledge comments (PowerShell, add eyes reaction)            │
│   ├── Step: Analyze with ai-review (pr-comment-responder agent + prompt)    │
│   ├── Step: Parse triage output (PowerShell, extract JSON findings)         │
│   └── Step: Execute fixes based on analysis (to be designed)                │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Type | Role |
|-----------|------|------|
| `Invoke-PRMaintenance.ps1` | PowerShell | Discover PRs, output matrix JSON (DONE) |
| `Resolve-PRConflicts.ps1` | PowerShell | Auto-resolve HANDOFF.md/sessions conflicts |
| `ai-review` action | Copilot CLI | Read-only analysis, triage comments |
| `pr-comment-responder` | Agent def | Agent personality for triage decisions |
| `pr-comment-triage.md` | Prompt file | Task-specific instructions for ai-review |
| PowerShell scripts | PowerShell | Execute mutations (acknowledge, reply, etc.) |

### Solution: Add Execution Mode to ai-review

Extend the `ai-review` action with an optional `execute-script` input:

1. Copilot CLI runs analysis (existing behavior)
2. If `execute-script` is provided, run that script after analysis
3. Pass analysis output (findings JSON) to the script
4. Script does the mutations (acknowledge, reply, commit, push)

```yaml
# Workflow usage
- uses: ./.github/actions/ai-review
  with:
    agent: pr-comment-responder
    context-type: pr-diff
    pr-number: ${{ matrix.number }}
    prompt-file: .github/prompts/pr-comment-triage.md
    execute-script: .claude/skills/github/scripts/pr/Invoke-PRCommentProcessing.ps1
    bot-pat: ${{ secrets.BOT_PAT }}
    copilot-token: ${{ secrets.COPILOT_GITHUB_TOKEN }}
```

## Critical Files

| File | Change Type | Status |
|------|-------------|--------|
| `.github/actions/ai-review/action.yml` | Add `execute-script` input and step | DONE (PR #459) |
| `.github/workflows/pr-maintenance.yml` | Update to use ai-review with execution | DONE (PR #459) |
| `.github/prompts/pr-comment-triage.md` | New prompt for comment triage | DONE (PR #459) |
| `.claude/skills/github/scripts/pr/Invoke-PRCommentProcessing.ps1` | New execution script | DONE (PR #459) |
| `scripts/Invoke-PRMaintenance.ps1` | Already outputs JSON (DONE in PR #453) | DONE |
| `.claude/skills/merge-resolver/scripts/Resolve-PRConflicts.ps1` | Already exists | DONE |
| `.claude/skills/github/scripts/pr/Get-UnaddressedComments.ps1` | Already exists | DONE |
| `.claude/skills/github/scripts/pr/Get-UnresolvedReviewThreads.ps1` | Already exists | DONE |

## Completion Status

**Plan completed**: 2025-12-27 via PR #459

All implementation steps have been delivered. Follow-up item #461 tracks migration from `$DryRun` to PowerShell-idiomatic `-WhatIf` pattern.

## Implementation Steps

### Step 1: Add Execution Mode to ai-review Action

Modify `.github/actions/ai-review/action.yml`:

1. **Add new input**:
   ```yaml
   inputs:
     execute-script:
       description: 'Optional PowerShell script to run after analysis'
       required: false
       default: ''
   ```

2. **Add new step after parsing**:
   ```yaml
   - name: Execute post-analysis script
     if: inputs.execute-script != ''
     shell: pwsh -NoProfile -Command "& '{0}'"
     env:
       GH_TOKEN: ${{ inputs.bot-pat }}
       AI_VERDICT: ${{ steps.parse.outputs.verdict }}
       AI_FINDINGS: ${{ steps.invoke.outputs.raw_output }}
       AI_LABELS: ${{ steps.parse.outputs.labels }}
       PR_NUMBER: ${{ inputs.pr-number }}
     run: |
       & "${{ inputs.execute-script }}" `
         -PRNumber $env:PR_NUMBER `
         -Verdict $env:AI_VERDICT `
         -FindingsJson $env:AI_FINDINGS
   ```

### Step 2: Create Triage Prompt

Create `.github/prompts/pr-comment-triage.md`:

```markdown
# PR Comment Triage

Analyze the PR comments and provide a structured triage:

## Output Format (JSON)

{
  "comments": [
    {
      "id": 123456,
      "author": "gemini-code-assist",
      "classification": "quick-fix|standard|strategic|wontfix|question",
      "priority": "critical|major|minor",
      "action": "implement|reply|defer|clarify",
      "summary": "Brief description of what needs to be done"
    }
  ],
  "synthesis_needed": true/false,
  "copilot_author": true/false
}

## Classification Rules
- quick-fix: Single file, clear fix, no architecture impact
- standard: Needs investigation, may affect multiple files
- strategic: Question is whether not how
- wontfix: Decline with rationale
- question: Need clarification

VERDICT: PASS if all comments triaged successfully
```

### Step 3: Create Execution Script

Create `.claude/skills/github/scripts/pr/Invoke-PRCommentProcessing.ps1`:

```powershell
param(
    [int]$PRNumber,
    [string]$Verdict,
    [string]$FindingsJson
)

# 1. Parse findings
$findings = $FindingsJson | ConvertFrom-Json

# 2. Acknowledge comments (add eyes reaction)
foreach ($comment in $findings.comments) {
    ./Add-CommentReaction.ps1 -CommentId $comment.id -Reaction 'eyes'
}

# 3. Process by classification
$quickFixes = $findings.comments | Where-Object { $_.classification -eq 'quick-fix' }
# ... implement fixes using existing scripts

# 4. Post replies
foreach ($comment in $findings.comments | Where-Object { $_.action -eq 'reply' }) {
    ./Post-PRCommentReply.ps1 -PRNumber $PRNumber -CommentId $comment.id -Body "..."
}

# 5. Resolve threads if all comments addressed
./Resolve-PRReviewThread.ps1 -PullRequest $PRNumber -All
```

### Step 4: Update Workflow

Update `.github/workflows/pr-maintenance.yml` process-prs job:

```yaml
process-prs:
  needs: discover-prs
  if: needs.discover-prs.outputs.has-prs == 'true'
  runs-on: ubuntu-24.04-arm
  timeout-minutes: 30
  strategy:
    matrix: ${{ fromJson(needs.discover-prs.outputs.matrix) }}
    fail-fast: false
    max-parallel: 3

  steps:
    - name: Checkout
      uses: actions/checkout@v4
      with:
        fetch-depth: 0

    - name: Checkout PR branch
      env:
        GH_TOKEN: ${{ secrets.BOT_PAT }}
      run: gh pr checkout ${{ matrix.number }}

    - name: Resolve conflicts (if needed)
      if: matrix.hasConflicts
      shell: pwsh -NoProfile -Command "& '{0}'"
      run: |
        ./.claude/skills/merge-resolver/scripts/Resolve-PRConflicts.ps1 `
          -PRNumber ${{ matrix.number }} `
          -BranchName '${{ matrix.headRefName }}' `
          -TargetBranch '${{ matrix.baseRefName }}'

    - name: Process PR comments
      uses: ./.github/actions/ai-review
      with:
        agent: pr-comment-responder
        context-type: pr-diff
        pr-number: ${{ matrix.number }}
        prompt-file: .github/prompts/pr-comment-triage.md
        execute-script: .claude/skills/github/scripts/pr/Invoke-PRCommentProcessing.ps1
        timeout-minutes: 15
        bot-pat: ${{ secrets.BOT_PAT }}
        copilot-token: ${{ secrets.COPILOT_GITHUB_TOKEN }}
```

## Success Criteria

| Criterion | Metric |
|-----------|--------|
| ai-review supports execution | `execute-script` input works |
| Matrix job processes PRs | Parallel processing of discovered PRs |
| Comments acknowledged | Eyes reaction added to each comment |
| Findings returned as JSON | Parseable by execution script |
| Existing tests pass | No regression in ai-review behavior |

## Execution Order

1. Add `execute-script` input to ai-review action
2. Add post-analysis step to ai-review action
3. Create pr-comment-triage.md prompt
4. Create Invoke-PRCommentProcessing.ps1 script
5. Update pr-maintenance.yml workflow to use new approach
6. Test with a single PR manually
7. Enable scheduled runs
