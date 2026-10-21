# Historical issue-to-fix control subtraction: protocol v3

Issue #6814. Supersedes `PROTOCOL-v2.md` for the primary result. Committed
before any v3 live launch.

## Why v2 was not enough

An independent review of the runner after the v2 batch (`runs/2026-10-21-v2/`)
found that every cell's workspace sat in one shared directory and none was
deleted after grading. Cells run `full` before `minus` within each repeat, so
when a `minus` cell launched, the graded `full` cell beside it still held the
withheld test file and that agent's change. Its Bash allowlist (`cat`, `ls`,
`git`, `python3`) could read them, and so could Read, Grep, and Glob.

v2's recorded Bash commands touch only each cell's own workspace, and its
`withheld_marker_hits` is empty in every run. But v2 recorded no inputs for
Read, Grep, or Glob, so a read through those tools cannot be ruled out. v2 is
published as superseded, not as the result.

## The changes

1. **Isolation.** A graded historical cell is deleted (workspace, review copy,
   and Claude profile) before the next cell launches, and the extracted base
   tree is deleted as soon as the controls hold its bytes. When an agent runs,
   the workspace root holds only its own cell and the version probe.
2. **Leak audit.** Run entries add `other_tool_inputs` (every non-Bash tool
   call's input, clipped to 200 characters per field). Withheld markers add
   the 7-character fix SHA and the runner checkout's path, which holds the
   shipped fix.
3. **Trajectory.** `test_commands` now lists only test commands that ran;
   `denied_test_commands` lists the ones the allowlist refused.
4. **Spend cap.** Fails closed: once any cell's cost is unmeasured (a timeout,
   or a failure that reported no cost), no further cell launches.
5. **Provenance.** Taken before the first launch, and records
   `runner_tree_dirty` and a diff hash.
6. **Task file.** Adds a non-graded `notes` key carrying a citation-freshness
   marker. The prompt, checks, scope, and controls are byte-identical to v2.

The review's other fixes (refusing `minus:AGENTS.md` and `minus:CLAUDE.md`,
refusing harness-owned `--pass-env` names, requiring full hex SHAs) refuse
configurations this protocol never uses.

## Unchanged from v1 and v2

Task, base and fix commits, seeded paths, allowed scope, prompt, both checks
and the deselected node, `known_good` and `known_bad`, controls `full` and
`minus:.claude/rules/voice.md`, model `claude-sonnet-5-5`, 4 repetitions per
arm interleaved, 0 retries, 900 s per launch, `--max-runs 8`,
`--max-cost-usd 25`, auth flags, the PATH fix from v2, per-run fields, abort
conditions, and the decision rule in `PROTOCOL.md`.

The decision rule and repetition count were declared in v1 before any score
existed. v1 and v2 scores were seen before this file was written; neither the
rule nor the repetitions change in response to them.
