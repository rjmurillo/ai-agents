---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-12-session-14694-bd686ca2f-recover-validate-ship-issue-4892.json
qaCommit: e3be5c7ae623f6d109ca23403673b39e6bd893fa
---

# Issue 4892 Recovery QA

## Current Main Reproduction

Current `origin/main` selected probe files under `worktrees/`,
`.agent-scratch/`, and `.scratch/`. A 4,168 target run with 1,042,000
argument characters exited 249 with empty stdout and stderr. The validator
then printed only MD040 and MD033 guesses.

## Fixed Branch Verification

After merging current `origin/main`, the same three probes produced zero
scratch targets. A simulated exit 249 reported the exit code and empty tool
output without rule guesses.

## Automated Evidence

- 60 targeted tests passed.
- Ruff passed on the four changed Python files.
- GPT-5.6 Sol reviewed the issue artifact and branch diff. Result: `CLEAN`.
