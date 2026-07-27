---
id: ADR-087
status: proposed
date: 2026-07-26
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: false
---

# ADR-087: Held-Out Validation for Iterated Improvement Claims

## Status

Proposed. Requested by two independent adversarial reviews on PR #3430
(gpt-5.6-sol and gemini-3.1-pro-preview), both of which concluded that the
mechanism that PR adds asserts a norm the repository has not written down.

A second adversarial round reviewed the resulting draft and returned REJECT.
It was right on the substance: the draft mischaracterized ADR-057, cited two
`proposed` ADRs as authority, overstated what the mechanism guarantees across a
loop, and claimed an enforcement property the code did not yet have. This
revision corrects each of those and adds an Open Requirements section naming
what still blocks acceptance. The document now describes a mechanism and its
limits rather than asserting a norm. Refs #3422.

## Date

2026-07-26

## Context

This repository evaluates three kinds of authored artifact empirically. Each
has its own methodology ADR and its own evaluator:

| Artifact | Evaluator | ADR |
|----------|-----------|-----|
| Prompt or rule | `eval-prompt-change.py`, `eval-rule-activation.py` | ADR-057 |
| Agent | `eval-agent-vs-baseline.py` | ADR-058 |
| Hook | `pytest tests/hooks` | Testing rigor, not an ADR |

All three answer the same question: did this edit make the artifact better.
All three answer it the same way, and that way has a defect that none of them
name.

The evaluator scores the artifact against the whole evaluation set. The author
reads which cases failed. The author edits the artifact. The evaluator scores
it against the same whole set again. Repeat until the number goes up.

That is fitting the test set. After the second iteration the reported score is
no longer an estimate of how the artifact behaves on cases it has not seen; it
is an estimate of how well the author responded to the specific cases in the
set. The two diverge exactly as the loop gets more effective, which is the
worst possible direction for the error to run.

Verified rather than asserted, and stated precisely because two drafts
overstated it in turn. None of the artifact evaluators that predate this ADR
performs a *pre-registered withholding*. `eval-agent-vs-baseline.py` loads
fixtures at lines 1095-1115 via `_load_fixture_paths` then `validate_fixtures`,
with no split. The same is true of `eval-prompt-change.py`.

Two narrower corrections, both from review. It is not true that no evaluator
subsets at all: `_report_aggregator.py` lines 406-422 drop flaky fixtures and
compute the headline delta on the surviving `stable_ids`, which
`eval-agent-vs-baseline.py` then reports (its own lines 1046-1062 only warn
that the threshold was crossed). That is a post-hoc exclusion chosen after
seeing which tasks misbehaved, the opposite of what this ADR asks for, and it
does not weaken the case. And the claim is now false of the directory as a
whole, because `optimize-artifact.py` from this ADR withholds by construction.

Two merged commits already ran this loop and said so in their messages,
marked `(SkillOpt-gated)`, #3056 and #3057. They went through an out-of-repo
harness in a dotfiles repository, they applied only to skills, and the
repository has no record of what was held out or whether anything was. The
practice arrived before the policy, which is the ordinary order and the reason
to write the policy now.

### What the existing ADRs do and do not cover

ADR-010 caps an evaluator-optimizer loop at three iterations and terminates on
a rubric score of 70% or above. It bounds how long the loop runs. It says
nothing about what evidence the loop is allowed to see, so three iterations
against a fully-visible set is fully compliant and fully overfit.

ADR-057 requires that a prompt change "must not degrade existing behavior
without explicit justification," and its gate is stricter than that sentence
reads: "Every pass-to-fail flip is recorded in `regressions` and blocks the
gate automatically; the gate has no mechanism to accept a 'justified'
regression." An earlier draft of this ADR claimed ADR-057 enforced only an
aggregate mean. That was false, and the error mattered: it was used here to
justify an override flag that would have been a weaker rule shipping under the
same name. The flag is gone and requirement 4 below now restates ADR-057's
no-bypass position rather than relaxing it.

What ADR-057 does not cover is iteration. Its gate reads the whole scenario
set, which is also the set the author reads while editing. It stops a
regression on a task the author can see. It says nothing about whether the
aggregate gain generalizes past the tasks the author was looking at.

ADR-058 is between-subjects, agent against baseline. It is the right shape for
"is this agent better than no agent" and the wrong shape for "is revision 7 of
this agent better than revision 6," which is the question an improvement loop
asks on every step. ADR-058 is itself `proposed`, so it is cited here as the
existing shape of the practice rather than as settled authority.

ADR-022's split criteria are the reason this is filed as an ADR: it constrains
what the evaluation machinery is structurally allowed to observe at decision
time, and it changes the shape of every future evaluator, rather than adding a
compliance step to an existing one. Two caveats a reader deserves. ADR-022 is
also `proposed`. And its own matrix calls for an ADR *plus* a governance
document when a decision carries an enforcement obligation, which this one
does. The governance half is not written; that gap is named under Open
Requirements below rather than papered over.

### Why this is not solved by discipline

The obvious alternative is to write the norm as guidance and expect authors to
follow it. Two reasons that fails here.

First, the party being disciplined is increasingly not a human. An agent
iterating unattended will optimize whatever number it is shown. If it is shown
a score computed on data it can read, it will fit that data, and it will do so
faster and more thoroughly than a human would.

Second, the task set is a directory the agent can write to. Guidance that says
"hold out a portion" is satisfiable by holding out a portion, losing, and
choosing a different portion. The hold-out has to be tamper-evident to mean
anything, and tamper-evidence is a mechanism, not a norm.

## Decision

**An improvement claim about an authored artifact, made by a loop that reads
its own evaluation results, MUST be validated against a group whose number of
consultations is bounded and counted by a mechanism the loop cannot move
through its own arguments.**

The stronger statement, that validation happens on tasks withheld from the
party making the edit, is what this ADR originally asserted. A sixth review
falsified it against the implementation, and the falsification is recorded in
Consequences. Withholding is the goal; a counted budget is what the current
mechanism delivers, and it is what the requirements below can honestly
demand.

Five requirements follow. They are numbered 1 through 5 and are referred to
elsewhere in this document as Decision Requirement 1 through Decision
Requirement 5, to keep them distinct from the separately numbered list under
Open Requirements.

### 1. The decision group is fixed before the first edit

The evaluation set is split into an optimize group, a selection group, and
optionally a test group. The author, human or agent, may read results on the
optimize group. The accept decision reads the selection group and nothing else.
The test group, when present, is read once at the end and never gates. That
lifecycle is stated, not yet enforced: `--test-ratio` defaults to `0.0` and no
command reveals the group, so the one-time read is an open requirement below
rather than a property of the code.

The split is committed before the first edit. It is not re-drawn because a
candidate lost.

### 2. The split is tamper-evident

The split is fingerprinted over the seed, the full task-id set, and the group
ratios. A decision made against a fingerprint that does not match the recorded
one is refused rather than computed.

This closes the cheapest available cheat, which is also the ordinary accident:
an edit loses, so tasks are added and the split is re-drawn, and the new split
happens to be kinder.

### 3. Repeated decisions against one held-out group are budgeted

Each accept decision against a selection group is a selection event on that
group. Enough of them and the selection group is an optimize group that nobody
labelled. The number of decisions is capped, and the count, the cap, and the
file they live in are held by the mechanism rather than re-derived from what the
caller passed.

The distinction is not pedantic, and it took five rounds to get right. Each
round fixed the part under review and left the rest reachable, where the same
defect reappeared in a new form:

| Round | What the caller still controlled | How review defeated it |
| --- | --- | --- |
| 1 | The count | `--consultations` defaulted to zero on every invocation. Two accepts reproduced under a cap of one by passing zero twice. |
| 2 | The cap | `--max-consultations` defaulted to unlimited, so the ordinary invocation had no budget, and a caller that hit the cap could raise it on the next call. |
| 3 | The ledger path | A missing ledger starts at zero, so `--ledger` pointed at a fresh path restored the whole budget without editing anything. |
| 4 | The split path the ledger was derived from | Deriving the ledger from `--split` moved the reset instead of closing it. Copying `split.json` to `split2.json` kept the fingerprint and left no ledger beside it, so the budget started over. |
| 5 | The inputs the fingerprint covers | Keying on the fingerprint keyed on the selection's inputs (seed, task ids, ratios) rather than its result, and group sizes round. Ten tasks at `--sel-ratio 0.40` and at `0.41` hold out the same four tasks and fingerprint differently, so one held-out group had two budgets. |

| 6 | The digest of the group, reachable from any I/O failure under the ledger root | Round five redacted three hand-written messages. Every other way to fail on a ledger path, a malformed ledger, a write that cannot land, an `os.open` failing for any errno but EEXIST, still printed the filename, and the filename ends in the digest. |

What holds now: the cap is required and recorded at the first decision, a later
cap change is refused, and the ledger is keyed by a digest of the sorted
held-out membership in a fixed state directory. A copy, a rename, or a differently
parameterized redraw that lands on the same tasks all share the budget those
tasks have already spent. The general rule this ADR extracts is that any part of
a budget the caller can restate, or can move by renaming something else, is not
part of the budget, and that the key has to name what is being spent rather than
what produced it.

Keying on membership deliberately has no corpus namespace. Two unrelated eval
sets whose task ids and held-out membership both coincide will share a budget.
The seam between this loop and its scorers carries task ids and pass booleans
and nothing else, so there is no corpus identity in it that the caller did not
supply, and a caller-supplied key is the defect this round closed. A namespace
derived from task contents or from trusted corpus provenance would work; it
needs a seam that carries one. Sharing is the conservative direction, so the
collision is accepted until that seam exists.

Decision Requirement 5 put a corpus identity into the seam, and the ledger key
deliberately does not use it. Adding it would split budgets rather than merge
them, and a caller who strips the envelope back to a bare mapping would land on
a different key with the same held-out tasks. That is a budget reset reachable
by editing an input, which is the defect rounds one through five closed five
times. The key stays keyed on membership alone: over-sharing a budget is safe,
resetting one is not. That same strip is refused at the gate instead, which is
the right layer for it: a refusal belongs where the comparison is decided, not
in the name of the file that counts it.

The key is a digest, and a digest of a set the caller can enumerate is that
set. It is therefore kept out of error output. A fifth round found it in three
hand-written lock and ledger messages; a sixth found the three fixes had missed
every generic I/O failure under the ledger root, since those interpolate the
filename and the filename ends in the digest. The scrub now sits at the seam
rather than at each call site, so paths added later inherit it. The redaction
is bookkeeping hygiene, not a boundary: as the next section records, membership
is recoverable by subtraction regardless.

The cap itself is still whatever positive integer the first call names. Nothing
constrains a first invocation that passes a thousand. That is operator policy,
and inventing a ceiling here would be a number with no evidence behind it; it is
listed under Open Requirements instead.

`$EVAL_LEDGER_DIR` relocates the ledger root. It exists so tests do not write to
a real user state directory, and it reopens the reset for anyone who sets it.
Naming it here is deliberate: it is an escape hatch, not a closure.

A consultation is charged before any held-out coverage or outcome is queried,
not when a verdict comes back. The split file is opened and its membership
hashed before that point, which is how the ledger is found at all; what the
charge precedes is every question whose answer depends on held-out results. A refusal decidable from bookkeeping alone (exhausted budget, stale
incumbent fingerprint, drifted split) reads nothing and costs nothing. Anything
past that point costs one, including a results file that turns out not to cover
the group and a process killed mid-comparison. An earlier version wrote the
count after the verdict, which made both of those free. Two gates running at
once cannot both spend the same remaining consultation, because the read, the
comparison, and the write happen under an exclusive lock keyed by the same
held-out group.

The gate also never names a held-out task. `score` and `mcnemar_exact` report
which ids they could not find, which is the right message for direct scoring and
a full disclosure inside the gate, where those ids are the withheld ones. A
candidate results file with no keys at all printed the entire membership in one
error. The gate now asks its own coverage question and answers that question
with one bit. (The *decision* payload is not one bit; see Consequences. This
paragraph is about the coverage predicate alone, and #3452 proposes replacing
even that with a whole-universe check, which removes the membership oracle it
still constitutes.) Not a count: `split` publishes the held-out size, so a count would tell a caller how
many of the keys it chose to omit were held out, and a few chosen omissions
recover the membership.

### 4. No pass-to-fail transition is accepted on an aggregate gain

The decision counts discordant pairs: tasks that went fail-to-pass and tasks
that went pass-to-fail. Any pass-to-fail transition refuses the edit, whatever
the aggregate did.

There is no override. This restates ADR-057's position rather than extending
it; that ADR already states its gate "has no mechanism to accept a 'justified'
regression." An earlier draft of this ADR provided an opt-out flag, described
as something a human would pass. It was not human-only, nothing distinguished a
human caller from the agent driving the loop, and it would have been a weaker
rule than the ADR it claimed to source from. It has been removed.

### 5. A comparison whose corpus is not pinned and agreed is refused

`split` records the corpus of the results it was drawn from, and both results
files declare the corpus they were scored against. When the three do not name
one corpus, the comparison is refused before the ledger is touched: it would
measure the corpus change alongside the edit.

This requirement exists because the omission had already cost something. On
2026-07-27 two runs of the same agent were gated against each other and read as
a null control. They agreed on `model_id` and on `agent_prompt_sha` and
disagreed on `fixture_set_sha`; all eight fixture files had changed between
them. The accept was published across four files before the mismatch was found.
The retraction is in Validation Status.

Six properties, each answering a specific failure the earlier rounds taught:

- **The refusal is free and cannot be masked.** It is decidable from three
  header fields, so it sits beside the split-drift refusal and ahead of the
  ledger. A mismatched pair is unusable at any budget, so charging for it would
  sell a consultation that can never be spent, and ordering it behind the budget
  check would tell an operator to buy budget for a comparison that can never be
  valid. This is the same ordering rule the out-of-range `--max-p` check
  follows. The preflight reads headers only and answers unknown to every content
  problem, so the converse also holds: a malformed verdict mapping cannot answer
  in place of the ledger, and the full read happens after the guards.
- **A results envelope cannot delete the refusal.** The first cut compared the two files
  against each other and refused only when both declared a corpus and the two
  disagreed, which left the refusal reachable by omission. Stripping the
  envelope off either side, which is what every consumer written before the
  envelope did, turned a known mismatch into two unknowns, and two unknowns have
  nothing to disagree about. The pin moves the value into the baseline
  commitment so no results file can delete it, and one known corpus beside an
  unknown one counts as a conflict, because a pair scored on one corpus does not
  have one side that forgot.
- **Deleting the split's pin is reported, not refused.** Removing the `corpus`
  key leaves two agreeing results files and nothing to contradict them, so the
  conflict rule finds no disagreement. Refusing that shape would refuse every
  `--tasks` split and both artifact classes that pin nothing, so the verdict
  carries `corpus_pinned` instead: `true` means the split named the corpus both
  results carry, `false` means only the two results were checked against each
  other. A sixteenth review found the earlier wording claiming this case was
  refused when it was not.
- **What was scored is what was checked.** The preflight reads headers; the
  comparison is scored from a second, full read. Only the second is
  authoritative, so the conflict rule runs again against the loaded values
  before a consultation is charged. Two reads of one path that never have to
  agree leave a window between them. Both checks emit the same document: a
  seventeenth review found the gate's copy carrying the ledger's prior spend,
  which let the key set alone say which read caught the mismatch and reported a
  number the caller cannot act on, since the budget guard has already run.
- **The refusal names nothing.** No task ids, no holdout key. A caller cannot
  turn repeated mismatches into a probe of the held-out group. The preflight runs
  under the same digest scrubber as the ledger paths.
- **Unknown everywhere is reported, not refused.** Only the agent path publishes
  a corpus identity today. Refusing unknown on all three would disable the gate
  for rules and hooks to guard a case it cannot detect there anyway, so the
  verdict carries `corpus_verified`, where `false` means the check never ran. A
  real mismatch never reaches a verdict.

A corpus identity is validated as 64 lowercase hex characters, the form
`hexdigest()` emits. An unchecked string reports a verified match on values that
identify nothing: two reports both carrying `fixture_set_sha: ""` compared as
verified until a fifteenth review pointed at it.

The bound is worth stating in the decision rather than leaving it to be
discovered. The split file is caller-supplied and its corpus pin is outside the
fingerprint, so a caller who edits the split can still push an
incomparable pair through: delete the pin, and two results scored on one corpus
compare against a split drawn from another. The verdict reports
`corpus_pinned: false` when that happens; nothing refuses it. Closing it needs
authenticated provenance, which this design does not have and does not claim. The requirement
defends against omission, which is the failure that occurred.

Task ids do not substitute, which is the reason the requirement is about corpus
contents rather than key sets. All eight fixture ids matched across those two
runs while all eight files differed. Identity of the keys says nothing about
identity of what the keys point at.

The requirement is bounded by what the scorers publish. `fixture_set_sha` is a
trusted source in the sense that requirement 12 asks for: it is computed by the
scorer from the fixture contents, not supplied by the caller being budgeted.
Neither the rule path nor the hook path publishes an equivalent, so open
requirement 12 stays open for them.

### What the mechanism protects against, and what it does not

This is a discipline control against accidental overfitting by a cooperating
optimizer. It is not a security boundary against an adversarial one.

**Held-out membership is public, and has to be.** `split` publishes `opt` on
stdout because the loop cannot edit toward a group it cannot name. The task
universe is the caller's own results file. So when no test group was drawn, and
the default `--test-ratio` of 0.0 draws none, the held-out group is the
complement of a published set inside a set the caller supplied, and subtraction
recovers it exactly. Verified directly: a twelve-task run publishes seven
optimize ids, and `universe - opt` is the five held-out ids on the nose.

An earlier revision of this ADR argued that publishing membership is harmless
because identity is public while outcomes stay withheld. A sixth review
falsified both halves.

**Outcomes are not withheld.** `cmd_extract` calls `_emit` on the complete
task-to-outcome mapping and its parser takes no group argument. The workflow
this ADR describes has the optimizer run `extract` itself to produce `base.json`
and `cand.json`, so held-out outcomes sit in the optimizer's own files before
the gate is called. `score --group` is group-aware; nothing routes the loop
through it.

**Publishing membership is sufficient to defeat the intent even without
outcomes,** because a task id resolves to a readable definition carrying its own
grading criteria. `evals/analyst-spike/fixtures/F001.json` holds the input, the
expected verdict, and the regex the scorer asserts.
`tests/evals/rule-scenarios/clean-architecture.json` holds the expected
vocabulary and rationale. `tests/hooks/test_dash_guard.py` is the assertion
itself. Naming a held-out task is therefore enough to hand-tune for it.

**The argument that the loop must name what it may not touch is backwards.** An
optimizer edits toward `opt` and needs no knowledge of `sel` at all, which is
how an ordinary train and validation split works. Only `opt` has to be exposed.
Dwork's reusable holdout (arXiv:1506.02629) assumes the analyst reaches the
holdout only through the mechanism, and that assumption is exactly what does not
hold here.

**The gate does not return one bit either.** Its payload carries both scores,
both discordant counts, and the p-value. The ledger bounds how many times the
loop may ask, not how much each answer tells it.

Two things follow. Redacting held-out ids from gate errors buys nothing in the
default configuration, and is kept for the configuration where it buys
something: with a test group drawn, the complement is the union of two groups,
the published sizes do not say which is which, and an error that named ids or
printed the membership digest would say exactly that. And no claim in this ADR
should be read as hiding the held-out task list, because it does not.

The split file, the ledger, and the results all sit on the same disk as
everything else, and an agent with write access can edit any of them. What the
mechanism removes is one accidental path and leaves another open. It removes
scoring against the held-out group because a sibling subcommand offered it,
and exhausting a budget that was never actually counted. It does not remove
reading held-out outcomes, because `extract` still emits every task's outcome
with no group argument and the documented workflow calls it (#3452).
Those were all real and all present in the first implementation. Each has a
deliberate path around it that survives: delete the ledger, set
`$EVAL_LEDGER_DIR`, edit the split, remove a stale lock, name a huge cap on the
first call. What closed is the version an ordinary invocation could reach by
accident.

Making this a real boundary needs a controller the optimizing agent cannot
write to. That is named under Open Requirements rather than claimed here.

### What this does not require

- It does not require a p-value threshold by default. Paired evidence
  (McNemar's exact test on the discordant counts) is reported on every compared
  decision and enforced only when the caller passes `--max-p`. At the group
  sizes this repository actually has, three discordant tasks cannot produce a p
  below 0.125, so a conventional 0.05 floor would make the ordinary case
  unpassable rather than informative. Reporting it keeps the reader honest about
  how thin the evidence is. Defaulting to enforcing it would only teach the loop
  to grow the eval set until the arithmetic cooperates.

  The flag exists because the 2026-07-27 live run produced an ACCEPT at p=0.25
  that a null control then reproduced from noise. Where an operator has enough
  held-out tasks to afford the power, the tail the gate already computes should
  be able to refuse. `--max-p` is read as the family bar and divided by
  `--max-consultations` (Bonferroni), because a per-comparison threshold does
  not bound a family: five looks at 0.05 each bound the family at 5 * 0.05 =
  0.25 without assuming anything about dependence, and at about 0.226 only if
  the five comparisons are independent, which looks at one selection group are
  not. Bonferroni controls the family bar under any dependence, which is why it
  is used rather than a sharper independence-dependent correction, and it means
  raising the budget buys more
  looks at a stricter bar rather than a cheaper one. It also costs power: at ten
  held-out tasks, clearing a corrected 0.01 needs seven one-directional
  discordant pairs. The bar refuses genuine improvements at these sizes. That is
  why it is opt-in rather than the default, and why the durable fix is more
  tasks or repeated sampling (Open Requirement 6), not a tuned threshold.
- It does not require a test group. At this repository's fixture counts, where
  the mode is 8, a three-way split can leave a selection group too small to
  decide anything. The default is optimize and selection only, and that default
  is stated rather than hidden.
- It does not apply to a single evaluated change. One edit, evaluated once,
  against a set the author had already seen, is the situation ADR-057 and
  ADR-058 already govern. The failure this ADR addresses needs iteration to
  appear.

## Consequences

### Positive

- An improvement claim means something it did not mean before, and the bound
  has to be stated exactly or it will be overread. What the mechanism delivers
  is this: **a consultation-budgeted comparison over a public benchmark,
  relying on a cooperating optimizer not to inspect task definitions and result
  files it can already reach.** It is not held-out validation of unseen tasks.
  Three drafts of this ADR claimed the stronger thing in three different
  phrasings, and each was falsified by reading the implementation. What holds
  regardless of the optimizer's cooperation is the budget: the consultation
  count, its cap, its storage path, and its key are derived from the held-out
  membership, with two exceptions worth stating rather than glossing: the
  path's root comes from the environment or the home directory, and the cap's
  first value comes from `--max-consultations` before it is pinned. So a budget
  already in progress cannot be moved by a caller argument; a first invocation
  still chooses its own cap, and filesystem access still relocates or deletes
  the root. What that bounds is **gate comparisons** against the held-out
  group, not total selection pressure, since `extract` and `score` reach
  results without touching the ledger. Gate comparisons are the quantity
  is the quantity multiple-comparison correction is about and the failure this
  directory actually had.
- The rule generalizes past skills, which is where the practice started. The
  seam between the decision and any scorer is one mapping of task id to pass
  boolean, so a fixture id, a scenario id, and a pytest node id are the same
  kind of thing to it. Agents, rules, and hooks are covered by one mechanism
  rather than three. Prompts are not: the ADR opens on prompt evaluation, but
  no prompt adapter exists yet, so prompt work goes through the rule adapter or
  not at all.
- ADR-057's degradation clause is enforced at the point of decision as well as
  at the point of review, on the held-out group specifically.
- The comparison itself is pure and unit-testable without eval budget. The
  scorers spend; the decider does not. The gate around that comparison is not
  pure, and an earlier draft of this ADR claimed it was: it takes a lock, reads
  a ledger, and writes one before it decides anything.

### Negative

- Fewer tasks inform each decision. A ten-task set at default ratios decides on
  four. That is a real loss of statistical power, accepted knowingly, and it is
  the cost paid for a benefit the mechanism only partly delivers. Under a
  cooperating optimizer the four carry a generalization claim the ten cannot;
  under one that reads its own `extract` output they carry a weaker claim than
  that, bounded by the budget rather than by ignorance. Four of anything is thin
  evidence either way.
- Reporting a p-value without enforcing it means accepted edits will carry
  weak evidence and say so. A candidate that fixes one held-out task and breaks
  none reports `p = 0.5` and is accepted, because one discordant pair cannot do
  better than 0.5 on a one-sided exact test. Anyone reading `p_value` as an
  accept criterion will misread it. It is a disclosure, not a gate, and the
  README says so at the point of output.
- Scorer noise is not handled uniformly across the three adapters. A held-out
  task that flips for reasons unrelated to the edit refuses a good edit under
  requirement 4. The exposure differs by artifact: the hook adapter is
  deterministic, the agent adapter already reduces over multiple runs (mean by
  default), and the rule adapter is single-shot against an LLM judge and
  therefore carries the full exposure. That gap is real and specific; it is not
  a reason to weaken requirement 4, because the costs are asymmetric. A
  spurious reject costs one rollout. A spurious accept ships a regression and
  raises the baseline it will be measured against next time.
- Small evaluation sets get more expensive to grow. Adding tasks mid-loop
  invalidates the fingerprint by design, so a set that turns out to be too small
  costs a restart rather than an append.
- The consultation budget will sometimes stop a loop that was making genuine
  progress. That is the cost of the guarantee; an unbudgeted loop cannot
  distinguish progress from selection.
- The boolean seam discards information the scorers already produce. An edit
  that lifts every held-out task from 0.50 to 0.99 without crossing the
  threshold is invisible to this decision. Tracked as issue #3437; the boolean
  is what makes three unlike scorers commensurable, so widening it is a
  redesign rather than an increment.

### Neutral

- Existing evaluators are unchanged. This ADR governs iterated improvement
  claims, and an evaluator invoked once for a single verdict is unaffected.

## Open Requirements

These block a move from `proposed` to `accepted`. They are listed as
requirements rather than nice-to-haves because each one is a place where the
document currently claims less than a reader might assume. The numbered items
in this section are referred to as Open Requirement 1 through Open Requirement
12, to keep them distinct from the Decision Requirements above.

Open Requirement 1 is not in that category. It is a **prerequisite for the
Decision statement's stronger form**, not future hardening, and it is listed
first for that reason.

1. **A trusted controller that owns task definitions, scoring, and result
   files, and hands the optimizer only the optimize group.** Three separate
   facts make this a prerequisite rather than an improvement. `extract` emits
   every task's outcome with no group argument, and the documented workflow has
   the optimizer run it. Task ids resolve to readable definitions carrying
   their own grading criteria, so membership alone is enough to hand-tune.
   `split` publishes `opt`, and with the default `--test-ratio` of 0.0 the
   complement is the held-out group by subtraction. Until a controller owns
   those three surfaces, this ADR must not be read as validating on unseen
   tasks; it validates under a bounded number of consultations, assuming
   cooperation. Two narrower changes were identified and deferred to their own
   issues rather than built here, since each changes behavior and this change
   is already large: making `extract` group-aware alongside a whole-universe
   coverage check in the gate (#3452), and minimizing the gate payload so
   diagnostics travel on a controller-only channel (#3453). The second carries a real tension:
   reporting `p` always and never enforcing it is load-bearing elsewhere in
   this ADR, and a `--diagnostics` flag the loop passes itself would be the
   same caller-supplied-restriction defect this document catalogs five times
   over. Under the current architecture that can only be a default.
2. **Provenance binding between the compared artifacts and the results files**
   (#3436). Nothing currently proves `candidate.json` was produced by the edit
   under test rather than by a previous run.
3. **A decision on the boolean seam** (#3437). Both code reviewers and both ADR
   reviewers argued for `{task_id: float}`. The boolean is what makes three
   unlike scorers commensurable, so this is a redesign, and it is the user's
   call rather than the author's.
4. **A governance document, per ADR-022's own matrix.** This ADR carries an
   enforcement obligation, and ADR-022 asks for both halves in that case.
5. **A live rule-path validation run.** Done 2026-07-27 via GitHub Models; see
   Validation Status. It produced a false accept and the null control that
   caught it, which is what promoted requirement 6 from a suspicion to a
   measurement.
6. **Multi-run reduction for the rule adapter** (#3445). The agent adapter
   already averages over runs; the rule adapter is single-shot against an LLM
   judge, which is the noisiest of the three and the only one with no defense.
   Now measured rather than assumed: scoring identical rule text twice moved
   13 of 24 tasks, 5 of them across the pass threshold, with mean absolute
   movement of 0.49 points on the five-point judge scale. The two held-out
   gains that produced the false accept were the two largest movements in the
   benchmark, 0.75 to 3.75 and 1.75 to 3.75. That is larger than the effect any
   single edit in this loop has produced, so until this lands, an accept on the
   rule path carries no more information than a coin flip that happened to
   avoid the no-regression clause. `--max-p` bounds the damage; it does not
   supply the missing samples. These are magnitudes from one paired re-run, not
   an estimated rate; a rate needs repeated replication, which is the work this
   requirement names.
7. **A one-time reveal path for the test group.** Decision Requirement 1 says
   the group is read once at the end, but no command reads it: `score` accepts
   `--group opt` only, and `gate` always reads `sel`. Either implement the
   reveal with its own once-ever record, or drop the third group from the
   design.
8. **A noise-parameter study before any reusable-holdout work.** See
   Alternatives Considered. `Thresholdout` is not rejected on merit; it is
   unadopted because nobody has chosen its parameters for the held-out sizes
   this loop actually produces.
9. **A policy for the initial cap.** The first call names any positive integer
   and the ledger then pins it. Nothing constrains that first number, so the
   budget is only as tight as the caller's first invocation. A ceiling belongs
   in whatever governs the loop, not in an argument the loop passes itself.
10. **A ledger root the loop cannot relocate.** `$EVAL_LEDGER_DIR` moves the
    state directory, which is how the tests stay isolated and also how anyone
    who sets it starts over. `$XDG_STATE_HOME` moves it too, and so does
    anything that changes what `Path.home()` returns, so the requirement is a
    root the process cannot relocate rather than one environment variable.
    Closing it means requirement 1's controller, or a root pinned by whatever
    launches the loop.
11. **A lock that expires rather than being cleared by hand.** A lock left by a
    killed process is reported rather than broken, because guessing the holder
    is gone makes the lock advisory. The consequence is that clearing it is a
    manual act with no record, and the process that clears it is the same one
    the budget constrains. An expiry alone does not close this: a paused holder
    can wake after its lease lapsed and another process took the lock, and both
    then write. It needs renewal plus a fencing token checked at the ledger
    write, which is enough machinery to want its own decision.
12. **A corpus namespace with a trusted source.** Decision Requirement 3
    accepts that two
    unrelated corpora with identical task ids and identical held-out membership
    share a budget, because the seam offers no corpus identity the caller did
    not supply. A namespace derived from task contents would fix it and needs a
    seam that carries them. On 2026-07-27 this stopped being hypothetical. Two
    architect-spike runs with identical task ids but different `fixture_set_sha`
    were gated against each other and read as a null control, and the resulting
    claim was published before the mismatch was found. The same missing identity
    that lets two corpora share a budget lets two corpora be compared, and the
    comparison failure is the more expensive of the two because it produces a
    verdict that looks valid. Decision Requirement 5 closed the comparison half
    for the
    agent path, whose scorer publishes `fixture_set_sha`. What stays open is the
    budget half, and both halves for the rule and hook paths, which publish no
    corpus identity for the seam to carry.

The default `--test-ratio` is 0.0, so the ordinary invocation produces optimize
and selection groups only. Decision Requirement 1's "test group, when present"
describes
an option that the default does not exercise. A reader should not assume a
final untouched group exists unless the split was drawn with one.

## Alternatives Considered

**A reusable holdout with noise-based protection.** Dwork et al., "The reusable
holdout: Preserving validity in adaptive data analysis," Science 348(6248),
2015, show that a held-out set can answer many more adaptive queries than a
naive budget allows if the answers are perturbed and thresholded, spending a
differential-privacy budget instead of a query count. That is the principled
version of requirement 3, and it directly addresses this ADR's weakest point:
the leak across a loop that the consultation cap bounds but does not remove.

Not adopted, and an earlier draft gave two reasons that review showed were
claims about the paper rather than about this repository. Both are withdrawn:
the companion (arXiv:1506.02629) states finite-sample bounds, and its
`SparseValidate` returns a single bit for threshold checks, which is the shape
this gate needs. The two are distinct constructions and an earlier draft
conflated them. `Thresholdout` is the noise-and-threshold mechanism that spends
a differential-privacy budget; `SparseValidate` is the Boolean,
description-length-bounded one. The parameter work below is `Thresholdout`'s.

The reason that survives is about our own state. Adopting `Thresholdout` means
choosing noise scale, threshold, and query budget against a specific held-out
size, then showing the chosen parameters leave usable signal. The task sets this
loop has actually been pointed at run from 12 tasks in the CLI fixtures to 532
hook nodes, and held-out size is that count times the selection ratio, so the
groups vary by more than an order of magnitude and move whenever the ratio does.
Nobody has done that parameter work here. Shipping a noise-based holdout without it would replace a
budget whose failure mode is visible, refusing to compare, with one whose
failure mode is a wrong answer that still looks like an answer. The
consultation cap is the conservative placeholder; the parameter study is listed
as an open requirement, and this is the first place to revisit if the eval sets
grow.

**Cross-validation instead of a fixed split.** Rotating the held-out group
across folds uses every task for both purposes and would recover the lost
power. Rejected for this application: each fold costs a full scoring run, and
scoring runs cost API budget in three of the four cases. It also weakens
tamper-evidence, because a rotating split is harder to fingerprint in a way a
reader can check. Worth revisiting if scoring ever becomes cheap.

**A rubric threshold, per ADR-010.** Terminate when the artifact scores above a
bar rather than when a held-out comparison says stop. Rejected because it
answers a different question. A threshold says the artifact is good enough; it
does not say this edit is what made it so, and the loop is making the second
claim.

**Guidance without mechanism.** Documented in the context above. Rejected
because the party being disciplined can write to the task set.

**Statistical significance as the accept rule.** Rejected on arithmetic. The
group sizes here cannot produce conventional p-values, so the rule would either
never accept or would push the loop to inflate the eval set for reasons that
have nothing to do with coverage.

## Implementation

The mechanism ships in PR #3430:

- `scripts/eval/_optimizer_core.py`: split, fingerprint, budget, decision,
  refusal guards, McNemar. Pure, no I/O.
- `scripts/eval/_optimizer_adapters.py`: one function per artifact class,
  converging each scorer's report shape onto the task-id-to-bool seam.
- `scripts/eval/optimize-artifact.py`: the CLI an optimizing agent drives.

Documented in `scripts/eval/README.md`.

Open follow-ups: #3436 (bind extraction provenance into the compared
artifacts), #3437 (widen the seam past booleans), #3438 (exact ratio
arithmetic), #3439 (rejection buffer lifetime).

## Validation Status

Honest statement of what has and has not been exercised against real data.

- **Agent path**: validated against a real report,
  `evals/analyst-spike/reports/20260528T050708Z-91be1106/report.json`, 24
  fixtures. Baseline 15/24 against agent 13/24; the decision correctly refused
  a real regression. **No null control has been run on this path.** One was
  claimed on 2026-07-27 and retracted the same day: the two architect-spike
  runs it used disagree on `fixture_set_sha`, so the corpus was a second changed
  variable. A valid control needs two runs agreeing on both `fixture_set_sha`
  and `agent_prompt_sha`, and no committed pair does.
- **Hook path**: validated against real `pytest tests/hooks` JUnit output, 532
  node ids extracted. No null control has been run on the hook path, and none
  is needed for the same reason: `pytest_results` is deterministic, so a
  repeated run of the same suite against the same tree produces the same
  mapping. The hook path is the only one of the three where an ACCEPT means
  what it says.
- **Rule path**: validated end to end against live judge output on 2026-07-27.
  Anthropic remained rate-capped, so the run routed through GitHub Models
  (`EVAL_PROVIDER=github`, `openai/gpt-4o-mini`), which `scripts/eval/_providers.py`
  already supported. `eval-rule-activation.py` scored all seven files in
  `tests/evals/rule-scenarios/`, 24 scenarios, 12 passing. An earlier
  error-path-only run had already earned its cost by exposing two integration
  defects that fixtures had hidden: a real envelope shape the extractor
  rejected, and a scenario-id collision that would have silently dropped 20 of
  24 tasks.

### What the live rule run falsified

The run produced an ACCEPT and the ACCEPT was wrong. That is the finding.

A real edit to `.claude/rules/working-with-legacy-code.md` moved the held-out
group 0.6 to 0.8 with two discordant gains, no losses, p=0.25. Post-hoc, the
edited rule's own four scenarios had not moved at all; every flip came from a
rule the edit never touched. Restoring the rule byte-for-byte and re-running
the identical scorer as a null control flipped 5 of 24 tasks with no input
change, moved the held-out group 6/10 to 7/10 on its own, and reproduced both
gains that had earned the ACCEPT. Gating the byte-identical no-op returned
REJECT only because the noise happened to break one task, which the ADR-057
no-regression clause caught.

Two conclusions, both load-bearing for this ADR:

1. **A strictly-greater rule over a single sample does not survive a
   nondeterministic scorer.** The decision was made by which way the variance
   fell. `--max-p` now lets the exact tail this gate already computed refuse;
   replaying the run under `--max-p 0.05` turns the false accept into a reject
   naming the 0.25 tail.
2. **No threshold rescues a ten-task held-out group.** A one-sided exact
   McNemar tail cannot reach 0.05 below five one-directional discordant pairs,
   so at this size the bar refuses genuine improvements too. Power comes from
   more tasks or repeated sampling per task, not from tuning the bar. That
   remains unbuilt.

This strengthens rather than weakens the case for the design: the gate refused
to be talked into anything by the optimize group, and the failure it did have
was visible in a number it was already printing. It also means no run of this
loop should be cited as evidence of an improvement until a null control has
been run alongside it.

One property of these numbers is worth stating so nobody over-reads them. The
"scorer variance" measured here is a compound of two nondeterministic stages,
the response model and the judge, both `gpt-4o-mini` at temperature 0. The
harness sets no per-stage seed and records no `system_fingerprint`, so nothing
in these reports attributes the movement to one stage or the other. The
0.49-point mean is the variance of the pipeline. Whether a judge held fixed
would show less is untested here.

### A retracted agent-path claim, and the guard it produced

An earlier revision of this section claimed the architect spike reproduced the
rule finding on a second benchmark: two runs of `claude-sonnet-4-6` against the
same eight fixtures, five of eight moving, and an ACCEPT on a pure null control.
**That claim was wrong. It is withdrawn in full, and so is the twelve of
twenty-four figure built on it.**

The two runs did not share a corpus. Each agent report carries
`fixture_set_sha`, and `_fixture_set_sha` in `eval-agent-vs-baseline.py`
documents its purpose exactly: it "allows the report consumer to verify that two
runs hit the same set." The two architect runs report `be99fa1b1180` and
`26136df314d6`, and all eight individual `fixture_sha` values differ. The
fixtures were committed once, on 2026-05-29, after both runs; the committed
copies match the later run, so the earlier corpus is unrecoverable. Fixture
content is a second changed variable, so nothing about the movement can be
attributed to run-to-run noise.

The two corroborating pairs fail for a different reason. The critic and
high-level-advisor comparisons hold `fixture_set_sha` fixed but differ in
`agent_prompt_sha`. There the prompt is the changed variable. Three confounded
comparisons pooled together do not make one valid one.

The corrected state of the evidence is one measured path, not three:

- **Rule path, measured.** The artifact was restored byte-for-byte and verified
  identical to `origin/main` before the re-run, holding both the corpus and the
  artifact fixed. Both held-out gains that earned the ACCEPT reproduced under
  the no-op.
- **Agent path, unmeasured.** A control needs two runs agreeing on both
  `fixture_set_sha` and `agent_prompt_sha`. No committed pair does.
- **Hook path, deterministic by construction.**

The error is more useful than the claim would have been, and it belongs in this
ADR rather than in a commit message. The report schema already carried the field
that falsifies the comparison. The tool that performed the comparison never read
it. Nothing in the design would have stopped the next person from repeating the
mistake, and the person who made it had just spent a session arguing that a
property reported but not enforced is not a property. Open requirement 12
already named the missing piece, that the seam carries no corpus identity. This
is the first evidence of what that costs, and it raised the requirement from a
budget-accounting nicety to a correctness gap: the same absence that lets two
unrelated corpora share a ledger also lets two unrelated corpora be compared to
each other. Decision Requirement 5 closes the comparison half on the one path
whose
scorer publishes an identity.

### What follows for anyone running this loop

A `gate` ACCEPT is only as trustworthy as the benchmark underneath it. Say that
plainly rather than burying it: `optimize-artifact.py gate` with no `--max-p` is
a guard against an optimizing agent gaming its own benchmark, and it is not a
guard against the benchmark being noisy. Those are different threats and only
the first one is closed by default. On the one path where a control was actually
run, the default issued an ACCEPT for gains that a no-op reproduced.

Until requirement 6 lands, a run of this loop against `rule_results` or
`agent_results` is worth citing only alongside a null control, and `--max-p`
should be supplied. The hook path needs neither, because it is deterministic.

The ADR stays proposed. The rule path is live-validated; requirement 6 is why it
cannot move further. A single-sample scorer at this benchmark size cannot
distinguish an edit from noise, and that is a property of the benchmark rather
than of the gate. That claim now rests on one benchmark, measured, rather than
on two, one of which was not measuring what it said.

## References

- ADR-010: Quality Gates with Evaluator-Optimizer Pattern. Bounds iteration
  count; does not bound what the loop may observe.
- ADR-057: Prompt Behavioral Evaluation Methodology. Source of the degradation
  clause this ADR makes operative.
- ADR-058: Agent Eval Discipline. Between-subjects; complementary rather than
  overlapping. Status `proposed`, cited as existing practice not as authority.
- ADR-022: Architecture vs Governance Decision Split Criteria. Basis for filing
  this as an ADR. Status `proposed`, and its matrix also asks for a governance
  document here; see Open Requirements.
- Dwork, Feldman, Hardt, Pitassi, Reingold, and Roth, "The reusable holdout:
  Preserving validity in adaptive data analysis," Science 348(6248):636-638,
  2015, and the technical companion "Generalization in Adaptive Data Analysis
  and Holdout Reuse," arXiv:1506.02629. The principled treatment of repeated
  queries against one held-out set, and the standard requirement 3 approximates
  with a plain counter.
- Issue #3422: the investigation that produced the mechanism.
- PR #3430: the implementation.
- Yang et al., "SkillOpt," arXiv:2605.23904. Prior art for held-out-gated skill
  optimization. This ADR departs from it in two places, both because the loop
  runs unattended rather than in a benchmark harness: the split is
  fingerprinted because the task set is writable, and repeated decisions are
  budgeted because a sequential decision against one group selects on it.
