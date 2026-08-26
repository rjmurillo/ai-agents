<!-- # taste-lint: ignore file-size, append-only review record; rounds are cited by number from the ADR, the tests, and the commit log; splitting breaks those references and the audit continuity. -->
# ADR Debate Log: ADR-104 Gate Tier Placement

## Summary

- **Rounds**: 8
- **Outcome**: Consensus to revise. Two Block votes, three Disagree-and-Commit,
  one Accept-with-findings. Every P0 was resolved by changing the code or the
  record, not by deferring it.
- **Final Status**: proposed, revised. `implemented: false` until merge.

Six seats reviewed the first revision of ADR-104 against the implementation on
`claude/pre-push-hook-performance-audak0`. Four additional agents reviewed the
implementation itself (code review, silent-failure, test coverage, CI wiring).
Phase 0 related-work research was folded into the seat prompts rather than run
as a separate pass: issues #5315, #4710, #5066, #5050 and ADRs 004, 049, 054,
071, 086, 101 were supplied as context and each seat verified what it used.

## Round 1

### Agent positions

| Agent | Position | Core objection |
|-------|----------|----------------|
| architect | Block | Rule 6's premise false; rule 3 violated by the shipping hook; ADR-054 and ADR-071 conflicts uncited |
| critic | Block | Rules 4 and 5 rest on "CI executes the same commit", false for the dominant change class; two of four claimed defect classes not caught |
| independent-thinker | Disagree-and-Commit | Same two premises; direction right, both statements ship to developers in hook output |
| security | Disagree-and-Commit | `.claude/skills/**` executes in neither plane; piping does not prove a glob-filtered job ran |
| analyst | Disagree-and-Commit | The 140s projection does not follow from its own components; the exit-1 causal claim unsupported |
| high-level-advisor | Disagree-and-Commit | Median fixed, tail untouched; the glob defect is the one no other seat's remit covers |

### P0 issues and resolution

**P0-1. The deduplication was unsound.** Raised independently by architect
(A2), critic (C3), security (S2), independent-thinker (I5), advisor (H1) and
the silent-failure agent. `piped: true` proves no earlier job failed, not that
one ran; every deferral target carries a `glob:` and `pre-pr-validation` does
not. The silent-failure agent settled it empirically on lefthook 2.1.10 against
a fixture repo: a glob-filtered job prints `(skip) no matching push files` and
the hook exits 0, so a skipped job is indistinguishable from a passed one.

Resolved by reverting the skip (`248797b4a`) rather than by weakening the
claim. The test that shipped with it checked job names and ordering, which
catches a rename and misses this entirely; it is rewritten as a regression
guard carrying the condition that would make a deferral sound, plus a negative
control proving the condition discriminates. Issue #5317 carries three costed
options for removing the duplication properly.

**P0-2. Two of four claimed defect classes are not caught by collection.**
Raised by architect (A4), critic (C2), independent-thinker (I2), each probing
independently. A test requesting a missing fixture collects clean, exit 0. Two
same-named test functions in one module collect and execute clean. Only the
import case, the syntax case, and a same-basename module collision exit
non-zero.

The false claim appeared in the ADR, in a docstring, and in the stderr line
developers read to decide what they are covered for. Corrected in all three
(`f215f6661`). Rule 5 now says "a defect class you have measured it to catch"
and names the two that failed.

**P0-3. "CI executes the same commit" was false at PR time.** Raised by critic
(C1), security (S1), independent-thinker (I1) and confirmed in detail by the
CI-wiring agent, which also found the mitigating fact nobody else had: `pytest.yml`
declares `merge_group` and `FORCE_RUN_EVENTS: merge_group`, so the paths filter
is bypassed in the merge queue and `main` was never exposed. The exposure was a
reviewer approving a green PR whose relevant tests had not run, with the
skip-through job carrying the same required check name.

Resolved two ways: the paths filter gained the Markdown roots its own tests
read (`134fd03f5`), each justified by a named test; and the stand-in's message
now states the merge-queue-versus-PR-time distinction instead of asserting
unconditional coverage.

### P1 issues resolved in this round

- The 140s projection did not follow from its cited components (analyst N1:
  the same arithmetic gives ~148.5s, and the "roughly 46s" term is a 3-of-4
  partial sum). The projection is removed rather than repaired; MUST-16 says a
  standalone sum is not a number to trust, and the real figure arrives with the
  first push.
- The exit-1 attribution was wrong (analyst N2). The mutation partition failed
  because its target file was being edited while the run was in flight, which
  the harness refuses by design; the `gh` GraphQL line came from a partition
  that passed. Corrected to state that 382s is a duration measurement and
  nothing more.
- `-q` was cancelled by `addopts = "-v ..."` (architect A9), printing 31,765
  lines into hook output per fallback push against 878 with three `-q`. Fixed;
  this was a token-cost regression in a change whose purpose includes cutting
  token cost.
- The record claimed no prior ADR set a pre-push cost bar (architect A8).
  ADR-054 set a qualitative one. Corrected and cited.
- Rule 3 was violated by the shipping hook with no exception clause (architect
  A1, advisor H2, independent-thinker I7), and ADR-071 had deliberately placed
  the credentialed e2e smokes in pre-push six days earlier. A Known
  non-conformances section now names all five jobs and cites ADR-071.
- ADR-054's enforced 900s `security-scan` budget contradicts the 300s target
  (architect A3). Named in the record as unreconciled rather than papered over.
- `AI_AGENTS_PYTEST_FULL_SUITE_LOCALLY` silently ignored every value but "1"
  (silent-failure agent), so `export ...=true` gave less work than requested
  with no notice. Now raises.
- `run_pytest` returned 0 for an empty command list (silent-failure agent). The
  invariant lives in another module; the function that decides whether a push
  is allowed now carries its own guard.
- The 14s / 34.62s inconsistency between the record and its own constant
  comment (critic C4, advisor H5, independent-thinker I4). Both are real, idle
  and loaded; the comment now says which, and the budget is sized from the
  loaded one per MUST-16.
- The inverted mutation control had its polarity broken by this branch
  (test-coverage agent): asserting exact stderr text made it die to a single
  added space, which is the opposite of an inverted control's job. Restored,
  with the exact-text assertion split into its own test. Its unverifiable
  "a mutation harness consumes this" docstring is dropped; nothing under
  `tests/mutation/` references it.
- The load-bearing broken-import claim had no executing test (test-coverage
  agent). Added end to end against a real tree with a clean-tree negative
  control, plus tests for the reason pass-through and for the collection
  ceiling appearing in a timeout message.
- `implemented: true` on an unmerged record (architect A10,
  independent-thinker I10). Set to false per ADR-073.

### Deferred with issues filed

- The duplication between `pre-pr-validation` and the fast stage, worth roughly
  40s per push: issue #5317, three costed options.
- The unmeasured tail (five glob-gated jobs, never timed when their globs
  fire), the unmeasured pre-commit target, the selector/CI-filter divergence, a
  hook-level deadline, and the ADR-054 reconciliation: issue #5318.

### Dissent recorded

The advisor seat dissented against shipping the record without the rule 3
exception clause and without fixing the glob defect. Both were done in this
round, so the dissent is satisfied rather than carried.

The analyst seat had no shell in its harness and could not run four of the
reproduction commands it was asked to run. Its claim audit is therefore
partial by construction, and it said so (N3). The orchestrator supplied those
measurements from its own runs; a future round should route a seat with
execution to confirm them independently.

The architect seat's A5 (eight pre-push jobs the tier model cannot place:
six advisory reporters and two local-state repair actions) is **not** resolved.
The record does not add a placement rule for non-blocking reporters. It is
recorded here as an open gap rather than folded into #5318, because it is a
question about the tier model itself rather than about pre-push cost.
*Closed in Round 6 as rules 9 and 10, where the count of local mutators is also
corrected from two to one.*

## Next steps

1. Measure the hook end to end on the first real push and put the number in the
   record. Acceptance is gated on it.
2. Work #5317 before re-attempting any deduplication.
3. Work #5318's five items; the tail is the part of the operator's stated
   problem this record does not solve.

## Round 2: the acceptance gate closed

Round 1 ended with acceptance gated on one thing no seat could supply: an
end-to-end in-hook measurement of the pre-push hook during a real push.
`ci-scripts.md` MUST-16 forbids sizing a pre-push budget from a standalone run,
and every number Round 1 had was standalone. The critic (C4),
independent-thinker (I3), advisor (H5) and architect (A7) seats each raised
this independently, from four different angles.

The first push of this branch supplied it. Lefthook 2.1.10, same 4-CPU
container:

```text
total                        142.39s   (679s recorded for a comparable push)
  pre-pr-validation          105.48s   (110.12s recorded)
  fast parallel stage         55.32s   ( 56.21s recorded, max member 20.62s)
  python-tests                15.10s   (498.52s recorded)
  security-scan               13.02s
```

Three findings from Round 1 are settled by this rather than argued:

- The analyst's N1 objection to the 140s projection is moot. The projection was
  removed rather than repaired, and the measured figure, 142.39s, happens to
  land near it. That is a coincidence worth naming, not a vindication: the
  projection's arithmetic was still wrong, and it would have been wrong at any
  outcome.
- The advisor's "median fixed, tail untouched" verdict holds exactly. Every
  glob-gated tail job cost under 3s on this push because none of their globs
  fired hard. Nothing here measures the tail; issue #5318 still owns it.
- The shape changed. `pre-pr-validation` is now 74% of the hook. The
  duplication the advisor's H1 and the reverted skip were both about is now the
  largest remaining target, which raises issue #5317's priority.

The first push attempt also produced an unplanned observation. The
`mutation-safety` guard refused it in 0.33s, on leftover harness state from a
SIGKILLed run earlier in the session. Its own `recover` command could not clear
the marker: the marker compares a file hash against a snapshot taken before
commits that legitimately advanced HEAD, so a clean tree still reads as
modified. Clearing it required proving by hand that the working tree matched
HEAD. That is a real gap in the harness's recovery path and is recorded against
issue #5318.

The architect seat's A5 remains open and unaddressed: the tier model still has
no placement rule for the six non-blocking advisory reporters or the two
local-state repair actions in pre-push.
*Closed in Round 6.*

## Round 3: bounding the declared worst case

Round 2 closed the acceptance gate with a measured 142.39s push and left the
advisor seat's verdict standing: the median was fixed, the tail was not. The
operator's requirement is that pre-push must stop being a cause of aborted
container pushes, and a 4.8x median cut does not on its own establish that.

The gap was concrete. Two real pushes measured 142.39s and 144.39s. The
**declared** worst case of the same graph was 4170s, 69.5 minutes, 29x higher,
because caps had been sized on unloaded machines and never revisited. A cap is
not a cost, but it is the promise about the worst case, and the worst case is
what reclaims a container.

Three things changed.

**Seventeen caps resized from in-hook measurement.** The stdin group carried
four caps of 5m and 2m for jobs measured at 0.93s, 0.28s, 0.38s and 0.38s. The
fast parallel gates carried 5m each against a slowest member of 20.62s.
`python-type-check` carried 15m against 2.73s. Margins were left far above the
9x to 15x in-hook inflation `ci-scripts.md` MUST-16 records for this graph.

**Inner budgets pulled under their outer caps.** `python-tests` 30m to 15m with
its suite budget 1740s to 780s, and `workflow-local-run` 30m to 10m with its
budget 1740s to 540s, so the inner timeout fires first and the reader gets a
diagnostic rather than a bare kill, per ADR-086 Decision item 9.

**A ratchet on the declared total**, which is rule 7's ceiling half that Round 1
noted was missing (architect A6, critic C5, advisor H3). It models lefthook's
scheduling from the config rather than from a run summary, per MUST-17, and
carries a negative control raising a cap to 99h.

Result: 4170s to 2610s, 69.5 to 43.5 minutes.

One cut was reverted during the work and is worth recording, because it is the
same class of coupling the reverted deduplication was. Cutting
`pre-pr-validation` from 15m to 5m failed
`test_check_generated_staleness_termination.py`: that job's Generated Artifact
Staleness gate clamps to `PRE_PR_OUTER_CAP_SECONDS` and a test pins
budget-plus-grace at or under half the cap. The 15m was load-bearing for an
invariant two files away. It also bought nothing, since a parallel group costs
its slowest member and that is a 20m e2e job either way.

### What is still not solved

43.5 minutes is not a survivable declared worst case, and the ratchet stops it
rising rather than bringing it down. The remaining 2100s is two job classes:

- the two CLI e2e smokes at 20m each, which set the expensive group's cost;
- `security-scan` at 15m, which ADR-054 sets as an enforced 900s budget.

Attempts to measure the four glob-gated tail jobs while firing were
inconclusive: each scopes its work to `origin/main...HEAD` and short-circuits
when the branch does not touch its inputs, and `workflow-local-run` is DEGRADED
in a container because actionlint is absent. So they are unmeasured while
firing, and a push whose glob fires one can still outlive a container. That is
the honest residual, and it is issue #5318, not a claim this record can make.

## Round 4: closing the container bound

Round 3 cut the declared worst case from 4170s to 2610s and left the
requirement open. The record said so plainly: a push whose glob fires an e2e
smoke could still outlive a container, and cutting those caps without measuring
them would be the guess MUST-16 forbids.

The way out was not a better guess. It was noticing that a workstation and a
container are asking different questions and had been given one answer.

A workstation needs a long cap for a job with real work to do; a long cap costs
patience there. A container is reclaimed after a period without progress, so
the same cap is a job that can outlive its environment and take the push with
it, leaving no diagnostic at all. `_run_command` is the funnel every expensive
pre-push job's work passes through, so clamping its child's deadline to 150s
when `_is_remote_container()` is true bounds the container case without
touching the workstation case or CI.

The detection was not invented for this. Issue #2548 already added it for
`workflow-local-run`, and already established the precedent of degrading a
pre-push job in a container rather than blocking on an environment gap. Reusing
it was the difference between a new concept and an application of an existing
one.

```text
declared, workstation   4170s -> 2370s   (69.5 -> 39.5 min)
container-clamped         n/a ->  660s   (        11.0 min)
```

660s sits below the roughly 679s at which a reclamation was observed.

Two things this round is worth recording beyond the numbers.

**A 100x margin two files away was holding 900s in place.**
`pre-pr-validation` could not drop below a 15m cap because its Generated
Artifact Staleness gate clamps to `PRE_PR_OUTER_CAP_SECONDS` and a test pins
budget plus grace at or under half that cap. The budget was 420s for work
measured at 1s. Nothing in `lefthook.yml` mentions that constraint, and an
earlier attempt to cut the cap failed the staleness test rather than any hook
test. This is the same shape as the reverted deduplication: a local edit that
looks free because the thing it depends on lives somewhere the edit does not
touch.

**Nine cap cuts silently hit the wrong hook.** The first pass edited by job
name with a regex, and nine job names exist in both `pre-commit` and
`pre-push`; the regex matched the pre-commit copy each time. It was caught only
because the container assertion still failed afterward with
`infrastructure-advisory=300` in its own failure message, a number that should
have been 60. Without an assertion that printed the contributing jobs, the
commit would have shipped looking correct. Both budget assertions now name
their three largest contributors for that reason.

### Still open after this round

- The workstation declared worst case is 39.5 minutes against a 300s target.
  The two e2e smokes account for 1200s of it and remain unmeasured while
  firing. Issue #5318. This is slow rather than destructive.
- ADR-054's enforced 900s `security-scan` budget still contradicts the 300s
  target. In a container the clamp bounds it at 150s regardless, which lowers
  the stakes but does not reconcile the two records.
- The architect seat's A5, no placement rule for the six advisory reporters or
  the two local-state repair actions, is unaddressed for a fourth round.
  *Closed in Round 6.*

### Round 4 addendum: the first cap set was too tight in one place

The fourth real push came back green at 142.47s, and it also showed
`pre-pr-validation` at 106.34s against the 3m cap that round had just given it.
1.7x headroom is thin, and a cap that blocks a legitimate push wastes the same
time the whole record is about; a false block is not a safer failure than a
slow push, only a different one.

Rebalanced rather than accepted: the subprocess clamp drops 180s to 150s, which
every job routing through it can afford (python-tests is the largest at 38.84s,
a 3.9x margin), and the reclaimed budget goes to `pre-pr-validation` as a 4m
cap, 2.3x over its measured cost. The container bound lands at 660s, exactly at
the ceiling, so the graph now has no slack: any new pre-push job fails the
assertion until something is measured and cut. That is the intended state for a
ratchet, not an accident.

## Round 5: CI red, and the sum was the wrong quantity

Round 4's push went green locally and red in CI. Five tests failed, all in
`tests/test_lefthook_integration.py`, all mine, and the cause was a process
failure rather than a design one: the local verification ran a subset of the
suite, not the suite. The PR's own instruction to run the repo's fast checks
before pushing was followed against the wrong scope.

The defect underneath was a fourth coupling of the kind this log keeps
recording. `test_each_python_subprocess_budget_has_lefthook_headroom` requires
every job invoking `git_hook_policy` to carry a cap at least 30s above its
inner child budget, so the inner timeout fires first and the reader gets a
diagnostic rather than a bare kill (ADR-086 item 9). With
`DEFAULT_SUBPROCESS_TIMEOUT_SECONDS` at 90, nine jobs cut to 20s and 60s were
below a floor that appears nowhere in `lefthook.yml`. Restored.

`MYPY_TIMEOUT_SECONDS` was the exception worth cutting instead: 840s for a gate
scoped to changed files and measured at 2.73s in-hook. That number was not a
budget for the work, it was the thing forcing a 15m outer cap through the
headroom rule.

### The container assertion was measuring the wrong thing

Round 4 asserted that the sum of the clamped caps stayed under 660s, chosen to
sit below the roughly 679s at which a reclamation was observed. That comparison
does not hold up:

- the sum is the case where every job in the graph hangs to its cap on the same
  push, which cannot happen;
- 679s is a single measured push, not a cap.

Two different quantities, compared because both were in seconds. A hang is one
job, so the property worth asserting is per job:

```text
declared sum, workstation        2850s   (was 4170s)
largest single job, container     240s   (was 1800s)
```

The per-job bound is the honest form of the claim Round 4 wanted to make, and
it is stronger where it matters: it holds no matter how many jobs a push fires.

### A third thing the clamp exposed

`test_cli_e2e_runs_with_clean_plugin_environment` asserts the e2e child receives
`CLI_E2E_TIMEOUT_SECONDS`. This repository's dev containers set `CLAUDECODE`, so
the clamp was firing inside the test and it was reading the clamp rather than
the budget it exists to pin. It now pins the workstation contract explicitly,
and two new tests cover the cases it cannot: a container clamps the child, and
CI does not inherit the clamp even when a container marker is present. That
last one matters because a real hang in CI is a real failure and must surface
as one.

## Round 6: A5 closed, and the count in it was wrong

The architect seat's A5 has been open since Round 1 and unaddressed through
five: the tier model had no placement rule for the pre-push jobs that are not
gates. It is closed here as rules 9 and 10, and closing it required disputing
the finding's own arithmetic.

A5 named "six advisory reporters and two local-state repair actions." The six
is right, and the mechanism behind it is not uniform, which is the part worth
a rule. Five return 0 in their own code, where a test can read the guarantee:
`python-lint-advisory` via `ruff --exit-zero`, and `additions-advisory`,
`observation-sync-advisory`, `bot-cascade-advisory`, and
`infrastructure-advisory` via handlers whose only top-level return is
`return 0`. The sixth is not like the others. `gc_worktrees.py` returns 2 or 3
on failure and `worktree-gc-report` appends `|| echo ...` in `lefthook.yml` to
swallow it, so the job is advisory by nine characters of YAML that no reader of
the script can see. Deleting them promotes it to a blocking gate nobody sized.

The two is wrong. Only `repair-packed-refs` mutates local state.
`mutation_workspace` takes `check` or `recover`, only `recover` writes, and the
hook runs `check`, so `mutation-safety` is an ordinary read-only blocking guard
already covered by rule 2. Had the rule been written to the finding as stated,
it would have justified an ordering constraint `mutation-safety` does not need,
and the ADR would have carried a fabricated requirement for as long as anyone
trusted it.

That makes six instances on this branch of one failure: a number held in place
from somewhere the number is not written down. Rule 7's caps, the
`_GATE_BUDGET_SECONDS` coupling, `MYPY_TIMEOUT_SECONDS`, the sum-versus-measured
comparison, the 300s assertion behind a 240s claim, and now a count of local
mutators taken from a job name. The name `mutation-safety` describes what the
job protects, not what it does; `repair-packed-refs` describes what it does on
the happy path, not that it blocks. Both readings failed the same way, in
opposite directions.

The rule that follows from the reporters is worth stating separately from the
rule about them. Rules 1 through 4 sort checks by what they block and how
early. A job that cannot fail is outside that sort entirely, and the tier
budget is the only thing it can be judged against, because latency is the whole
of what it costs. Six jobs sitting in pre-push that can never stop a push is
not obviously wrong, but it was never a decision either, and rule 9 makes it
one: a local slot is earned by output the developer acts on before the PR
exists, and an advisory read on the PR belongs on the PR.

### The record crossed a size threshold, and the remediation was code-shaped

Rules 9 and 10 took ADR-104 to 537 lines, and the taste count ratchet rejected
the push at 577 against a baseline of 576. The linter's remediation is to split
the file into helpers, types, and constants, which is advice for a module and
means nothing for a decision record; the ten rules are cited by number from this
log and from tests, so any split renumbers them. Declared as a frontmatter
exception, the same form four other ADRs already carry.

The way it surfaced is worth more than the decision. The first run of the
ratchet was piped to `tail`, which reported the pipeline's exit 0 while the
script had exited 1, and the regression was invisible for one turn. That is the
same defect as the backgrounded-push false completion recorded in this session's
opening retrospective: the exit code read was not the exit code that mattered.
Twice in one session, in two different tools, from the same cause.

It also argues for the tier boundary this record draws. The check that would
have cost a full push round trip ran locally in under a second, which is rule
2's case stated as an event rather than a principle.

### Still open after this round

- The workstation declared worst case is 47.5 minutes against a 300s target.
  The two e2e smokes account for 1200s of it and remain unmeasured while
  firing. Issue #5318. Slow rather than destructive: in a container the clamp
  bounds each at 150s.
- ADR-054's enforced 900s `security-scan` budget still contradicts the 300s
  target. Issue #5318.
- `pre-pr-validation` is roughly 70% of the hook and the cheap way to cut it
  was the unsound one. Issue #5317.
- Rule 9 states where a reporter belongs; nothing yet enforces it, and no
  reporter has been moved or removed on its authority. The rule is a decision
  the next reader can apply, not a change to this hook.

## Round 7: a reviewer read the config the probes did not

The PR left draft and Copilot reviewed all 17 files. Two findings landed on
load-bearing claims, and both were right.

**Rule 5's third catch does not exist here.** `pyproject.toml` sets
`--import-mode=importlib`. A same-basename module collision is a collection
error under pytest's default `prepend` mode and collects clean under
`importlib`. Every probe behind the claim ran in a throwaway tree with no
config, so all of them silently measured the other mode. Verified both ways:
the collision exits 2 under the default and 0 under production configuration,
while a broken import and a syntax error exit 2 under both.

That claim was stated in four places and carried a behavior test added
specifically to prove it. The test passed for the wrong reason. Round 6 argued
that three surfaces agreeing is not the same property as any of them being
true, and added the behavior tests on exactly that reasoning; the reasoning was
right and the fixture was still wrong, which is the sharper lesson. A test that
executes the real command against a real tree is only as faithful as the
environment it builds, and an absent config file is an environment choice made
by omission.

The fixture now copies `addopts` out of the real `pyproject.toml` rather than
restating them, so it cannot drift the way a hand-maintained duplicate would,
and the collision is pinned as a negative: if anyone drops `importlib`, the test
fails and says to move the class back into the catches.

**The per-job container bound is a per-child bound.** The clamp applies to one
subprocess. `run_pytest` holds an aggregate deadline and passes each child its
remaining time, so that job is bounded, but at 780s on the opt-in path rather
than 240s. `scan_pushed_heads` holds no aggregate deadline at all: it loops
over pushed refs and each `_scan_pushed_head` gets a fresh 150s, so N refs cost
up to N times 150s. The assertion is evidence for "no single subprocess
outlives the container" and only incidentally for the per-job reading.

Recorded at the constant rather than quietly restated, because the difference
is the whole safety claim. The measured hook is ~148s end to end and the
default path spawns one child, so the exposure is a tail case; that argues for
sizing the fix deliberately, not for keeping a bound that does not hold. Issue
#5318.

**Six citations pointed at the wrong issue.** #5316 is a closed Renovate action
bump, confirmed through the API. The work is tracked by #5315, #5317, and
#5318. A wrong issue number is the cheapest possible version of this branch's
recurring pattern and it survived every gate, because nothing resolves a
citation to check that it says what the citing text claims.

Also corrected: the ADR recorded a retired 1740s suite budget and an unchanged
30m cap that this branch had already cut to 780s and 15m, and this log declared
one round while containing six.

**Two filter roots were missing, found by reading tests rather than the
filter.** `tests/build_scripts/test_hook_contract_knowledge.py` opens
`.agents/critique/ADR-084-debate-log.md` and `tests/test_pr_identity_gate.py`
reads `templates/agents/`. Both trees were absent from `pytest.yml`, so a PR
touching only them still skipped the suite. The colocated test checks that
every root in the filter is read by a test and cannot check the reverse, which
the PR named as unprovable; these are what that gap looked like in practice.

### Still open after this round

- No aggregate deadline in `scan_pushed_heads`, so `security-scan` has no job
  bound in a container. Issue #5318.
- The budget model credits a clamp to any job not on the unclamped roster
  without proving its command routes through `_run_command`. A job renamed or
  replaced with a direct command would pass falsely.
- A container-clamp timeout reports the aggregate budget rather than the clamp
  that actually fired, sending the reader to the wrong limit.

## Round 8: the same correction, stopping short twice more

A second Copilot pass on the corrected head. Two findings were new and two were
places the previous round's correction had not reached.

**The opt-in flag was validated on one branch of two.**
`AI_AGENTS_PYTEST_FULL_SUITE_LOCALLY` was checked inside `_full_suite_stand_in`,
which only the fallback paths reach, so a narrowed import-graph selection
silently ignored `=true`. The developer asked for the full suite, did not get
it, and was not told. Every existing opt-in test drives the fallback path, so
all of them passed with the hole open.

This is the same defect already fixed for `AI_AGENTS_PYTEST_WORKERS`, hoisted
out of the executing partitions a few commits earlier with the reasoning
written at the call site. The reasoning sat two lines above the sibling flag
and was not carried across. Fixing one instance of a pattern is not fixing the
pattern, even when the fix is three lines and the second instance is adjacent.

**The per-job retraction reached one of its two homes.** Round 7 corrected the
Consequences section and left the Decision section asserting the same bound.
That is the identical partial-correction failure Round 7 had just recorded
about the issue body and PR description, committed again in the same artifact
within one commit of writing it down. Both now state the enforced property.

**Five more filter roots, found the same way as the previous two.**
`PULL_REQUEST_TEMPLATE.md`, `.agents/schemas/`, `.claude/settings.json`,
`.claude/hooks/`, and `src/copilot-cli/hooks/` are each opened by a test and
matched nothing: the filter carries no `**/*.json` or `**/*.md`, so every JSON
or Markdown input has to be named to be seen. Seven roots over two rounds, all
found by reading tests rather than the filter, is the argument for a
reverse-direction guard rather than a third round of this. That needs to
resolve a path out of a test at rest, which is AST work; #5318 carries it.

### Still open after this round

- `scan_pushed_heads` has no aggregate deadline, so `security-scan` has no
  job-level bound in a container. Issue #5318.
- `push-ref-policy` carries a 2m cap over `check_push_refs`, which runs many
  git children sequentially at 90s each. Raised this round and unverified; the
  same aggregate-versus-child shape as the two above.
- The budget model credits a clamp to any job not on the unclamped roster
  without proving its command routes through `_run_command`.
- A container-clamp timeout reports the aggregate budget rather than the clamp
  that fired.
- No reverse-direction guard on the CI filter.
