# PR Metrics Analysis

You are analyzing pull request metrics to identify opportunities for improving the development workflow.

## Context

The CSV data contains PR metrics with these columns:

- PR: Pull request number
- Commits: Number of commits in the PR
- Additions/Deletions: Lines of code changed
- Changed Files: Number of files modified
- Time to First Review: Time from PR creation to first review
- Comments: Number of review comments
- Participants: Number of people involved
- Feature Lead Time: Total time from first commit to merge
- First to Last Review: Duration of the review process
- First Approval to Merge: Time from approval to merge

## Analysis Focus

### 1. Time to First Review

- Identify PRs with unusually long wait times
- Calculate average and median time to first review
- Flag if average exceeds 4 hours during business days

### 2. Review Comment Density

- High comment counts may indicate insufficient pre-review testing, missing documentation, or complex changes without context
- Target: fewer than 5 comments per PR average

### 3. First to Last Review Duration

- Long review cycles suggest scope creep during review, unclear requirements, or insufficient initial feedback
- Target: Complete reviews within 24 hours

### 4. First Approval to Merge Time

- Long delays after approval indicate merge conflicts, CI pipeline issues, or manual merge bottlenecks
- Target: Merge within 2 hours of approval

### 5. PR Size Correlation

- Analyze if larger PRs correlate with more comments, longer review times, or more participants
- Recommendation threshold: fewer than 500 lines per PR

## Required Output Format

### Summary Statistics

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Avg Time to First Review | HH:MM | <4h | PASS/WARN/FAIL |
| Avg Comments per PR | N | <5 | PASS/WARN/FAIL |
| Avg Review Duration | HH:MM | <24h | PASS/WARN/FAIL |
| Avg Approval to Merge | HH:MM | <2h | PASS/WARN/FAIL |

### Trends

Describe any patterns observed: improving, stable, or degrading.

### Top Issues

| Priority | Issue | Evidence | Recommendation |
|----------|-------|----------|----------------|
| High/Med/Low | Description | Data | Action |

### Actionable Recommendations

Numbered list of specific, actionable improvements with expected impact.

### Verdict

Use one of:

- `VERDICT: PASS` - Metrics are within acceptable ranges
- `VERDICT: WARN` - Some metrics need attention
- `VERDICT: CRITICAL_FAIL` - Significant process issues detected

```text
VERDICT: [PASS|WARN|CRITICAL_FAIL]
MESSAGE: [Brief explanation of overall health]
```
