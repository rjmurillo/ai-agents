---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-12-session-14696-bd686ca2f-resolve-github-issue-4868-end.json
qaCommit: 2afd8ad304b563f9270f1b9b73aba57fc61eabca
---

# PR 4969 Instruction Reserve QA Report

## Scope

Validated instruction corpus byte recovery and the 600-byte default reserve.

## Evidence

| Check | Result |
|---|---|
| Main reproduction | 98,982 of 99,000 bytes, 18 bytes headroom, default exit 0 |
| Main negative control | Explicit 600-byte reserve exits 1 |
| Branch measurement | 98,162 of 99,000 bytes, 838 bytes headroom, default reserve 600 |
| Targeted tests | 444 passed, 1 skipped |
| Real corpus boundary | Reserve 838 passed, reserve 839 failed |
| Override checks | CLI `--reserve 0` and environment override passed |
| Ruff | All changed Python files passed |
| Rule generation | Regeneration produced no diff |
| Pre-PR validation | Exit 0 |
| Pre-push validation | All jobs passed |
| QA agent | PASS, no functional gaps |
| Security agent | PASS, hard ceiling remains independent of reserve |

## Verdict

PASS. The branch fails before concurrent instruction additions can consume the
required reserve. Explicit overrides preserve the existing operator contract.
