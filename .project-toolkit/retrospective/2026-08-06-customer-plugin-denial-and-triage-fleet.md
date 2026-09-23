# Retrospective: Customer Plugin Denial and the 95-Issue Triage Fleet

**Date**: 2026-08-06
**Scope**: Issue #4672 customer fix, structural guard, and the surrounding fleet session
**Branch**: fix/4672-plugin-install-fail-open

---

## What was delivered

A customer on a Windows Dev Box installed `project-toolkit` and every Copilot
CLI tool call was denied. Three prior customers hit the same class and
uninstalled. The fix makes the dispatcher degrade instead of deny when the
plugin cannot load, and adds a guard workflow that runs on every pull request
across Linux, macOS, and Windows, including two vanilla rows that genuinely
lack a Python interpreter rather than simulating one.

All twelve guard jobs pass on real runners, including the real Windows rows
that match the customer environment.

---

## What went wrong, and what it taught

### A green test suite is not a green push

Five separate branches passed the full suite and were rejected at push time.
One passed 23,693 tests and failed five pre-push gates. The suite and the push
run different gate sets, so "tests pass" is evidence about tests, not about
whether the change can ship.

Acting on it: run the gate set, not just pytest, before claiming a branch is
ready. The specific commands are recorded in `.agents/governance/GOTCHAS.md`.

### The endpoint that explains a throttle reports healthy while nothing works

`gh api rate_limit` reported 4,935 of 5,000 core requests remaining while every
REST call returned 403. The limit reached was a secondary concurrency limit,
which that endpoint does not report at all. Separately, `gh pr view` and
`gh pr list` are GraphQL and fail before REST does, so the tooling that reports
health fails first under exactly the load that makes health worth checking.

### Zero in progress is an infrastructure verdict, not a repository one

A growing Actions queue with zero jobs running looked like a self-inflicted
cost stall: 64 open pull requests, and a guard I had just made unconditional
across macOS and Windows rows, where macOS bills at a 10x multiplier. That
reading was self-consistent and wrong. GitHub Actions was in a major outage.

Two destructive actions were one command away: cancelling 405 queued runs
belonging to other agents' work, and trimming coverage from a customer-facing
guard to fix a cost problem that did not exist. The status page settled it in
one call.

The general form: a quota stall throttles concurrency, it does not pin it at
zero. Confirm dispatch is happening at all before blaming your own change.

### Tests can confirm a belief instead of a behavior

The most valuable defect found this session was not in production code. The
repository-root `conftest.py` carries roughly a hundred lines of ref-trace
parsing that can never execute, because the same fixture unsets the environment
variable that trace format depends on. It survived several changes because its
tests synthesize the trace lines themselves and feed them to the parser. Those
tests prove the parser parses. They never establish that anything emits such a
line, and nothing does.

The same shape appeared four more times: an assertion on a set that is always
empty, a placeholder asserting `True`, an act rule whose predicate could never
match a single line, and an aggregate excuse that claimed a safety property it
did not implement. Each looked like coverage.

Acting on it: every non-trivial fix this session carries a negative control
verified in both directions, by reverting the fix and confirming the test goes
red. That check found two cases where my own test passed for the wrong reason.

### Adversarial review earns its cost, and must itself be verified

Sol reviewed four pull requests and produced fourteen findings. Eleven
reproduced. Three did not, and one of those three was misattributed to my
branch but turned out to be an older and worse defect: the suite injected
`commit.gpgsign=false` only when `GIT_CONFIG_COUNT` was unset, so any caller
using the indexed mechanism silently disarmed it. The Copilot CLI harness sets
that variable, so the protection had never been active on this harness and the
test guarding it reported a skip rather than a failure.

Verifying a wrong finding is what surfaced the real one. Accepting the report
would have fixed nothing; dismissing it would have missed a live gap.

### The fix that was one file over

Two defects this session were checks that existed, were tested, and never ran.
`check_unresolved_scope` was defined and covered but not called from the
closure path. A traversal checker was extracted into a new module, and the CI
paths filter still listed only the module it came from, so a change to the
checker alone would skip the job that runs it.

A check that is wired but gated off is the same defect with extra steps. Trace
the call path from the entry point rather than confirming the function exists.

---

## Process observations

**Parallel agents multiply substrate failures.** Sixteen agents exhausted the
API in minutes, and the working copy they all triaged against was 183 commits
stale, so the first full pass was against dead code. Verify the substrate before
dispatching work onto it.

**Read-only agent types cannot write.** The built-in `explore` and `research`
task types have no Bash, no session state, and no GitHub API. Sixteen agents
were told to record findings and could not, and nothing in the transcript
reported a permission error, so the loss read as agents being unhelpful rather
than unable. Recorded in GOTCHAS as a fleet trap.

**Worktrees inside the repository root cost seven scanners a workaround.** One
scan returned 1,557,567 findings. 173 worktrees were relocated and the
accumulated workarounds filed as #4702.

---

## What I would do differently

Pin adversarial review to a commit SHA. Sol's first pass reviewed a stale
snapshot and four of five High findings did not reproduce against current HEAD,
which cost a verification cycle to establish.

Check the status page before forming a hypothesis about my own change. The
outage cost roughly an hour of misdirected reasoning that one call would have
prevented.

---

## Artifacts

Eight pull requests: #4696, #4701, #4703, #4704, #4715, #4716, #4719, #4720,
plus #4721 and #4723 from delegated agents.

Serena memories written: the rate-limit endpoint under a secondary limit, the
merge-queue prerequisite, agent tests confirming belief, staged files faking a
red main, green pytest versus green push, fail-open versus fail-closed as a
blast-radius decision, queued runs with zero in progress, asking git for
`--local-env-vars` rather than hardcoding, and the lefthook job name not being
the subcommand.

Issues filed: #4689, #4690, #4691, #4692, #4698, #4702, #4706, #4709, #4717.
