# Maintenance: Homework Automation Justification

## Skill-Maintenance-003: Homework Automation Justification

**Statement**: 20% hit rate (5/27 PRs) for homework scanning justifies GitHub Action automation

**Context**: When deciding whether to automate homework scanning process

**Evidence**: Session 39 scanning results:
- PRs scanned: 27
- Actionable items found: 5
- Hit rate: 18.5% (~20%)
- Sources: PR #100 (3 items), PR #94 (1 item), PR #76 (1 item)
- Consistency: Multiple PRs from different authors and timeframes

**ROI Analysis**:
- Manual effort: ~90 minutes for 27 PRs (~3.3 min/PR)
- Automation effort: ~4 hours to build GitHub Action
- Break-even: ~73 PRs (at 20% hit rate = 15 issues created)
- Expected usage: 50-100 PRs/year → 10-20 issues created

**Recommendation**: Automate as GitHub Action triggered on PR merge

**Implementation Outline**:
```yaml
name: Homework Scanner
on:
  pull_request:
    types: [closed]
    branches: [main]

jobs:
  scan:
    if: github.event.pull_request.merged == true
    runs-on: ubuntu-latest
    steps:
      - name: Scan for Homework
        run: |
          gh api repos/{owner}/{repo}/pulls/{number}/comments \
            | jq -r '.[].body' \
            | grep -E "Deferred to follow-up|TODO|future improvement"
      
      - name: Create Issues
        if: findings.txt is not empty
        run: |
          # Create GitHub issue with context
          gh issue create --title "..." --body "..."
```

**Atomicity**: 95%

**Source**: Session 38 retrospective (2025-12-20)

**Related Skills**: Skill-Maintenance-002

---

## Pattern: Homework Issue Template

When creating issues from homework scanning, include:

1. **Title**: Clear action from original comment
2. **Source PR**: Link to original PR number
3. **Source Comment**: Link to specific review comment or discussion
4. **Current State**: What exists today
5. **Proposed Solution**: What the deferred work suggests
6. **Category Label**: enhancement, maintenance, bug, etc.
7. **Context**: Relevant code snippets or file paths

**Example**:
```markdown
## Source

From PR #100, comment by CodeRabbit:
https://github.com/owner/repo/pull/100#discussion_r123456789

## Current State

`pester-tests.yml` workflow has duplicated path lists in multiple jobs.

## Proposed Solution

Extract path list to workflow-level `env` variable to eliminate duplication.