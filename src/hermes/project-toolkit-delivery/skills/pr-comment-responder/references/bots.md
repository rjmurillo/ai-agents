# Bot-Specific Handling

## Reviewer Signal Quality

| Reviewer | Signal | Trend | Action |
|----------|--------|-------|--------|
| **cursor[bot]** | 100% | [STABLE] | Process immediately |
| **Human reviewers** | High | - | Process with priority |
| **Copilot** | ~44% | [IMPROVING] | Review carefully |
| **coderabbitai[bot]** | ~50% | [STABLE] | Review carefully |

### Priority Matrix

| Priority | Reviewer | Rationale |
|----------|----------|-----------|
| **P0** | cursor[bot] | 100% actionable, finds CRITICAL bugs |
| **P1** | Human reviewers | Domain expertise, project context |
| **P2** | coderabbitai[bot] | ~50% signal, medium quality |
| **P2** | Copilot | ~44% signal, improving trend |

### Signal Quality Thresholds

| Quality | Range | Action |
|---------|-------|--------|
| **High** | >80% | Process all immediately |
| **Medium** | 30-80% | Triage carefully |
| **Low** | <30% | Quick scan |

### Comment Type Analysis

| Type | Actionability |
|------|---------------|
| Bug reports | ~90% |
| Missing coverage | ~70% |
| Style suggestions | ~20% |
| Summaries | 0% |
| Duplicates | 0% |

## Copilot Behavior

Copilot may:

1. Create follow-up PRs after you reply
2. Post issue comments (not review replies)
3. Continue working even when told "no action needed"

### Follow-Up PR Detection

Pattern:

- Branch: `copilot/sub-pr-{original_pr_number}`
- Target: Original PR's base branch
- Announcement: Issue comment containing "I've opened a new pull request"

### Follow-Up Handling

```bash
# Search for follow-up PR
FOLLOW_UP=$(gh pr list --state=open \
  --search="head:copilot/sub-pr-${PR_NUMBER}" \
  --json=number,title,body,headRefName,baseRefName,state,author)
```

Categories:

**DUPLICATE**: Same changes already applied

```bash
gh pr close ${FOLLOW_UP_PR} --comment "Closing: This follow-up PR duplicates changes already applied in the original PR.

Applied fixes:
- Commit [hash1]: [description]

See PR #${PR_NUMBER} for details."
```

**SUPPLEMENTAL**: Additional issues

```bash
# Evaluate for merge or request changes
gh pr merge ${FOLLOW_UP_PR} --auto --squash --delete-branch
```

**INDEPENDENT**: Unrelated

```bash
gh pr close ${FOLLOW_UP_PR} --comment "Closing: This PR addresses concerns that were already resolved."
```

## CodeRabbit Behavior

CodeRabbit responds to commands:

```text
@coderabbitai resolve    # Resolve all comments
@coderabbitai review     # Trigger re-review
```

Use sparingly. Only resolve after actually addressing issues.

## cursor[bot] Behavior

cursor[bot] has 100% actionability (9/9 comments) - every comment identified a real bug.

- Prioritize these comments for immediate attention
- Bug reports from cursor[bot] are almost always valid
- Process before other reviewers

## Cumulative Performance

| Reviewer | Comments | Actionable | Signal | Trend | Action |
|----------|----------|------------|--------|-------|--------|
| **cursor[bot]** | 9 | 9 | **100%** | [STABLE] | Process immediately |
| **Human reviewers** | - | - | High | - | Process with priority |
| **Copilot** | 9 | 4 | **44%** | [IMPROVING] | Review carefully |
| **coderabbitai[bot]** | 6 | 3 | **50%** | [STABLE] | Review carefully |

**cursor[bot]** has demonstrated 100% actionability (9/9 comments) - every comment identified a real bug. Prioritize these comments for immediate attention.

**Note**: Statistics are sourced from the `pr-review/pr-comment-responder-skills` memory and should be updated after each PR review session.

## Updating Signal Quality

After completing each PR comment response session, update the cumulative table above and the `pr-review/pr-comment-responder-skills` memory with:

1. Per-reviewer comment counts and actionability
2. Any trend changes (improving/declining signal)
3. New patterns observed (e.g., duplicate detection)

## Copilot Follow-Up Handling Detail (Phase 4.5)

Read this when Phase 4.5 finds a follow-up PR. The branch pattern, query, and the three categories are in Copilot Behavior above. This section adds the announcement check, the intent categories with examples, and the full close and merge commands.

Copilot follow-up PRs match:

- **Branch**: `copilot/sub-pr-{original_pr_number}`
- **Target**: Original PR's base branch (not main)
- **Announcement**: Issue comment from `app/copilot-swe-agent` containing "I've opened a new pull request"

**Example**: an original PR → its follow-up PR (branch `copilot/sub-pr-{original_pr_number}`)

### Step 4.5.2: Verify Copilot Announcement

```bash
# Check for Copilot announcement comment on original PR
ANNOUNCEMENT=$(gh api repos/OWNER/REPO/issues/${PR_NUMBER}/comments \
  --jq '.[] | select(.user.login == "app/copilot-swe-agent" and .body | contains("opened a new pull request"))')

if [ -z "$ANNOUNCEMENT" ]; then
  echo "WARNING: Follow-up PR found but no Copilot announcement. May not be official follow-up."
fi
```

### Step 4.5.3: Categorize Follow-Up Intent

Analyze the follow-up PR content to determine intent:

**DUPLICATE**: Follow-up contains same changes as fixes already applied

- Example: the original PR and its follow-up PR (both address same 5 comments)
- Action: Close with explanation linking to original commits

**SUPPLEMENTAL**: Follow-up addresses different/additional issues

- Example: Extra changes needed after initial reply
- Action: Evaluate for merge or request changes

**INDEPENDENT**: Follow-up unrelated to original review

- Example: Copilot misunderstood context
- Action: Close with note

### Step 4.5.4: Execute Decision

**DUPLICATE Decision**:

```bash
# Close with explanation
gh pr close ${FOLLOW_UP_PR} --comment "Closing: This follow-up PR duplicates changes already applied in the original PR.

Applied fixes:
- Commit [hash1]: [description]
- Commit [hash2]: [description]

See PR #${PR_NUMBER} for details."
```

**SUPPLEMENTAL Decision**:

```bash
# Evaluate for merge or request changes
# Option A: Merge if changes are valid and address new issues
gh pr merge ${FOLLOW_UP_PR} --auto --squash --delete-branch

# Option B: Leave open for review
# Post comment on original PR documenting supplemental follow-up
```

**INDEPENDENT Decision**:

```bash
# Close with note
gh pr close ${FOLLOW_UP_PR} --comment "Closing: This PR addresses concerns that were already resolved in PR #${PR_NUMBER}. No action needed."
```

**Handling unnecessary follow-up PRs**:

```bash
# Check if Copilot created a follow-up PR
FOLLOW_UP=$(gh pr list --author "copilot[bot]" --search "base:[branch]" --json number,state)

# If exists and our resolution was "won't fix", close it
gh pr close [follow_up_number] --comment "Closing: Original comment addressed without code changes. See PR #[original]."
```

## Memory References

| Reviewer | Memory Name |
|----------|-------------|
| cursor[bot] | `pr-review/cursor-bot-review-patterns` |
| Copilot | `copilot/copilot-pr-review-patterns` |
| coderabbitai[bot] | (Use `pr-review/pr-comment-responder-skills`) |

Statistics are sourced from `pr-review/pr-comment-responder-skills` memory and should be updated after each PR review session.
