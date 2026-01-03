# Verification Gates

These gates implement RFC 2119 MUST requirements. Proceeding without passing causes artifact drift.

## Gate 0: Session Log Creation

**Before any work**: Create session log with protocol compliance checklist.

```bash
SESSION_FILE=".agents/sessions/$(date +%Y-%m-%d)-session-XX.md"
```

**Evidence required**: Session log file exists with checkboxes.

## Gate 1: Acknowledgment Verification

**After Phase 2**: Verify eyes reaction count equals total comment count.

```bash
REACTIONS_ADDED=$(cat .agents/pr-comments/PR-[number]/session.log | grep -c "reaction.*eyes")
COMMENT_COUNT=$TOTAL_COMMENTS

if [ "$REACTIONS_ADDED" -ne "$COMMENT_COUNT" ]; then
  echo "[BLOCKED] Reactions: $REACTIONS_ADDED != Comments: $COMMENT_COUNT"
  exit 1
fi
```

## Gate 2: Artifact Creation Verification

**After generating comment map and task list**: Verify files exist and contain expected counts.

```bash
test -f ".agents/pr-comments/PR-[number]/comments.md" || exit 1
test -f ".agents/pr-comments/PR-[number]/tasks.md" || exit 1

ARTIFACT_COUNT=$(grep -c "^| [0-9]" .agents/pr-comments/PR-[number]/comments.md)
if [ "$ARTIFACT_COUNT" -ne "$TOTAL_COMMENTS" ]; then
  echo "[BLOCKED] Artifact count: $ARTIFACT_COUNT != API count: $TOTAL_COMMENTS"
  exit 1
fi
```

## Gate 3: Artifact Update After Fix

**After EVERY fix commit**: Update artifact status atomically.

```bash
sed -i "s/TASK-$COMMENT_ID.*pending/TASK-$COMMENT_ID ... [COMPLETE]/" \
  .agents/pr-comments/PR-[number]/tasks.md

grep "TASK-$COMMENT_ID.*COMPLETE" .agents/pr-comments/PR-[number]/tasks.md || exit 1
```

## Gate 4: State Synchronization Before Resolution

**Before Phase 8**: Verify artifact state matches intended API state.

```bash
COMPLETED=$(grep -c "\[COMPLETE\]" .agents/pr-comments/PR-[number]/tasks.md)
TOTAL=$(grep -c "^- \[ \]\|^\[x\]" .agents/pr-comments/PR-[number]/tasks.md)

UNRESOLVED_API=$(gh api graphql -f query='...' --jq '.data...unresolved.length')

if [ "$COMPLETED" -ne "$((TOTAL - UNRESOLVED_API))" ]; then
  echo "[BLOCKED] Artifact COMPLETED ($COMPLETED) != API resolved"
  exit 1
fi
```

## Gate 5: Final Verification

**After Phase 8**: Verify all threads resolved AND artifacts updated.

```bash
REMAINING=$(gh api graphql -f query='...' --jq '.data...unresolved.length')
PENDING=$(grep -c "Status: pending\|Status: \[ACKNOWLEDGED\]" .agents/pr-comments/PR-[number]/comments.md)

if [ "$REMAINING" -ne 0 ] || [ "$PENDING" -ne 0 ]; then
  echo "[BLOCKED] API unresolved: $REMAINING, Artifact pending: $PENDING"
  exit 1
fi

echo "[PASS] All gates cleared"
```

## Phase 8 Sub-Gates

### Phase 8.1: Comment Status Verification

```bash
ADDRESSED=$(grep -c "Status: \[COMPLETE\]" .agents/pr-comments/PR-[number]/comments.md)
WONTFIX=$(grep -c "Status: \[WONTFIX\]" .agents/pr-comments/PR-[number]/comments.md)

if [ "$((ADDRESSED + WONTFIX))" -lt "$TOTAL" ]; then
  echo "[WARNING] INCOMPLETE: $((TOTAL - ADDRESSED - WONTFIX)) comments remaining"
fi
```

### Phase 8.2: Conversation Resolution

```powershell
pwsh .claude/skills/github/scripts/pr/Resolve-PRReviewThread.ps1 -PullRequest [number] -All
```

### Phase 8.3: Re-check for New Comments

```bash
sleep 45
NEW_COMMENTS=$(pwsh .claude/skills/github/scripts/pr/Get-PRReviewComments.ps1 -PullRequest [number] -IncludeIssueComments | jq '.TotalComments')

if [ "$NEW_COMMENTS" -gt "$TOTAL_COMMENTS" ]; then
  echo "[NEW COMMENTS] $((NEW_COMMENTS - TOTAL_COMMENTS)) new comments detected"
fi
```

### Phase 8.4: CI Check Verification

```powershell
$checks = pwsh -NoProfile .claude/skills/github/scripts/pr/Get-PRChecks.ps1 -PullRequest [number] -Wait -TimeoutSeconds 300 | ConvertFrom-Json

if ($checks.FailedCount -gt 0) {
    Write-Host "[BLOCKED] $($checks.FailedCount) CI check(s) not passing"
    exit 1
}
```

Exit codes:

- `0`: All checks passing
- `1`: One or more checks failed
- `7`: Timeout waiting for checks

### Phase 8.5: Completion Criteria Checklist

| Criterion | Check |
|-----------|-------|
| All comments resolved | grep count equals total |
| No new comments | Re-check returned 0 new |
| CI checks pass | AllPassing = true |
| No unresolved threads | All resolved |
| Commits pushed | Up to date with origin |

**If ANY criterion fails**: Do NOT claim completion. Return to appropriate phase.
