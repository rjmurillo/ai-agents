# Skill Sidecar Learnings: QA

**Last Updated**: 2026-01-16
**Sessions Analyzed**: 1 (Session 07)

## Constraints (HIGH confidence)

- Worktree isolation requires BLOCKING gate: Phase 3 blocked until `git worktree list` shows isolated path for each agent (Session 07, 2026-01-16)
  - Evidence: Sessions 40-41 - 4 agents pushed to shared branch `copilot/add-copilot-context-synthesis` instead of isolated branches, caused attribution confusion and deployment risk, 89% atomicity, required 8-minute recovery via cherry-pick

- Pre-push verification checklist MUST verify: branch name matches pattern (feat|fix|audit|chore|docs/\*), NOT on main/master/shared branches, worktree shows isolated path, commits reference single issue/feature (Session 07, 2026-01-16)
  - Evidence: Sessions 40-41 - missing pre-push gate allowed 4 PRs to originate from same branch, worktree verification would have prevented shared branch pollution

## Preferences (MED confidence)

- None yet

## Edge Cases (MED confidence)

- None yet

## Notes for Review (LOW confidence)

- None yet

## Related

- [qa-007-worktree-isolation-verification](qa-007-worktree-isolation-verification.md)
- [qa-benchmark-script-validation](qa-benchmark-script-validation.md)
- [qa-session-protocol-validation-patterns](qa-session-protocol-validation-patterns.md)
- [qa-workflow-refactoring-patterns](qa-workflow-refactoring-patterns.md)
