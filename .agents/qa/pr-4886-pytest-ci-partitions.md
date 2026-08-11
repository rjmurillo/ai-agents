---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-11-session-10036-b69d836cb-ship-stacked-pytest-partitions-under.json
qaCommit: 6af4669941c0f9864782551a2ecbb21fcb75c1c0
---

# QA Report: Issue 4854 pytest CI partitions

## Result

PASS for local runtime and static workflow contracts. Four matrix partitions
preserve every collected test and finish within the local six-to-seven-minute
target.

## Evidence

- Full ACT workflow path: exit 0 in 331.34 seconds.
- Bulk partition: 26,712 passed, 36 skipped in 194.27 seconds.
- Serial safety partition: 55 passed in 9.48 seconds.
- Focused workflow and coverage contracts: 125 passed in 3.46 seconds.
- xdist matrix contract: 41 passed in 1.07 seconds.
- System CA workflow contract: 42 passed in 1.22 seconds.
- Local fallback routing: 142 passed in 5.85 seconds.
- Workflow-local duplicate-run guard: 6 passed, 809 deselected in 1.03
  seconds.
- Secret-safe workflow output: 142 passed in 5.86 seconds.
- Collection parity: 27,148 full and 27,148 partitioned, with zero missing,
  extra, or duplicate node IDs.
- Ruff and actionlint passed.
- CWE-78 scan: zero findings in one scanned Python file.
- Security agent review: PASS for action pins, permissions, matrix arguments,
  artifact boundaries, path filtering, required-check behavior, secrets, and
  system CA trust.

## Partition Counts

| Partition | Collected |
|---|---:|
| Bulk | 26,748 |
| Mutation | 20 |
| Push safety | 55 |
| PR autofix | 24 |
| Verdict pins | 229 |
| REQ-009 pins | 72 |

## Scope

This report covers local execution, collection parity, workflow structure,
coverage aggregation, and security review. Branch protection owns the GitHub
Actions result.
