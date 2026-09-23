# Measure Before Asserting: 82 Overturned Premises in One Session

Date: 2026-07-29
Failure mode: Class 9, confident-incorrectness recurrence
(`.agents/governance/FAILURE-MODES.md`). Secondary: Class 10, silent defaults
and guard-clause suppression.

## Summary

A single autopilot session worked the open issue queue in `rjmurillo/ai-agents`.
Every stated premise was re-measured before it was acted on. Measurement
overturned the written claim 82 times. The claims came from issue bodies, from
bot and human review comments, from my own earlier conclusions in the same
session, and from tests I had written myself. The overturn rate is the finding.
Prose in this repository is not evidence, and that includes prose I wrote an
hour earlier.

## Impact

| Area | Severity | Effect |
|------|----------|--------|
| Issue queue accuracy | High | 21 open issues described problems that no longer existed or never did. Each was closed with a measurement, not an opinion. |
| Fix correctness | High | Acting on unverified issue text would have shipped wrong fixes. Issue #3649 said 4 violations; the real count was 71 across 44 files. Issue #3742 blamed data loss; byte counts were identical and the real defect was ordering. |
| Review-thread cost | Medium | Four reviewer-stated API contracts were wrong when measured. One of my own replacements was also wrong, and one reply I posted was wrong and needed a public correction. |
| Test trust | High | Four tests in PR #3688 parsed, collected, and silently never ran. A monkeypatched subprocess fake encoded a false git exit-code contract, twice. |
| CI throughput | Medium | Each wrong premise that reached a push cost a 6 to 15 minute gate cycle. |

## Timeline

1. Issue text taken at face value would have produced a 4-file fix for #3649.
   Scanning found 71 violations across 44 files. Shipped as PR #3762.
2. Issue #3742 attributed interleaved output to lost data. Byte counts before
   and after were identical, so the defect is reordering. Shipped as PR #3799
   with the causal story corrected in the commit body.
3. A reviewer on PR #3824 stated that `git cat-file -e` returns 1 for a missing
   path and 128 for a fatal error. Measured on git 2.43.0: inverted. My own
   `git rev-parse --verify --quiet` replacement was then refuted by my own
   tests. A four-path probe showed `git ls-tree` is the only discriminator. The
   reviewer's conclusion (the check fails open) was correct through a mechanism
   neither of us had named.
4. A reviewer on PR #3778 said `_confirm_ignored` could raise
   `UnicodeDecodeError` at `.decode()`. Measured: it raises `UnicodeEncodeError`
   at `payload.encode()`, one call earlier, before git is spawned, where
   `except OSError` does not catch it.
5. A reviewer on PR #3780 said `tree_root.name` drops parent components for
   three trees. Measured: all six `AGENT_TREES` entries are wrong, and four of
   them collapse to the same ambiguous final component.
6. I posted a claim on PR #3820 that the session validator accepts an empty
   `endingCommit` unconditionally. Re-measured: the rule is already on `main`,
   fires correctly, and lands in `result.warnings`. The defect is the severity,
   not the absence. I posted a public correction.
7. My own PR #3858 patch reopened the race it was closing. An empirical probe
   proved it. Two directional regression tests now hold both ends.
8. Three of my own theories were refuted by data and abandoned: a CI merge
   deadlock, a queue-starvation attribution, and the claim that unresolved
   review threads block merges.

## Root Cause

Five whys.

1. Why did 82 premises need overturning? Because they were written as
   conclusions without an attached measurement.
2. Why were they written that way? Because the cost of asserting is one
   sentence and the cost of measuring is a scratch repository and a probe.
3. Why is the cost asymmetric? Because no gate requires a measurement to
   accompany a claim in an issue body or a review comment.
4. Why does that matter more here than elsewhere? Because agents read issue
   text as instructions. A wrong premise in an issue becomes a wrong fix in a
   PR without a human in the path.
5. Why was that not caught earlier? Because a fix that matches the issue text
   looks correct in review. Nothing compares the issue's claim against the
   repository.

Root cause: this repository treats written claims as evidence. Agents and
reviewers both assert exit codes, counts, and API contracts from memory, and
nothing in the pipeline demands the measurement that would falsify them.

## What Worked

- Re-measuring every premise before acting on it. This is the whole finding.
- Mutation harnesses on every fix. A surviving mutant caught an unwired
  component in PR #3836 and an uncovered git-launch path in PR #3824.
- Isolating negative controls proving each new component is load-bearing.
- Public corrections when my own posted reply was wrong. Two this session.

## What Did Not Work

- Trusting a monkeypatched subprocess fake to encode a real exit-code contract.
  It silently encoded a false one twice, in `_fake_scan` and in
  `test_confirm_ignored_survives_non_utf8_paths`.
- Assuming an indentation problem from a symptom. Pytest collects nested test
  classes; the four dead tests in PR #3688 parsed cleanly and never ran.
- Assuming `rc=$?` after a pipe captures the Python exit code. It captures the
  last stage. One measurement was wrong for exactly that reason.

## Remediation

| Action | Owner | Tracking |
|--------|-------|----------|
| Ratchet taste-lint error counts so debt cannot grow | shipped | PR #3824, issue #3779 |
| Guard against escaped-newline PR bodies | shipped | PR #3798, issue #3777 |
| Flush stdout before fd-inheriting spawns | shipped | PR #3799, issue #3742 |
| Backstop conflict markers in CI | shipped | PR #3820, issue #3770 |
| Name the full tree path in nested-agent guidance | shipped | PR #3780 |
| Merged PRs silently fail to close linked issues | open | issue #3827 |
| 490 dead `noqa` directives repo-wide | open | issue #3792 |
| Word-boundary gap class, 29 sites and 21 latent | open | issue #3877 |
| Session-log required items declaring no `level` key | open | issue #3763 |
| File the ref-lock push race that wastes a full gate cycle | not filed | see Follow-Ups |

## Follow-Ups Not Yet Filed

1. The push ref-lock race. `cannot lock ref ... is at X but expected Y` fires
   after every gate has passed, because the bot pushes to human feature
   branches mid-flight. Cost is one full 6 to 15 minute cycle per occurrence.
2. The `endingCommit` contradiction in `scripts/validation/validate_session_json.py`
   is demoted to a warning, so the process exits 0 and prints a pass banner on
   the line above the finding.
3. The taste-lint ratchet baseline is a moving target. `main` drifted 615 to 616
   inside this session, which makes any ratchet PR red on arrival.
4. A monkeypatched subprocess fake can encode a false exit-code contract with no
   signal. Seen twice this session. Fakes that model an external tool should be
   pinned by at least one test against the real tool.

## Learning

A claim without a measurement is a hypothesis, and this repository currently
files hypotheses as issues and posts them as review comments. The cheapest
durable fix is cultural and already partly encoded: when an issue or a review
comment states an exit code, a count, or an API contract, measure it before
acting. Four reviewer claims, one of my own replacements, and one of my own
posted replies were wrong this session. The measurement took minutes. The wrong
fix would have taken a cycle each and shipped a defect.

Applies equally to my own prior conclusions. Three theories I authored were
refuted by data in the same session that produced them.
