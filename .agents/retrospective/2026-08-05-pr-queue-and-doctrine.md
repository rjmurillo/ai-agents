# Retrospective: Autonomous PR queue drain and Shihipar doctrine application

## Session Info

- **Date**: 2026-08-05
- **Agents**: Copilot CLI (Claude Opus 5) orchestrator, 21 background fix-cluster agents, GPT-5.6 Sol adversarial reviewer
- **Task Type**: Feature
- **Outcome**: Partial

### Provenance of figures

An adversarial pass by GPT-5.6 Sol separated the numbers here into two classes,
and this file now labels them accordingly.

**Verifiable from the repository**: the sign-test result and its eight archived
runs, `baseline_health` having no production caller, the 62 workflow files with
zero `merge_group` triggers, the 22 sites matching
`bot-pat: ${{ secrets.BOT_PAT }}`, the worktree count, and every cited memory
path. That last one needs its pattern named to reproduce: a bare grep for
`secrets.BOT_PAT` returns 56 hits across 12 files, and only the pass-through
form is 22.

**Self-reported from the session, not reconstructible from the repository**:
agent counts, issue and PR tallies, elapsed times, cycle counts, and the impact
and atomicity scores, which are judgments rather than measurements. Treat them
as attestation. The audit also corrected two false claims before publication: a
transposed `4928` for the measured `core=4948`, and the framing of
`gh api rate_limit` as an empty result when it was a falsely reassuring
non-empty one.

## Phase 0: Data Gathering

### 4-Step Debrief

**Observe.** The session applied a first-party Anthropic context-engineering
doctrine to this repository's authoring surfaces, then drained an open PR
queue. The doctrine work finished and merged. The published eval reversed its
own expected conclusion: two-tailed sign p = 0.0703125, 7 positive and 1
negative, so cutting the always-on book rules is not justified.

**Respond.** Fifty-plus PRs merged. Twenty-two-plus issues filed. Fifty-five
adversarial review rounds with a second model. One self-inflicted CI outage.

**Analyze.** Most lost time came from three repeating shapes, not from hard
problems. Each is listed under Phase 1.

**Apply.** Two memories written this session, plus two more appended. Two
issues filed for defects the session proved rather than guessed.

### Execution Trace

| Stage | Result | Cost |
|---|---|---|
| Built Copilot CLI eval provider, ran 8 variance runs | Conclusion reversed | Delivered |
| Adversarial rounds to convergence, PR #4124 | Objective complete | Delivered |
| Fleet mode, 21 parallel agents (self-reported) | PR queue drained | Delivered |
| Agent polling exhausted the shared API budget | CI went red | Outage |
| 13 pushes rejected on drift or local defects | Rework | ~3 hours |
| BOT_PAT identity traced to root cause | Issue #4607 | Delivered |

### Outcome Classification

**Glad.** The eval reversed a conclusion the session wanted. The instrument
beat the hypothesis, and the result shipped unchanged.

**Sad.** Thirteen pushes burned. Each costs 15 minutes because the pre-push
suite runs first.

**Mad.** My own polling starved CI of the API budget it needed, and CI
authenticates as the same user, so I caused the outage I then debugged.

## Phase 1: Insights Generated

### Five Whys: the 15-minute push cycle burned 13 times

1. **Why did pushes fail?** Local checks rejected them: baseline drift,
   duplicate definitions from a merge, a metrics ratchet.
2. **Why were those not caught earlier?** I ran the checks after the push
   started, not before.
3. **Why after?** The push runs them for free, so running them first felt
   redundant.
4. **Why did that reasoning hold?** I priced the check at its runtime, a few
   seconds, and ignored the cost of learning the answer late.
5. **Why did I price it that way?** A failed push and a failed local test look
   identical in the log. Only the wall clock separates them, and I was not
   measuring wall clock.

**Root cause.** I treated the pre-push suite as a checker rather than as a
15-minute serialization point. The fix is not more discipline. It is running
the three cheapest gates before the push, which takes about 20 seconds.

### Five Whys: I caused the CI outage I debugged

1. **Why did CI fail?** The GraphQL budget was exhausted.
2. **Why exhausted?** My agents polled PR state continuously.
3. **Why did that affect CI?** CI and my session share one budget.
4. **Why one budget?** `BOT_PAT` holds the human account's token, so both
   authenticate as user 6811113.
5. **Why was that not visible?** ADR-026 Decision 5 says the bot identity is
   configured, and it is. It is configured and not effective, and nothing
   checks the difference.

**Root cause.** A configured control with no test is an assumption. Filed as
issue #4607 with a runnable acceptance criterion: `gh api user --jq .id`
returns 250269933 inside CI.

### Fishbone: self-introduced defects (43 by session tally, no repo ledger)

| Category | Contributing factor |
|---|---|
| Method | Merging main without checking for add/add duplicate definitions |
| Method | Writing a patch script whose self-check was wrong, not the file |
| Measurement | Reading an empty grep as absence with no positive control |
| Measurement | Reading an empty `ls-remote` as failure with no liveness probe |
| Environment | `git worktree list` reported 174 on 2026-08-05, so stale state is the default, not the exception |
| Environment | Concurrent agents pushing, so contention stretches every cycle |

### Patterns and Shifts

The dominant pattern is one shape wearing different clothes: **a reading that
cannot separate the state I care about from a broken instrument.** Three were
ambiguous negatives: an empty grep, an empty `ls-remote`, and
`unresolved_count: 0` from a query that failed. The fourth was the mirror
image, a falsely reassuring positive: `gh api rate_limit` reported `core=4948`
of 5000 while every non-exempt call was refused, because that endpoint is
itself exempt from the limit it reports on. Four instruments, one failure mode,
two signs.

The shift that worked: pairing each negative with a positive control. That
caught two false conclusions in the final segment alone.

## Phase 2: Diagnosis

### Successes (Tag: helpful)

| Strategy | Evidence | Impact | Atomicity |
|----------|----------|--------|-----------|
| Pair every negative result with a positive control | Caught the empty `ls-remote` misread and the `merge_group` grep | 9 | 95% |
| Verify an adversarial reviewer's premise before conceding | Sol's ADR-084 rule 3 citation was wrong; rules 1 and 2 carried it | 8 | 90% |
| Search existing memories and issues before writing | Avoided two duplicate memories and ten duplicate issues | 8 | 92% |
| Publish only what was measured | Caught my own open-PR count before publishing; the listing was capped and I had counted the cap | 9 | 88% |
| Let the eval overturn the hypothesis | p = 0.0703125 shipped unchanged | 10 | 85% |

### Failures (Tag: harmful)

| Strategy | Error Type | Root Cause | Prevention | Atomicity |
|----------|------------|------------|------------|-----------|
| Push, then find out | Serialization | Priced the check at runtime, not at cycle time | Run baseline, duplicate-def, and episode gates before pushing | 93% |
| Poll PR state continuously | Resource exhaustion | Shared budget invisible in the config | Fix `BOT_PAT`; back off on 403 | 90% |
| Merge main without a duplicate check | Self-introduced defect | Add/add merges keep both copies silently | Run the duplicate tests right after every merge | 95% |
| Trust `rate_limit` remaining | Wrong instrument | Payload does not predict service | Probe a non-exempt endpoint | 88% |
| Trust a constant to be a gate | Wrong instrument | `MAX_BASELINE_SLACK` has no production caller | List callers before trusting a threshold | 91% |
| Debug a failed push from scratch | Re-derivation | Did not search memory at the moment of failure | Search `.serena/memories` on the error string first | 94% |

### Near Misses

| What Almost Failed | Recovery | Learning |
|--------------------|----------|----------|
| Re-pushing on an empty `ls-remote` | Checked the process table first | An absent ref and a pending ref are byte-identical |
| Concluding the dedupe patch corrupted the file | The script's self-check was wrong, not the file | My own fix is a hypothesis too |
| Concluding both secrets feed `bot-pat` | `grep -A1` had captured the next input line | A context flag can manufacture a correlation |
| Filing issue #4608 with a wrong mechanism | Sol caught it; corrected by comment in minutes | Publishing fast still needs the mechanism verified |
| Re-deriving the episode ratchet cause | The memory already held the full cause | Search memory on the error string before debugging |

## Phase 3: Decisions

### Action Classification

| Action | Class | Detail |
|---|---|---|
| Positive control beside every negative result | Keep | Caught two false conclusions in one segment |
| Pre-push gate trio run before pushing | Add | Baseline compare, duplicate-def tests, episode metrics |
| Continuous PR polling | Drop | It starves the shared budget |
| Trusting `rate_limit` remaining | Drop | Use the repo's own non-exempt probe |
| Adversarial review with a second model | Modify | Verify its premise, not just its conclusion |

### SMART Validation

**Pre-push gate trio.** Specific: run three named checks. Measurable: each
exits 0. Achievable: about 20 seconds total. Relevant: it addresses 13 burned
pushes. Time-bound: before every push in this repository.

**Threshold caller check.** Specific: list callers of any constant before
trusting it as a gate. Measurable: at least one caller outside `tests/`.
Achievable: one grep. Relevant: `MAX_BASELINE_SLACK` had none. Time-bound: at
the moment you cite the constant.

### Action Sequence

1. Fix `BOT_PAT` (issue #4607). Everything else gets cheaper once the budget
   stops being shared.
2. Add `merge_group` triggers before any merge queue is enabled. The set is
   every workflow emitting one of the 17 required checks in ruleset
   `11104075`, which is 12 of the 62 workflow files; none of the 62 declares
   `merge_group` today. Enabling first wedges every merge permanently.
3. Recalibrate `MAX_BASELINE_SLACK` (issue #4608), which depends on step 2.

## Phase 4: Extracted Learnings

### Learning 1

- **Statement**: A reading that cannot separate absence from failure is not evidence.
- **Atomicity Score**: 95%
- **Evidence**: grep, `ls-remote`, and a failed thread query returning
  `unresolved_count: 0` gave ambiguous empties; `gh api rate_limit` gave a
  falsely reassuring `core=4948` while every non-exempt call was refused.
- **Skill Operation**: ADD
- **Target Skill ID**: n/a

### Learning 2

- **Statement**: A threshold constant with no production caller is not a gate.
- **Atomicity Score**: 91%
- **Evidence**: `MAX_BASELINE_SLACK = 5` sits beside the ratchet, and every
  caller of `baseline_health` is a test.
- **Skill Operation**: ADD
- **Target Skill ID**: n/a

### Learning 3

- **Statement**: Run the push's own checks before the push, not during it.
- **Atomicity Score**: 93%
- **Evidence**: 13 pushes burned at 15 minutes each; the three gates that
  caught them run in about 20 seconds.
- **Skill Operation**: ADD
- **Target Skill ID**: n/a

### Learning 4

- **Statement**: A configured control with no test is an assumption.
- **Atomicity Score**: 90%
- **Evidence**: ADR-026 Decision 5 configures a bot identity that
  `gh api user --jq .id` shows is not in effect.
- **Skill Operation**: ADD
- **Target Skill ID**: n/a

### Learning 5

- **Statement**: Search memory on the error string before debugging a failure.
- **Atomicity Score**: 94%
- **Evidence**: I re-derived the episode ratchet cause from source while
  `.serena/memories/ci/episode-ratchet-trips-because-the-episode-predates-the-commit.md`
  already named `_collect_shas`, the empty `endingCommit`, and the fix.
- **Skill Operation**: ADD
- **Target Skill ID**: n/a

## Skillbook Updates

### ADD

```json
{
  "skill_id": "measurement-a-reading-needs-a-positive-control",
  "statement": "A reading that cannot separate absence from failure is not evidence.",
  "context": "Before concluding absence or health from any query, grep, or API probe.",
  "evidence": "2026-08-05: grep, ls-remote, and a failed thread query returned ambiguous empties; gh api rate_limit returned core=4948 while every non-exempt call was refused.",
  "atomicity": 95
}
```

```json
{
  "skill_id": "ci-threshold-constant-needs-a-production-caller",
  "statement": "A threshold constant with no production caller is not a gate.",
  "context": "Before citing a constant as the thing that bounds behavior.",
  "evidence": "2026-08-05: every caller of baseline_health is a test, so MAX_BASELINE_SLACK is enforced by pytest.",
  "atomicity": 91
}
```

```json
{
  "skill_id": "git-run-push-checks-before-the-push",
  "statement": "Run the push's own checks before the push, not during it.",
  "context": "In a repository whose pre-push suite takes 15 minutes.",
  "evidence": "2026-08-05: 13 pushes burned; the catching gates run in about 20 seconds.",
  "atomicity": 93
}
```

```json
{
  "skill_id": "memory-search-the-error-string-before-debugging",
  "statement": "Search memory on the error string before debugging a failure.",
  "context": "The moment a push, hook, or CI job fails with a named assertion.",
  "evidence": "2026-08-05: re-derived the episode ratchet cause that ci/episode-ratchet-trips-because-the-episode-predates-the-commit.md already documented in full.",
  "atomicity": 94
}
```

```json
{
  "skill_id": "governance-a-configured-control-needs-a-test",
  "statement": "A configured control with no test is an assumption.",
  "context": "When an ADR or config claims an identity, boundary, or isolation holds.",
  "evidence": "2026-08-05: ADR-026 Decision 5 configures a bot identity that gh api user --jq .id shows is not in effect. Issue #4607.",
  "atomicity": 90
}
```

### UPDATE

| Skill ID | Current | Proposed | Why |
|----------|---------|----------|-----|
| git-empty-hook-run-means-an-empty-push | Covers a push that finishes too fast | Also covers a push that has not finished | The two are opposite reads of one instrument |

### TAG

| Skill ID | Tag | Evidence | Impact |
|----------|-----|----------|--------|
| ci/github-rate-limit-payload-does-not-predict-service | confirmed | A repeat confirmation is already recorded in the memory at line 258, written 2026-08-05. No edit needed. | High |

### REMOVE

| Skill ID | Reason | Evidence |
|----------|--------|----------|
| n/a | No learning was invalidated this session | n/a |

## Deduplication Check

| New Skill | Most Similar | Similarity | Decision |
|-----------|--------------|------------|----------|
| measurement-a-reading-needs-a-positive-control | ci-a-truncated-job-log-greps-exactly-like-a-clean-one | High | Keep both; that one is log-specific, this one is general |
| ci-threshold-constant-needs-a-production-caller | ci-count-ratchets-require-branch-freshness | Low | Keep; different failure |
| git-run-push-checks-before-the-push | git-rebase-after-push-costs-two-cycles | Medium | Keep; that one is about rebase, this about check ordering |
| memory-search-the-error-string-before-debugging | episode-ratchet-trips-because-the-episode-predates-the-commit | Low | Keep; that one is the answer, this is the habit of looking |
| governance-a-configured-control-needs-a-test | ci/github-rate-limit-payload-does-not-predict-service | Medium | Keep; that one is one instance, this is the general rule |
