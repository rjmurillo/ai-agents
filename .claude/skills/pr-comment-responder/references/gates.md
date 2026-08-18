# Verification Gates

These gates implement RFC 2119 MUST requirements. Proceeding without passing causes artifact drift.

## Gate 0: Continuity

Before work, read the current per-issue handoff when one exists. Keep PR comment
state in the working artifact directory created by the skill. A session log is optional.

**Evidence required**: Transcript or PR artifact identifies the loaded state.

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
PENDING=$(grep -c "^\*\*Status\*\*: pending\|^\*\*Status\*\*: \[ACKNOWLEDGED\]\|^\*\*Status\*\*: \[NEW\]" .agents/pr-comments/PR-[number]/comments.md)

if [ "$REMAINING" -ne 0 ] || [ "$PENDING" -ne 0 ]; then
  echo "[BLOCKED] API unresolved: $REMAINING, Artifact pending: $PENDING"
  exit 1
fi

echo "[PASS] All gates cleared"
```

## Phase 8 Sub-Gates

### Phase 8.1: Comment Status Verification

```bash
ADDRESSED=$(grep -Ec "^\*\*Status\*\*: \[COMPLETE\]" .agents/pr-comments/PR-[number]/comments.md)
WONTFIX=$(grep -Ec "^\*\*Status\*\*: \[WONTFIX\]" .agents/pr-comments/PR-[number]/comments.md)

if [ "$((ADDRESSED + WONTFIX))" -lt "$TOTAL" ]; then
  echo "[WARNING] INCOMPLETE: $((TOTAL - ADDRESSED - WONTFIX)) comments remaining"
fi
```

### Phase 8.2: Conversation Resolution

```bash
SCRIPTS_DIR="${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/github/scripts"

# Resolve all threads for a PR
python3 "$SCRIPTS_DIR/pr/get_pr_review_threads.py" --pull-request [number] --unresolved-only | \
  jq -r '.threads[].thread_id' | while read tid; do
    python3 "$SCRIPTS_DIR/pr/resolve_pr_review_thread.py" \
      --expected-pull-request [number] --thread-id "$tid"
  done
```

Each single-thread resolve requeries the target after the PR-level gate.
`Data.action=SKIP` means the thread is resolved, missing, or belongs to another
PR. Do not retry a safe skip with a lower-level mutation.

### Phase 8.3: Re-check for New Comments

```bash
SCRIPTS_DIR="${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/github/scripts"
sleep 45
NEW_COMMENTS=$(python3 "$SCRIPTS_DIR/pr/get_pr_review_comments.py" --pull-request [number] --include-issue-comments | jq '.TotalComments')

if [ "$NEW_COMMENTS" -gt "$TOTAL_COMMENTS" ]; then
  echo "[NEW COMMENTS] $((NEW_COMMENTS - TOTAL_COMMENTS)) new comments detected"
fi
```

### Phase 8.4: CI Check Verification

**CI-failure triage step 1 (issue #5073)**: when any check is failing, run
`triage_red_check.py` for that check name BEFORE reading logs or starting any
local investigation. The cause frequently lives on main, and each missed
attribution costs a full investigation.

```bash
SCRIPTS_DIR="${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/github/scripts"
python3 "$SCRIPTS_DIR/pr/triage_red_check.py" --check-name "[failing check name]" --pull-request [number]
# Exit 0 = GREEN_ON_MAIN: the PR introduced the failure; investigate the PR.
# Exit 1 = RED_ON_MAIN: inherited from main; cite Data.EvidenceUrl (the main
#          run) in the thread instead of debugging the PR.
# Exit 3 = UNKNOWN: probe failure is not absence; never treat as green.
```

```bash
SCRIPTS_DIR="${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/github/scripts"
checks=$(python3 "$SCRIPTS_DIR/pr/get_pr_checks.py" --pull-request [number])
merge_ref_usable=$(echo "$checks" | jq -r '.Data.MergeRefUsable')
all_passing=$(echo "$checks" | jq -r '.Data.AllPassing')
failed_count=$(echo "$checks" | jq '.Data.FailedCount')

if [ "$merge_ref_usable" = "false" ]; then
    echo "[BLOCKED] PR merge ref cannot be built, so CI status is incomplete"
    exit 1
elif [ "$all_passing" != "true" ]; then
    echo "[BLOCKED] CI checks are not all passing"
    exit 1
elif [ "$failed_count" -gt 0 ]; then
    echo "[BLOCKED] $failed_count CI check(s) not passing"
    exit 1
fi
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
| CI checks pass | MergeRefUsable = true and AllPassing = true |
| No unresolved threads | All resolved |
| Commits pushed | Up to date with origin |

**If ANY criterion fails**: Do NOT claim completion. Return to appropriate phase.
