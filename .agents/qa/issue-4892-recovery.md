---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-12-session-14694-bd686ca2f-recover-validate-ship-issue-4892.json
qaCommit: dd8dc0a65df6b0c10c11de83adb4787362a4f20e
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

## Post-review Refresh

Commit `ac2599c71d56bd9a0d3b2ed5b00608e24a6716b5` addressed all three
review threads.

- 61 targeted markdown validation tests passed.
- Ruff passed on the four changed Python files.
- The real markdownlint smoke test passed.
- Independent code review returned `CLEAN`.
- The completion gate found one suppressed non-BMP path issue. Commit
  `9b6a419b30dddbeeba9d175b5f9c071e5465092f` fixed it.
- 62 targeted tests passed after measuring Windows command length in UTF-16
  code units.
