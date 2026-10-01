# Skill Sidecar Learnings: GitHub

**Last Updated**: 2026-09-29
**Sessions Analyzed**: 1

## Observations (HIGH confidence)

- Deleting a stacked PR's base branch with `merge_pr.py --delete-branch` CLOSED the dependent PR instead of retargeting it. PR #6026 closed and was reopened as #6029 during the #5245 stack. Open dependent PRs against main, or retarget each dependent to main before merging and deleting its base. (Session claude-session-0191QTCyqXgwVXfiZgDSfTcn, 2026-09-29)
