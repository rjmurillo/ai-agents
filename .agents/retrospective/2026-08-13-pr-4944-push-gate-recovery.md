# PR #4944 pre-push gate recovery

**Date**: 2026-08-13  
**PR**: #4944  
**Session**: 14696  
**Outcome**: Recovered without bypassing hooks.

## Timeline

1. Session 14696 reused the QA report path already bound to session 14695.
2. The first hook-enabled push rejected the branch-wide session validation.
3. The same push found the branch three commits behind `origin/main`.
4. The stale base omitted generated `src/copilot-cli/lib/hook_dispatch_protocol.py`.
5. The unreachable-code hook failed, although the wider `pre_pr` scan passed.
6. `origin/main` merged cleanly. Session 14695 regained its original QA binding.
7. Session 14696 received a unique QA report path. Focused tests and code stayed green.
8. The policy then required this retrospective. Pre-commit generated the episode evidence.

## Root causes

The session protocol treats QA evidence as session-scoped. Repointing session
14695's report to session 14696 invalidated the older session's binding.

The branch base was stale before the expensive push. Its missing generated
dispatcher module exposed a reachability failure outside the broader scan.

## Recovery

Restore the session 14695 QA binding. Give session 14696 its own QA report.
Merge `origin/main` before retrying. Keep the hook failures as evidence and
accept the hook-generated episode file unchanged.

## Prevention rules

- Use one QA report path for each session.
- Refresh from `origin/main` before an expensive push.
- Never bypass pre-push hooks.
- Accept hook-generated episode evidence. Do not edit it manually.

## Evidence

- PR #4944, session 14696.
- First hook-enabled push: session-binding and unreachable-code failures.
- Recovery state: focused tests and code green after the clean `origin/main` merge.
