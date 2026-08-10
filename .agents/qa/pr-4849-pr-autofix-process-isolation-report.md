---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-10-session-10036-bd1e1475a-serialize-flaky-pr-autofix-process-tests.json
qaCommit: 75c22a3e0fe768b600a93a40819a0789b7b286c4
---

# PR 4849 pr-autofix process isolation

## Result

PASS. Pre-push runs the pr-autofix process-group tests in their own serial
pytest process. Fast mutations that exit before process-group observation now
return their actual status without releasing the PR lease early.

## Evidence

- 83 partition-policy and safe-push tests passed.
- All 24 pr-autofix process tests passed in ten consecutive runs.
- Ruff passed on the three changed Python files.
- `build_all.py` regenerated the Copilot skill mirror.
- Security review found no blocking finding.
- Review regression confirmed the lease remains held after a fast mutation.
- `pre_pr.py` passed all 49 non-session validations. Session validation only
  required this refreshed QA binding.
