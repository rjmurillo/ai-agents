# ADR Debate Log: ADR-104 amendment bounding the pre-push pytest step (issue #6200)

Panel: full six seats, because the change moves executable enforcement. It sets the pre-push pytest budget in `git_hook_policy.py`, adds a deferral path, and changes a constant that tests and the `testmon-seed` job read.

Each seat ran as its own `claude -p` process (model sonnet) with its agent template from `.claude/agents/` as the system prompt and read-only tools. Seats received the ADR diff, the code diff, the measurements file and the issue's acceptance criteria. They did not receive the author's reasoning. The author consolidated the reports and made the fixes.

## Summary

- **Rounds**: 3
- **Outcome**: No seat blocked. Round 3 votes were five Disagree-and-Commit and one Accept, with no P0, no P1 and no REFUTED claim open. The fixes after round 3 were not re-read by the seats.
- **Final Status**: ADR-104 stays proposed (amended).

## Decision under review

Delegated owner decision for issue #6200, 2026-10-13: pick among a size threshold, a time budget, or both.

- The default pre-push pytest step gets a 180s budget. The full-suite opt-in keeps 780s.
- With no testmon database and no seed, the hook collects the suite instead of running it, prints the count it did not run, and says CI runs it.
- The CI seed job still builds the database from nothing.
- A selection that spends 180s fails the push with a message that names the opt-in.

## Round 1 Summary

### Agent Positions

| Agent | Position | Main finding |
|-------|----------|--------------|
| architect | Disagree-and-Commit | Notice said CI runs on every push; `pytest.yml` triggers push on main only. Container fit claimed without measurement. Stale `origin/main` sentence |
| critic | Disagree-and-Commit | Unedited ADR text still described the cold build. Stale-database dead end after a lock change. 180s calibrated on one host |
| independent-thinker | Disagree-and-Commit | Replay row misdated and misattributed. "Declared worst case" is measured, not declared. Lock-change loop |
| security | Disagree-and-Commit | Replay row. 206s rests on one in-hook run that excluded `push-ref-policy`. First seeded run failed (#6477). Lock-change loop |
| analyst | Disagree-and-Commit | Lock-change overrun not handled. Replay row. Threshold rejection used a mixed-rate comparison |
| high-level-advisor | Disagree-and-Commit | Stale lines 46, 627, 746. "Fits 300s" is arithmetic. Lefthook cap still 15m. Overrun fails while cold defers, unexplained |

### Key Issues Addressed

- The replay-trial row was dated 2026-10-13 but came from the 2026-10-08 trial, on a loaded host, with the sysmon core.
- Unedited ADR text contradicted the amendment: the Status paragraph, the "Chosen 2026-10-09" row, the missing `origin/main` sentence, and the Positive consequence about the first push.
- The deferral notice said CI runs on every push. It runs on pull request and merge-queue events and on pushes to main.
- A `uv.lock` change with a database present re-selects the whole suite, passes 180s, and fails every push. The opt-in does not refresh the database. The ADR did not say so.
- "Idle host" had no source. Load average was 4.36, 7.01 and 8.52 at the first run.
- The first seeded run failed with the xdist collection error of #6477 and the table used the second run.

### Major Changes Made

- The measurements table separates 2026-10-13 runs from the older replay evidence, and the host is described as shared.
- Stale ADR text is updated and the 2026-10-09 rows say what 2026-10-13 changed.
- The notice and the overrun message say CI runs the tests on the pull request and in the merge queue.
- A new "Accepted gaps" list records the lock-change loop, the single 48-thread calibration, the missing collector for the new trigger, and the container dead end for the opt-in.
- The ADR says plainly that the declared bound is the inner budget, that `lefthook.yml` keeps 15m for the opt-in, and that 26s plus 180s is arithmetic from one run.
- The ADR says why an overrun fails instead of deferring: a killed run cannot name the tests it did not reach.
- A revert path is recorded.

## Round 2 Summary

### Agent Positions

| Agent | Position | Note |
|-------|----------|------|
| architect | Accept | P2 only: the 12s figure, load average wording, the 124s to 142s range |
| critic | Disagree-and-Commit | An unsourced "12s" fixed-overhead figure; container fit asserted as fact; #6477 unreported |
| independent-thinker | Disagree-and-Commit | The "12s" figure |
| security | Disagree-and-Commit | The "12s" figure; container fit; #6477; the commit message said "idle" |
| analyst | Disagree-and-Commit | Container fit contradicts the Neutral bullet; "12s"; load average wording |
| high-level-advisor | Disagree-and-Commit | Container fit; #6477 |

### Fixes after round 2

- The "12s" figure is removed. The ADR says neither the fixed nor the per-test magnitude was isolated.
- Both container sentences now say the deferral is expected to fit and nobody has measured it in a container.
- #6477 is named as an accepted gap that this amendment neither causes nor fixes.
- Load average wording cites the three values and says later runs were not checked.
- The "124s to 142s" range became "124s to 128s", the figure the ADR already records for measured pushes.
- The revert list names every symbol and test file the change added.
- The commit message no longer says "idle". Seats were not asked to re-read these edits; they are wording changes verified by search.

### Dissent

The security and critic seats hold that 180s is sized on one 48-thread host and that the 206s sum was not measured with pytest at its cap beside `pre-pr-validation`. The ADR records both as accepted gaps. The author agrees no measurement exists for a 4 to 8 thread host. The re-evaluation trigger (more than 3 overrun failures in a month) is the only mitigation, and it has no collector.

## Round 3 Summary

After round 2 a separate `/review` pass of the branch (security, qa, reliability, correctness and six other axes, each as its own process) found: the overrun message keyed on the clock, an all-empty cold collection passed, a failed collection could print tens of thousands of ids, and the hook test fixture changed three test modules' quality scores. The code changed for all four. A rename and a test-fixture redesign followed. Round 3 re-read the new code and the ADR.

### Agent Positions

| Agent | Position | Note |
|-------|----------|------|
| architect | Disagree-and-Commit | The silent cold deferral was not on the accepted-gaps list; one test path is unreachable in production; the delegation quote |
| critic | Disagree-and-Commit | The delegation quote had no source; a zero-collection guard failed open on an unparseable summary |
| independent-thinker | Disagree-and-Commit | The delegation quote; failing output under `output: false` asserted, not measured; revert list incomplete |
| security | Accept | P2 only: quote marks, exit 5 counted by exit code, revert list |
| analyst | Disagree-and-Commit | Delegation quote; `output: false` claim |
| high-level-advisor | Disagree-and-Commit | Silent deferral belongs in the accepted gaps; the delegation covers choosing among options, not reversing the 2026-10-09 acceptance |

### Fixes after round 3

- The delegation is described as relayed in the agent's task text, with no quote marks and no URL, because none exists.
- Exit 5 from a collect-only run now counts as zero tests by exit code, so an all-empty cold collection fails even when the summary text is unfamiliar.
- A measured line records that failing hooks print under `output: false` and passing ones do not.
- The silent cold deferral is on the accepted-gaps list.
- The revert list names every symbol and comment edit the change added.
- The overrun message notes that the container clamp applies to the opt-in too.

### Dissent

The high-level-advisor seat holds that a delegation to choose among options does not clearly cover reversing an explicit 2026-10-09 acceptance. The ADR names the reversal and gives the revert path, and the pull request body flags it for the owner.

## Verdict

No seat blocked. ADR-104 stays proposed.
