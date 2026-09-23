# Retrospective: Shipping a fix the issue tracker had already rejected

## Session Info

- **Date**: 2026-08-02
- **Agents**: orchestrator (this session), pytestred, cimisc2, plus 17 fleet agents
- **Task Type**: Bug
- **Outcome**: Partial

## Phase 0: Data Gathering

### 4-Step Debrief

**Observe.** `origin/main` failed the taste count ratchet at 602 violations against a
baseline of 601. The taste ratchet runs in the pre-push lefthook group, so every branch in
the repository was push-blocked. Four PRs were failing `Run Python Tests` on the inherited
failure.

**Respond.** I ran the red-main diagnostic, confirmed the failure on a pristine probe
worktree, bisected the plus-one to `scripts/validation/pre_pr_sequence.py`, identified
PR \#4272 as the source, then designed and shipped an extraction: 57 lines moved into a new
`pre_pr_sequence_fast.py`, taking the module from 512 lines to 455.

**Analyze.** The extraction was the wrong fix. Issue \#4285 was already open, and its title
reads: "pre_pr_sequence.py is a registration list measured by a complexity ceiling;
extraction only resets the counter." That is a verbatim description of what I built. I never
searched the issue tracker for the file before designing the fix.

**Apply.** Closed PR \#4302 with a written justification. Took \#4285 to do the fix that
actually addresses the defect, a table-driven registry, and handed my supporting
measurements to the agent that owns the adjacent issue.

### Execution Trace

| Time | Event | Evidence |
|------|-------|----------|
| T0 | Red-main diagnostic on pristine probe worktree | `taste count ratchet: REGRESSION 602 > 601` |
| T0+4m | Per-file bisection between `aea3a49cd` and main | `pre_pr_sequence.py` 0 errors to 1 |
| T0+6m | Root cause identified as PR \#4272 | file at 512 lines, ceiling 500 |
| T0+10m | Design decision: extraction over suppression | applied code-quality "suppressions are a last resort" |
| T0+35m | Extraction built, 2 guard tests written, mutation-proved | 124 tests pass, 3 ratchets green |
| T0+50m | Push completes | `python-tests` 839s, `taste-count-ratchet` 2.26s |
| T0+52m | PR \#4302 opened | |
| T0+53m | Discovered main already green | PR \#4290 merged the suppression at 17:43:29Z |
| T0+55m | Discovered issue \#4285 | title describes my fix's failure mode exactly |
| T0+58m | PR \#4302 closed with justification | |

### Outcome Classification

**Glad.** The red-main diagnostic worked and two independent investigations (mine and
`pytestred`'s) reached the same root cause. The fleet broadcast reached 19 agents before
they each burned 15-minute push cycles into a known-red main. Mutation testing caught a
tautological test I wrote. Widening a sample from 100 to 500 runs caught a measurement
artifact before it reached an issue comment.

**Sad.** Roughly 50 minutes of design and build plus a 14-minute push cycle produced a PR I
closed myself. `pytestred`, one of my own agents, had already shipped the correct stopgap
while I was building the wrong permanent fix.

**Mad.** The information that would have redirected me was one `gh issue list` away and had
been open the entire time.

## Phase 1: Insights Generated

### Five Whys

1. **Why did I ship a fix I then closed?** I chose extraction over suppression on the
   principle that suppressions are a last resort.
2. **Why did that principle mislead me?** It assumes the idiomatic fix reduces the
   underlying problem. Here extraction relocates it: `run_all_validations` is a 408-line
   function before and roughly 350 after, and the repo-wide count is unchanged because the
   lines moved rather than disappeared.
3. **Why did I not know extraction was hollow here?** I never checked whether the repository
   had already reasoned about this specific file. Issue \#4285 had.
4. **Why did I not check?** I treated a repository-wide push block as an emergency that
   justified skipping the search step, and I had already root-caused the failure to a
   specific file, which felt like sufficient understanding to act.
5. **Why did root-causing feel sufficient?** Because I conflated diagnosing the cause with
   knowing the remedy. Bisection told me *which* file crossed the ceiling. It said nothing
   about *why* that file is long, or whether a file-size ceiling is the right measure for a
   flat registration list. I acted on cause-knowledge as though it were remedy-knowledge.

**Root cause:** urgency suppressed the search step, and confidence from a clean root-cause
bisection masked the omission. Search Before Building has no urgency carve-out, but I
applied one implicitly.

### Fishbone

| Category | Contributing factor |
|----------|--------------------|
| Method | Root-cause bisection produced high confidence, which substituted for remedy research |
| Method | No step in my sequence asked "has this file been discussed before" |
| Environment | A repository-wide push block created real time pressure |
| Environment | 19 parallel agents meant a duplicate fix was likely and I did not check for one |
| Measurement | The taste ceiling is a proxy for complexity and misreports on registration lists |
| People | I hold the code-quality rule strongly enough to apply it without checking its fit |

### Patterns and Shifts

This is the same shape as the session's other overturns, but pointed inward. All session
long I have re-measured other people's premises before acting on them, 135 times now. I did
not apply that discipline to my own remedy choice. The premise "the idiomatic fix is
extraction" went unmeasured, and it was false.

## Phase 2: Diagnosis

### Successes (Tag: helpful)

| Strategy | Evidence | Impact | Atomicity |
|----------|----------|--------|-----------|
| Red-main diagnostic on a pristine probe worktree | Confirmed 602 vs 601 on untouched `origin/main`; two agents converged independently | 9 | 95% |
| Broadcast the finding to the whole fleet before fixing it | 19 agents told not to absorb the failure or retry pushes; `pytestred` closed its duplicate PR \#4297 on receipt | 8 | 92% |
| Mutation-prove every new test before trusting it | Reorder mutant caught by pre-existing test; membership mutant caught only by the new ones | 9 | 94% |
| Widen a sample when the conclusion is load-bearing | 100-run sample said 2.6min critical path; 500-run sample said 13.5min and reversed the verdict | 9 | 92% |
| Apply the same triage standard to my own PR as to others' issues | Closed \#4302 within 5 minutes of the disconfirming evidence | 8 | 90% |

### Failures (Tag: harmful)

| Strategy | Error Type | Root Cause | Prevention | Atomicity |
|----------|------------|------------|------------|-----------|
| Designed the remedy straight off the bisection result | Skipped research | Cause-knowledge mistaken for remedy-knowledge | Search issues for the target file before designing, not after | 95% |
| Applied "suppressions are a last resort" without checking its fit | Rule misapplication | The rule assumes the idiomatic fix reduces the problem; extraction relocated it | Ask what the rule is a proxy for before applying its remediation | 90% |
| Did not check whether a fleet agent was already fixing it | Coordination gap | 19 parallel agents, no duplicate-work check before starting | Check open PRs touching the file before starting a fix | 88% |

### Near Misses

| What Almost Failed | Recovery | Learning |
|--------------------|----------|----------|
| Nearly filed that strict base-currency is viable, based on a 100-run CI sample showing a 2.6 minute critical path | Widened to 500 runs across 5 pages; real critical path is 13.5 minutes and the verdict inverted to gridlock | Filtering runs by `status=completed` over a recent window structurally excludes slow workflows, because slow runs are disproportionately still in progress |
| Wrote `test_moving_a_fast_gate_later_is_detected` deriving its expected value from the same production source it compared against | Ran a real mutant; the test passed it, exposing the tautology; replaced with a pinned membership list | An expectation must come from a different authority than the code under test, regardless of whether it is hard-coded or read from source |

## Phase 3: Decisions

### Action Classification

| Class | Action |
|-------|--------|
| Keep | Red-main diagnostic on a pristine probe before attributing any failure |
| Keep | Mutation-proving every new guard test against a plausible mutant |
| Keep | Fleet-wide broadcast the moment a shared blocker is confirmed |
| Add | Search the issue tracker for the target file before designing a fix |
| Add | Check open PRs touching the file before starting, when a parallel fleet is running |
| Modify | Treat a clean root-cause bisection as the start of remedy research, not the end |
| Drop | Applying a code-quality rule's remediation without first asking what the rule proxies for |

### SMART Validation

| Learning | Specific | Measurable | Achievable | Relevant | Time-bound |
|----------|----------|------------|------------|----------|-----------|
| Search issues for the target file before designing | Yes, names `gh issue list` and the file path | Yes, the search either ran or did not | Yes, one command, under 10 seconds | Yes, would have prevented 64 minutes of waste | Yes, before design begins |
| Cause-knowledge is not remedy-knowledge | Yes, names the bisection-to-design transition | Yes, did a remedy-research step occur | Yes | Yes | Yes, at the design step |
| Recent-N completed run samples exclude slow workflows | Yes, names the API filter and the mechanism | Yes, 2.6min versus 13.5min, 5x understatement | Yes, paginate to 500 | Yes, one issue comment avoided | Yes, at measurement time |
| An expectation must come from a different authority | Yes, names the two failing shapes | Yes, mutant survives or dies | Yes | Yes | Yes, before trusting a test |

### Action Sequence

1. Close PR \#4302 with justification. **Done.**
2. Hand the \#4057 measurements to the owning agent. **Done.**
3. Persist the learnings below to memory. **Phase 5.**
4. Do the real fix for \#4285, a table-driven registry, which also removes the need for the
   suppression PR \#4290 added.

## Phase 4: Extracted Learnings

### Learning 1

- **Statement**: Search open issues for the target file before designing a fix, even under P0.
- **Atomicity Score**: 95%
- **Evidence**: Issue \#4285's title described the failure mode of the fix I built; 64 minutes lost to design, build, and a 14-minute push cycle on PR \#4302, closed by me.
- **Skill Operation**: ADD
- **Target Skill ID**: n/a

### Learning 2

- **Statement**: Root-cause bisection names the cause, never the remedy.
- **Atomicity Score**: 90%
- **Evidence**: Bisection correctly named `pre_pr_sequence.py` as the file that crossed the 500-line taste ceiling, and said nothing about the file being a 48-entry registration list whose length is not a complexity signal.
- **Skill Operation**: ADD
- **Target Skill ID**: n/a

### Learning 3

- **Statement**: Recent-N completed GitHub run samples exclude slow workflows, understating CI critical path 5x.
- **Atomicity Score**: 92%
- **Evidence**: A 100-run `status=completed` sample reported a 2.6 minute critical path and implied strict base-currency was viable. A 500-run sample across 5 pages reported 13.5 minutes p50 and inverted the verdict to gridlock, because `Python Tests` and `AI PR Quality Gate` never appeared in the smaller window.
- **Skill Operation**: ADD
- **Target Skill ID**: n/a

### Learning 4

- **Statement**: A test expectation must come from a different authority than the code under test.
- **Atomicity Score**: 92%
- **Evidence**: `test_moving_a_fast_gate_later_is_detected` read its expected gate list from production source via `inspect.getsource`, so a reorder moved both sides together and the mutant survived. This is the self-referential anti-pattern wearing the opposite costume: the existing memory's example failed by hard-coding, mine failed by not hard-coding.
- **Skill Operation**: UPDATE
- **Target Skill ID**: feedback-self-referential-test-anti-pattern

## Skillbook Updates

### ADD

```json
{
  "skill_id": "research-search-issues-before-designing-fix",
  "statement": "Search open issues for the target file before designing a fix, even under P0.",
  "context": "Any bug fix, immediately after root-causing and before choosing a remedy. Highest value when a parallel agent fleet is running or the file has a history of contested changes.",
  "evidence": "Session 2026-08-02: issue #4285's title described the failure mode of PR #4302 before it was written; 64 minutes lost.",
  "atomicity": 95
}
```

```json
{
  "skill_id": "diagnosis-cause-is-not-remedy",
  "statement": "Root-cause bisection names the cause, never the remedy.",
  "context": "At the transition from diagnosis to design. Applies when a gate, ratchet, or lint identifies a file: ask what the rule is a proxy for before applying its prescribed remediation.",
  "evidence": "Session 2026-08-02: bisection correctly named pre_pr_sequence.py at 512 lines over a 500-line ceiling; the file is a 48-entry registration list whose length is not a complexity signal, so the prescribed extraction relocated 57 lines without simplifying anything.",
  "atomicity": 90
}
```

```json
{
  "skill_id": "measurement-recent-n-censors-slow-runs",
  "statement": "Recent-N completed GitHub run samples exclude slow workflows, understating CI critical path 5x.",
  "context": "Any measurement of CI duration, queue depth, or workflow cost via the Actions runs API with a status filter. Paginate to at least 500 runs.",
  "evidence": "Session 2026-08-02: 100-run sample reported 2.6 min critical path; 500-run sample reported 13.5 min p50 and reversed a policy verdict from viable to gridlock.",
  "atomicity": 92
}
```

### UPDATE

| Skill ID | Current | Proposed | Why |
|----------|---------|----------|-----|
| feedback-self-referential-test-anti-pattern | Frames the anti-pattern as asserting on a generator's own output, with hard-coding the expectation as the implied contrast | Add the inverse shape: reading the expectation from production source at runtime is the same defect. The invariant is that the expectation comes from a different authority, not that it is or is not hard-coded | The existing example fails by hard-coding a string the generator also produces. Mine failed by refusing to hard-code and reading from source instead. Both halves came from one authority in both cases, so a reader applying the current memory's implied fix ("hard-code it") could reproduce my defect in reverse |

### TAG

| Skill ID | Tag | Evidence | Impact |
|----------|-----|----------|--------|
| knowledge/chestertons-fence | helpful | The fence here was the file's length; the sign explaining it was issue \#4285, which I did not read before removing the fence | Confirms the principle and extends its search surface from memory to the issue tracker |

### REMOVE

| Skill ID | Reason | Evidence |
|----------|--------|----------|
| n/a | | |

## Deduplication Check

| New Skill | Most Similar | Similarity | Decision |
|-----------|--------------|------------|----------|
| research-search-issues-before-designing-fix | knowledge/chestertons-fence | High on principle, low on surface. The existing memory says search *memory* before changing code; it never names the issue tracker, and the issue tracker is where this fence's sign was posted | ADD as new, cross-reference chestertons-fence |
| diagnosis-cause-is-not-remedy | knowledge/chestertons-fence | Moderate. Chesterton asks why the fence exists; this asks what the measuring rule is a proxy for. Related but distinct failure modes | ADD as new |
| measurement-recent-n-censors-slow-runs | decision-calibrate-guards-on-the-whole-corpus | Moderate. That memory covers self-selection bias, sampling from a guard's own hits. Mine is censoring: a filter that correlates with the quantity being measured. Different mechanism, same family | ADD as new, cross-reference |
| test-expectation-different-authority | feedback-self-referential-test-anti-pattern | Very high. Same defect, opposite surface | UPDATE the existing memory rather than adding a fourth near-duplicate |
