---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-11-session-10036-b69d836cb-ship-stacked-pytest-partitions-under.json
qaCommit: efb740a275fe9bba3c5c20bc4cddded5a189283e
---

# QA Report: Issue 4854 pytest CI partitions

## Result

PASS for local runtime and static workflow contracts. Five matrix partitions
preserve every collected test. Both bulk jobs finish under 135 seconds locally.

## Evidence

- Full ACT workflow path: exit 0 in 331.34 seconds.
- Bulk partition: 26,712 passed, 36 skipped in 194.27 seconds.
- Serial safety partition: 55 passed in 9.48 seconds.
- Focused workflow and coverage contracts: 125 passed in 3.46 seconds.
- xdist matrix contract: 41 passed in 1.07 seconds.
- System CA workflow contract: 42 passed in 1.22 seconds.
- Fresh CI before the split: bulk reached 98 percent, then the 10-minute job
  cap cancelled it after 624 seconds. The pytest step ran for 476 seconds.
- Root bulk partition: 11,860 passed, 3 skipped in 50.91 seconds.
- Nested bulk partition: 14,858 passed, 33 skipped in 134.47 seconds.
- Split bulk collection parity: 26,754 original and 26,754 partitioned, with
  zero missing, extra, or duplicate node IDs.
- Split coverage combine: four input files merged and emitted coverage XML.
- Updated workflow contracts: 63 passed in 2.86 seconds.
- Partition omission negative control: removing `tests/workflows` failed the
  directory coverage guard.
- Security review: OK. Matrix paths are fixed repository constants, shell
  globbing stays quoted, permissions did not change, and each job remains
  capped at ten minutes.
- Local fallback routing: 142 passed in 5.85 seconds.
- Workflow-local duplicate-run guard: 6 passed, 809 deselected in 1.03
  seconds.
- Secret-safe workflow output: 142 passed in 5.86 seconds.
- Collection parity: 27,154 full and 27,154 partitioned, with zero missing,
  extra, or duplicate node IDs.
- Ruff and actionlint passed.
- CWE-78 scan: zero findings in one scanned Python file.
- Security agent review: PASS for action pins, permissions, matrix arguments,
  artifact boundaries, path filtering, required-check behavior, secrets, and
  system CA trust.

## Partition Counts

| Partition | Collected |
|---|---:|
| Root bulk | 11,863 |
| Nested bulk | 14,891 |
| Mutation | 20 |
| Push safety | 55 |
| PR autofix | 24 |
| Verdict pins | 229 |
| REQ-009 pins | 72 |

## Scope

This report covers local execution, collection parity, workflow structure,
coverage aggregation, and security review. Branch protection owns the GitHub
Actions result.
