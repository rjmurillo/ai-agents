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

## Memory References

| Reviewer | Memory Name |
|----------|-------------|
| cursor[bot] | `cursor-bot-review-patterns` |
| Copilot | `copilot-pr-review-patterns` |
| coderabbitai[bot] | (Use pr-comment-responder-skills) |

Statistics are sourced from `pr-comment-responder-skills` memory and should be updated after each PR review session.
