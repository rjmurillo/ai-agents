---
status: recorded
process: adr-review adversarial rounds (7 rounds, 2 non-Claude models)
adr: ADR-087
---

# ADR-087 Held-Out Gate Debate Log

Adversarial review of ADR-087 and the code it describes, session 3422, PR
\#3430. Recorded honestly: this was not the six-persona architect / critic /
security panel the adr-review skill usually convenes. The objective required
adversarial review by models different from the authoring model, so every
round was run by `gpt-5.6-sol` or `gemini-3.1-pro-preview` against work
authored by Claude, with the reviewer told to assume a defect existed and to
produce the strongest available falsification.

Seven rounds ran. Every one of them falsified at least one load-bearing
claim. That record is the reason ADR-087 carries a defeat table instead of a
clean argument, and the reason its Decision statement is weaker than the one
the first draft made.

## Votes

| Round | Reviewer | Verdict |
| --- | --- | --- |
| 1 | gpt-5.6-sol | REJECT |
| 2 | gemini-3.1-pro-preview | REJECT |
| 3 | gpt-5.6-sol | REJECT |
| 4 | gemini-3.1-pro-preview | REJECT |
| 5 | gpt-5.6-sol | REJECT |
| 6 | gemini-3.1-pro-preview | REJECT |
| 7 | gpt-5.6-sol | REJECT |
| 8 | Copilot (PR #3458) | REJECT |
| 9 | gemini-3.1-pro-preview | REJECT |
| 10 | gpt-5.6-terra | REJECT |
| 11 | gpt-5.6-luna | REJECT |
| 12 | gpt-5.6-sol | REJECT |
| 13 | gemini-3.1-pro-preview | ACCEPT |

Twelve consecutive rounds returned REJECT. Every finding was verified at source before being
acted on, rather than accepted on the reviewer's authority; all of them held.
The ADR is recorded with its defeats visible because twelve consecutive
falsifications are evidence about the claim, not noise to be smoothed over.
The thirteenth round is the first that did not falsify anything, and one
ACCEPT after twelve REJECTs is the moment to distrust relief rather than bank
it, so its load-bearing claim was re-verified independently before being
accepted.

Rounds 8 through 12 are the cleanest illustration in this log of why the
count kept climbing. Each found its defect inside the previous round's fix.
Rounds 10, 11, and 12 were all given explicit permission to return ACCEPT and
told that a false finding costs more here than a missed one, so the streak is
not an artifact of the prompt asking for a defect. Round 11 is also the first
round whose report was partly declined, which is the other half of taking
reviews seriously.

## The finding that changed the decision

Round 6 falsified the ADR's central argument: that withholding the decision
group's membership bounds what the loop can tune toward. Both halves are
false, and both were verified at source.

1. Outcomes are not withheld. `cmd_extract` calls `_emit(results)` on the
   full mapping and its parser has no group argument, and the documented
   workflow has the optimizer run `extract` itself. Held-out results were
   already sitting in the optimizer's own files, uncharged. Tracked as
   \#3452.
2. Membership is public and sufficient. Task ids resolve to readable
   definitions that carry their own grading criteria: a fixture's expected
   verdict and regex, a scenario's expected vocabulary, a pytest assertion.
   Naming a held-out task is enough to hand-tune for it.

The reviewer also inverted the ADR's own reasoning. "The loop cannot edit
toward a group it cannot name" is backwards: an optimizer edits toward the
optimize group and needs no knowledge of the selection group at all. Only the
optimize group must be exposed for the discipline to work.

Resolution: the Decision statement was weakened, four paragraphs recording
why both halves are false replaced the original argument, and the honest
characterization now leads both the ADR and the README.

> A consultation-budgeted comparison over a public benchmark, relying on a
> cooperating optimizer not to inspect accessible task definitions or result
> files. It is not yet held-out validation of unseen tasks.

## The recurring defect

Eleven of the twelve rounds found the same shape. Any part of a budget the caller
can restate, or move by renaming something else, is not part of the budget.
The same holds for what the budget is meant to withhold: any path by which the
withheld thing is readable is not withholding it.

1. The count. `--consultations` defaulted to 0 every call, so a loop passing
   zero each time had an unlimited budget while looking capped. Review
   reproduced two ACCEPTs under a cap of one.
2. The cap. `--max-consultations` defaulted to unlimited.
3. The ledger path. A missing ledger starts at zero, so `--ledger PATH`
   naming a fresh file restored the whole budget.
4. The split path the ledger derived from. Copying the split to a new name
   reset the budget with identical membership inside.
5. The fingerprint. It hashed the split's inputs rather than its drawn
   result, so it caught an added or removed task but not a task moved between
   groups.
6. The digest in error paths, then the digest reachable from generic I/O
   failures. Every ledger filename ends in the digest of the held-out
   membership, so any error interpolating a path leaked the withheld thing.
   Closing it per call site missed lock release, which runs after the
   decision is already emitted.
7. The pathless `OSError`. Two failures inside the lock operate on a file
   descriptor and carry no filename, so they fell past the redaction branch
   into a raw re-raise that `main` does not catch, leaving the JSON contract
   for a stack trace.
8. The unredacted cause. Redacting the message and chaining the original with
   `raise ... from exc` leaves the digest one `__cause__` hop away, which is
   exactly where a printed traceback goes.
9. The line above the seam. `lock.parent.mkdir(...)` sat one line outside the
   scrub that covers everything below it, so the first thing the lock does was
   the one thing nothing protected.
10. The new line above the seam. Moving the `mkdir` in left `_ledger_root()`
    above it, and that call resolves the home directory, which can fail
    outright. Fixing a boundary by moving one line inward leaves whatever was
    above that line as the new boundary.
11. The guard in front of the redaction. `_scrub` learned to fold case and the
    `if holdout_key in text` deciding whether to call it did not, so the input
    the fix was written for skipped the fix. The one-definition rule has to
    cover the predicate, not just the replacement.

## Round 7 blocking findings

1. The digest scrub covered the lock's acquire and left its release outside.
   `lock.unlink(missing_ok=True)` in the `finally` names the lock file, and
   `main()` catches `ConfigError` but not `OSError`, so a cleanup failure
   printed the whole held-out group as an uncaught traceback one line below
   where the leak was supposedly closed. RESOLVED in `97817c0ba`: the scrub
   now spans the whole lifecycle. Safe over the `yield` because
   `LedgerMismatchError` is a sibling of `ConfigError`, not a subclass.
2. Both documents said the budget bounds "the loop's own selection pressure."
   False: `extract` and `score` reach results without touching the ledger, so
   the budget bounds gate comparisons only. RESOLVED in `f690ce24b` for the
   README and in this ADR's Consequences section.

## Round 8 blocking finding

The scrub added in round 7 re-raised `OSError` untouched whenever the message
did not contain the digest, and `main` catches `ConfigError`, `AdapterError`,
and `ValueError` but not `OSError`. Ledger failures that name a path stayed
inside the CLI's JSON error contract; ones that name no path escaped as
tracebacks. Two are reachable inside the lock: `os.write` filling the disk and
`os.close` hitting EIO both operate on a file descriptor, so neither message
carries a filename, so neither reached the redaction branch that also happened
to be the branch keeping them in the contract.

This is the recurring defect one layer down. The handled paths were the ones
somebody enumerated. RESOLVED: the seam converts every `OSError` and redacts
only when the digest is present, so the contract and the redaction stop being
the same branch. A `ConfigError` without the digest is re-raised as itself so
nothing inspecting the exception object loses it.

Two adjacent claims were checked while fixing it and both held, so no change
was made: `LedgerMismatchError` derives from `Exception` rather than
`ConfigError`, so the scrub never touches it and it reaches its handler
intact; and both of its messages name `path.parent` rather than the
digest-bearing filename.

## Round 9 blocking findings

Round 9 was asked for the ninth defect by name, on the theory that eight
consecutive rounds each finding something says more about the code than
about the reviewers. It returned two, and both reproduced.

The first is the ninth shape of the recurring defect: the seam redacted the
digest from the message and then attached the unredacted exception as
`__cause__`. `key in str(exc)` was False and `key in traceback` was True. The
lock-contention branch was worse, because its message deliberately withholds
the lock name and then handed back the `FileExistsError` that spells it out.
A redacted message with an unredacted cause is not redacted.

The reviewer proposed severing every chain. That was wider than the evidence
supported, so the fix severs the two branches that provably carry the digest
and leaves `from exc` on the pathless-`OSError` branch, where `str(exc)` has
no filename to leak and the original raise site is worth keeping. That the
`holdout_key in text` test is a sound detector was checked rather than
assumed: `str(OSError(2, "m", "/p"))` includes the filename and
`str(OSError(28, "No space"))` does not.

The second finding was not a leak. Release runs in a `finally`, after the
decision is already on stdout, so an unlink failure reached `main`, which
printed a second JSON document after the first and returned the
config-failure code for a comparison that had succeeded. Verified: exit code
2 on a passing gate, and `json.loads` on stdout raising "Extra data". The
module docstring promises a caller reads a field rather than guessing from
the exit code, and two documents break every reader of the first. Cleanup now
catches `OSError` locally and warns on stderr.

Worth recording plainly: this session had already observed the two-document
stdout while writing round-7 tests, recorded it as a test-harness quirk, and
worked around it. The reviewer reclassified it correctly. A workaround that
makes a symptom stop being visible in tests is not a finding closed.

## Round 10 blocking finding

Round 10 was told plainly that a false finding costs more than a missed one
here and that ACCEPT was an acceptable answer. It returned REJECT with one
finding that has two legs, and both reproduced.

The leak leg is the weaker one and is recorded as such rather than at the
severity the reviewer assigned. `$EVAL_LEDGER_DIR` can name a directory
containing the digest, and both the `mkdir` traceback and the round-9 release
warning render that directory. A caller who set that variable already knows
the digest, so this discloses a secret to the party holding it. It is fixed
anyway, for two reasons that do not depend on the threat model: the standing
rule from nine rounds is that a path by which the withheld thing is readable
is not withholding it, and the release warning was justified in review by the
claim that a directory carries no digest, which this falsifies.

The contract leg is the stronger one and needs no digest anywhere. `mkdir` on
a ledger root the process cannot create raises `PermissionError`; `main`
catches `ConfigError`, `AdapterError`, and `ValueError`. A read-only home or a
sandboxed runner therefore got a traceback where the module docstring promises
a JSON error document. That is the round-8 defect, still live at the one line
that was outside the seam, reachable with no contrivance at all. Verified
before the fix as `PermissionError` with `main would catch it: False`, and
after as `ConfigError` with `True`.

The fix moves the `mkdir` inside the scrub and gives redaction one definition,
`_scrub`, used by the seam and by the warning. The round-9 warning was a
second redaction site written by hand, and it was wrong. Two consecutive
rounds finding a defect at a hand-written redaction site is the argument for
having exactly one. A plain root is still named in the warning, under test,
because redaction that redacts everything is silence rather than redaction.

## Round 11: three findings taken, one declined

Round 11 was given the same explicit permission to return ACCEPT. It returned
four findings. Three were reproduced and fixed; one was reproduced and
declined, which is recorded here because a review process that accepts
everything is not reviewing.

Taken, and the only one that matters on its own: `_ledger_root()` sat above
the scrub after round 10 moved the `mkdir` inside it. `Path.home()` raises
`RuntimeError` when `$HOME` is unset and the uid has no passwd entry. That is
an ordinary container running as a numeric user, and it fires on the default
configuration, because the root consults home only when neither
`$EVAL_LEDGER_DIR` nor `$XDG_STATE_HOME` is set. `main` does not catch
`RuntimeError`. Verified before the fix as `RuntimeError` with `main catches
it: False`, and after as `ConfigError` with `True`. Realism was checked rather
than argued: with `$HOME` unset and `pwd.getpwuid` raising, `Path.home()`
raises "Could not determine home directory."

Taken, small: `os.write` and `os.close` shared one `try`, so a write failing
on a full disk jumped to the `finally`, which unlinks the lock and never
closes the descriptor. The close now has its own `finally`, and is not
retried, because POSIX frees the descriptor even when close reports EIO.

Taken, smallest: `_scrub` matched case-sensitively and a hex digest has an
uppercase spelling that `$EVAL_LEDGER_DIR` can carry. Only reachable by a
caller who already knows the digest. Fixed for the stated property, not the
threat, and because hex is the one alphabet where case folding has no
surprises.

Declined: the report that resolving the root twice lets the lock and the
ledger disagree, letting concurrent gates double-spend. It reproduces only by
mutating `$EVAL_LEDGER_DIR` between the two resolutions. No in-process
environment mutation exists in any of the three modules, checked rather than
assumed, so the CLI cannot reach it. Threading a derivable parameter through
two signatures to defend an unreachable case is plumbing this codebase
declines on purpose. Recorded rather than silently dropped, so that anyone who
later adds environment mutation knows this was weighed.

## Round 12: the previous round's fix, applied to half the pair

Round 12 got the same explicit permission to return ACCEPT and returned one
finding, reproduced through the real `gate` entry point with only the stdlib
`Path.mkdir` patched to deny.

Round 11 taught `_scrub` to fold case because a hex digest has an uppercase
spelling that `$EVAL_LEDGER_DIR` can carry. The line deciding whether to call
it still read `if holdout_key in text`, which does not fold case. So the exact
input round 11 was written for failed the guard, skipped the corrected scrub,
and printed whole. Severity is the stated property rather than
confidentiality, on the standing rule: reaching it requires the caller to have
put the digest in the environment variable, so the reader already knows it.

The fix deletes the second predicate instead of teaching it to fold. `_scrub`
returning a different string answers both "is it here" and "what does it look
like without it", so there is nothing left to keep in step. The one-definition
rule that came out of rounds 9 and 10 had been applied to the replacement and
not to the test in front of it.

The tests are the other half of the finding and the more useful half. Round 11
added four tests for case folding and every one called `_scrub` directly. They
passed while the CLI printed the digest, because they asserted that the
function had changed rather than that the property held. A test that exercises
the unit you edited will confirm your edit. Only a test through the seam can
contradict it.

## Round 13: the first round that found nothing

Round 13 ran against gemini-3.1-pro-preview, which is the same model family
that returned REJECT in round 9, so it is not a reviewer that rubber-stamps
this file. It got the same explicit permission to return ACCEPT and the same
warning that a false finding costs more than a missed one. It returned ACCEPT
after probing path-bearing `OSError`s through a read-only `$XDG_STATE_HOME`
and a directory planted at the ledger path, pathless `OSError`s, internal
`ConfigError` propagation, and exception types outside the seam's catch tuple.

Its load-bearing claim was that the last branch, `raise ConfigError(text) from
exc`, keeps `__cause__` but that this is harmless because `main` renders only
`str(exc)`. That was re-verified rather than accepted:

- The pathless branch does keep its cause. Confirmed.
- An exception whose `__str__` hides a path the object still carries defeats
  the scrub in principle, since the scrub reads `str(exc)`. Constructed one.
  The key appears in neither `str()` nor the fully rendered traceback, because
  traceback rendering also goes through `__str__`. So the seam and the renderer
  read the same surface, and a key invisible to one is invisible to the other.
- `main` formats no traceback anywhere in the module. Confirmed by source.
- `OSError.__str__` renders `filename2` as well as `filename`, so a failing
  `os.replace` puts both paths where the scrub can see them. Confirmed.

Thirteen rounds is where this stops. The marginal round now returns ACCEPT,
and the reviewer that accepted had rejected earlier, which is the closest
thing available here to an independent second opinion.

## Corrections applied without dispute

- The path root comes from `$EVAL_LEDGER_DIR`, `$XDG_STATE_HOME`, or home,
  and the cap's first value comes from `--max-consultations`. Only a budget
  already in progress is immovable.
- No `reveal` command exists. The subcommands are `extract`, `split`,
  `budget`, `score`, `apply`, `gate`, `buffer-check`, `buffer-add`. Any claim
  that the test group is scored once at the end describes an open
  requirement, not the implementation.
- A consultation is reserved before the group is read and before coverage is
  validated. That ordering is deliberate, but "charged when the gate reaches
  the comparison" had it backwards.

## Deferred rather than rushed

- \#3452: make `extract` group-aware and replace the one-bit coverage
  predicate with a whole-universe check. These do not compose without a
  controller holding the complete mapping, so the issue is sequenced as a
  prerequisite for Open Requirement 1.
- \#3453: bound what each consultation discloses. There is no fixed
  multiplier to document, so the statable property is the output alphabet.
- \#3437: widen the seam from `{task_id: bool}` to `{task_id: float}`. Every
  reviewer across all twelve rounds argued for it. Left to the user, since it
  is a redesign rather than a tweak.

## What the live run found, after the reviews stopped

Thirteen rounds of adversarial review argued about the gate's logic. None of
them could argue about its inputs, because until 2026-07-27 the loop had never
been driven by a real model. The live run found something no reviewer had:
the gate's accept rule is sound and still produced a wrong answer, because the
scorer underneath it is noisier than any edit it was asked to judge.

Setup: `eval-rule-activation.py` over all seven files in
`tests/evals/rule-scenarios/`, 24 scenarios, `openai/gpt-4o-mini` through
`EVAL_PROVIDER=github`. 12 of 24 passing at baseline, so real headroom. Split
seed `live-2026-07-27`, 14 optimize and 10 held out, fingerprint `06f74397`.

| Run | Held-out | Gain | Loss | p | Verdict |
|-----|----------|------|------|---|---------|
| Real edit to a rule | 0.6 to 0.8 | 2 | 0 | 0.25 | ACCEPT |
| Byte-identical no-op | 0.6 to 0.7 | 2 | 1 | 0.5 | REJECT |

Both candidates gained the same two held-out tasks. The edited rule's own four
scenarios did not move under either run. The null control flipped 5 of 24 tasks
with no input change. The verdict difference was entirely which way the noise
fell: the real edit drew no regression, the no-op drew one, and the
no-regression clause did the rest.

### The fourteenth defect shape

Every earlier shape was a defect in the code. This one is not.

Shapes 1 through 13 were all variations on the same theme: a property was
stated in one place and enforced in another, and the two drifted. Shape 14 is
different in kind. **The gate printed the number that would have caught it and
had no way to act on it.** The source comment said so out loud: p was
"reported rather than enforced" because a three-task held-out group cannot
reach a conventional floor. That reasoning was correct and the conclusion was
incomplete: the right answer was an opt-in bar, not no bar.

The transferable form: *a diagnostic you compute and print but cannot act on
will be read as reassurance.* Reporting p next to an ACCEPT reads as evidence
supporting the accept, when in this case it was evidence against it. If a
number is worth printing beside a verdict, there should be a way to make the
verdict answer to it.

### What this does not fix

`--max-p 0.05` at ten held-out tasks refuses nearly everything, genuine
improvements included: a one-sided exact McNemar tail needs five
one-directional discordant pairs to clear 0.05, and seven once the family-wise
correction from round fourteen divides that bar across a five-consultation
budget. The bar bounds the damage from noise; it does not create the
statistical power the benchmark lacks. That is requirement 6 in ADR-087
(#3445, multi-run reduction), now backed by measurement instead of assumption:
on one byte-identical re-run, 13 of 24 tasks changed score at all, mean
absolute movement 0.49 on a 5-point scale, max 3.00, and 5 crossed the 3.5 pass
line. Those are counts from a single replication, not a rate. Five flips out of
24 has a 95% interval running roughly 7% to 42%, so the honest claim is that
the noise floor is large enough to manufacture the accept we saw, not that it
sits at any particular percentage.

The sharpest number is not the flip count. The two held-out gains that earned
the false ACCEPT, `philosophy-of-software-design::S2` at +3.00 and
`refactoring::S3` at +2.00, were the two largest excursions in the entire
benchmark. The accept rode the two biggest noise events out of 24 tasks.

One more limit the numbers cannot separate. "Scorer variance" here is a
compound of two nondeterministic stages: the response model that produces the
answer and the judge that scores it. Both are `gpt-4o-mini` at temperature 0,
and the harness records no per-stage seed, so nothing in these reports
attributes the movement to one or the other. The 0.49 mean is the variance of
the pipeline, not of the judge. `_providers.py` passes `temperature` but never
passes OpenAI's `seed` parameter and never reads back `system_fingerprint`, so
the harness is not currently making the attempt that would let it tell the
difference.

### Method worth reusing

The null control is the cheap part and it is what caught this. Restore the
artifact byte-for-byte, re-run the identical scorer, and gate the result. If a
no-op earns an accept, or gains the same tasks the real edit gained, the loop
is measuring its own variance. Two facts made the suspicion actionable before
the control was run: the edited artifact's own tasks had not moved, and every
flip landed in artifacts the edit could not have touched.

## Round fourteen: reviewing the fix the live run demanded

Two reviewers ran in parallel against the `--max-p` change, both non-Claude, per
the ADR Review Protocol. `gpt-5.6-terra` took the code, `gemini-3.1-pro-preview`
took the ADR claims. Both returned REJECT. Round fourteen is worth recording for
two opposite reasons: the code review found a real statistical error I had
argued myself into, and the ADR review's headline finding turned out to be
false, which is itself a result about how to consume adversarial review.

### Defect shape 15: a per-comparison bar does not bound a family

The `--max-p` flag as first written applied the threshold to each comparison
independently. The loop's own documented recipe permits five consultations
against one held-out group. Five independent looks at 0.05 give a family-wise
false accept probability of `1 - 0.95**5`, about 0.226. An operator who asks for
0.05 and receives 0.226 has been told a number that is not true.

This is the same shape as every earlier defect in this log: a control that
appears to bind and does not. The ledger existed precisely because a budget you
can re-declare is not a budget. A bar you can spend five times is not that bar.

Fixed by reading `--max-p` as the family bar and dividing by
`--max-consultations`. Bonferroni is conservative under any dependence between
comparisons, which is the correct direction for a gate. The useful property is
that the incentive runs the right way: raising the budget buys more looks at a
stricter bar, never a cheaper one, so there is no way to buy an accept by
declaring more consultations.

Three smaller findings shared the shape. The bar was not pinned in the ledger,
so a candidate refused at 0.05 could be re-gated at 0.1 until it passed; it is
now pinned, and its absence pinned too, since omitting the flag is the loosest
setting available. A bar supplied without a p-value accepted rather than raised.
And an out-of-range bar spent a consultation before anything checked its range,
which also meant an exhausted budget turned a malformed flag into an ordinary
REJECT instead of a config error. Range is decidable without reading the
held-out group, so it now runs first.

### The headline finding that was not true

The ADR reviewer's primary claim was that the five flips in the null control
were not model nondeterminism at all but HTTP 429 rate-limit errors recorded as
task failures. It reasoned from real code: `_providers.py` sets `max_retries=0`,
the rule evaluator has no retry loop, and the adapter maps an errored scenario
to `False`. Every link in that chain exists.

The conclusion was still false. Checking the three live reports directly: zero
errored mechanism-runs out of 216, and no `FAIL_JUDGE_ERRORS` verdict in any
run. The reviewer had described a path that could produce the observed pattern
and asserted that it did, without the reports being able to support it.

Two things follow, and they point in opposite directions. First, a review this
confident is worth the ten minutes it takes to check against data before acting
on it; had I accepted it, the debate log would now carry a false explanation for
its central finding, and the null control's actual lesson would have been
buried. Second, the mechanism is real and unguarded even though it did not fire
here, so it was filed as #3474 rather than dismissed. A finding can be wrong
about what happened and right about what can happen. The reviewer's dependent
finding, which claimed the ACCEPT was an artifact of the same errors, falls with
the premise.

### What round fourteen did not fix

The README and ADR contradictions the reviewer found in its remaining three
findings are fixed here. The confounded-variance disclosure is added above. The
missing `seed` parameter in `_providers.py` is noted and unfixed: passing it is
best-effort on OpenAI's side and would not make the harness deterministic, but
not passing it means the harness is not attempting the one cheap thing that
might reduce the noise floor it just measured. Filed as #3475.

## The agent path, and the luck that hid the problem

> **RETRACTED 2026-07-27, same day.** Everything in this section between here
> and "Defect shape 17" rests on the claim that the two architect runs used the
> same fixtures. They did not. The section is kept intact rather than deleted
> because the retraction is the finding; see defect shape 17 below for what was
> wrong and how it was caught.

The rule finding rested on one benchmark and one replication. That is thin
enough to be worth attacking, so I attacked it with data already in the
repository rather than more eval spend.

The architect spike holds two runs of `claude-sonnet-4-6` against the same eight
fixtures, both tracked at `evals/architect-spike/reports/`. Five of eight
fixtures scored differently between them. At the default pass threshold one run
passes five fixtures and the other passes two.

Gating the lower as incumbent against the higher as candidate, default
configuration, no significance bar:

```text
decision: ACCEPT   held-out 0.0000 -> 0.6667
discordant_gain: 2   discordant_loss: 0   p_value: 0.25
held out: A002 False -> True, A007 False -> True, A006 False -> False
```

No edit. No artifact. An ACCEPT.

### Defect shape 16: a protection against regression is not a protection against variance

The rule run was saved by requirement 4, the no-pass-to-fail clause. I recorded
that at the time as the design working. Re-reading it against this result, that
was luck and I should have said so. Requirement 4 fires when noise happens to
break something. It is silent when noise happens to fall one way, and noise is
under no obligation to be symmetric. On the rule path it broke a third task and
the gate refused. Here it did not and the gate accepted.

This is the most useful thing the agent run produced, because it is a correction
to my own earlier reading rather than a new external finding. A control that
holds on the sample you looked at, for a reason that does not generalize, is the
same failure mode as every defect in the fourteen rounds above. I had it in the
conclusions column instead of the defect column.

`--max-p 0.05` over a five-consultation budget refuses the same comparison at
the corrected 0.01. It is the only thing in the design that does.

### The noise floor is not one benchmark's problem

Same same-model, same-fixture comparison on the other two spikes: critic moves
three of eight, high-level-advisor four of eight. Twelve of twenty-four across
the three agents, against thirteen of twenty-four on the rule benchmark.

Weight those unequally. Both architect reports are tracked, so that pair is
reproducible from a clean clone. The critic and high-level-advisor pairs each
have one side that is untracked spike output, so they corroborate rather than
prove.

Even discounted, the shape holds: two unrelated benchmarks, different artifacts,
different scorers, different model families, both moving about half their tasks
when nothing changes. The rule result was not one eval having a bad day.

### What this cost

Nothing. No API calls, no eval spend. The evidence was sitting in the repository
the whole time, in two report files committed months ago. The cheapest
adversarial review available was re-reading data already on disk against a claim
made later, and it produced a sharper correction than either paid reviewer in
round fourteen.

### Defect shape 17: the comparison tool ignores the field that validates the comparison

The section above is wrong, and the same afternoon's attempt to push on it is
what found the error.

The published claim needed the two architect runs to differ in nothing. I had
checked two things before publishing: `model_id` matched, and `agent_prompt_sha`
matched. I did not check the third field, and the report schema puts it at the
top level of both files:

```text
run A  fixture_set_sha be99fa1b1180
run B  fixture_set_sha 26136df314d6
```

All eight individual `fixture_sha` values differ too. `_fixture_sha` is
`sha256(path.read_text())`, so the fixture files changed between the runs. The
fixtures directory carries exactly one commit, `c81ac278f`, dated the day after
both runs, and the committed fixtures hash-match run B exactly. Run A's corpus
is not recoverable from the repository. The comparison had two changed variables,
not zero, and the null control it claimed to be was never a null control.

The other two spikes fail differently. Critic and high-level-advisor each hold a
pair with matching `fixture_set_sha` and **different** `agent_prompt_sha`. So
the corroboration is confounded too, by the other variable. Across all six
tracked spikes there is no same-model pair that agrees on both fields. The
twelve-of-twenty-four figure is withdrawn in full, and the agent path currently
has no null control at all.

What makes this a defect shape rather than a mistake is where the falsifying
information was. `_fixture_set_sha`'s own docstring says it "allows the report
consumer to verify that two runs hit the same set." The report consumer here is
`optimize-artifact.py extract`, and it never reads the field. The schema
provides the check; the tool that needs it discards it. A tool whose entire
purpose is comparing two measurements should refuse a pair the upstream format
already labels as incomparable, and this one accepts it silently and prints a
verdict.

Task ids do not substitute. All eight architect ids matched across the two runs.
Identity of the key set says nothing about identity of what the keys point at.

Two smaller corrections fall out of the same check:

- A hypothesis of mine died on the way here. I predicted the agent path's noise
  lived in the brittle free-text `regex` assertions and that the `verdict`
  assertion was stable, which the committed variance-control run (#1877, N=20,
  ESCALATE twenty times) seemed to support. Measured per assertion across the
  paired runs: `verdict` unstable in 9 of 16 cells, `regex` in 6. The opposite.
  That measurement is drawn from the confounded pair, so it is not publishable
  either; it is recorded here only as the reason I kept digging.
- The #1877 FINDINGS.md generalizes verdict determinism from a single fixture
  where the agent had an unambiguous opinion. That generalization is not safe,
  and it is part of what made the bad claim feel plausible.

The cost of the error was one commit, `bb98bf24a`, which put the claim in the
README, this log, the ADR, and the session log at once. The cost of finding it
was one `grep` for a field name. The asymmetry is the argument for the guard.

Worth generalizing: before spending on a new run to test a claim, check whether
some existing artifact already disagrees with it.

## Defect shape 18: a refusal reachable by deletion is not a refusal

Round fifteen, `gpt-5.6-terra`, REJECT.

The corpus guard from defect shape 17 shipped its first cut comparing the two
results files against each other, refusing only when both declared a corpus and
the two disagreed. The reviewer opened it in one line: strip the envelope off
either side and the pair becomes two unknowns, and two unknowns have nothing to
disagree about. The guard was defeated by `jq '.results'`.

What makes this worth writing down rather than filing as a bug is that the
bypass needs no intent. Every consumer written before the envelope existed emits
a bare mapping, and the reader accepts bare mappings on purpose for backward
compatibility. So the "attack" is what an ordinary pipeline does by default.
That is the same shape as the incident the guard was built for, where nobody
edited anything and a field simply went unread. A guard whose failure mode is
identical to the failure it guards against has not moved the needle.

Two changes close it, and the pair is the point:

- `split` pins the corpus of the results it was drawn from. The value now lives
  in the baseline commitment rather than being inferred from the pair, so no
  results file can delete it. Stripping both envelopes still leaves the pin.
- One known corpus beside an unknown one counts as a conflict. Asymmetry is
  itself the evidence: a pair scored on one corpus does not have one side that
  forgot. This also covers splits drawn before the pin existed.

Neither alone is enough. The pin without the asymmetry rule does nothing for a
legacy split; the asymmetry rule without the pin still falls to stripping both
sides.

Two smaller findings from the same round, both real:

- An unvalidated corpus string reported a verified match on values that identify
  nothing. Two reports both carrying `fixture_set_sha: ""` compared as verified.
  The form is now checked: 64 lowercase hex, which is what `hexdigest()` emits.
- Reading both results files in full before the ledger lock let a malformed
  verdict mapping answer in place of an exhausted budget, which tells the caller
  to fix the wrong thing. The pre-lock work is now a header read that answers
  unknown to every content problem and cannot raise. The full read moved behind
  the guards.

One finding was argued down rather than absorbed. The reviewer wanted the whole
corpus check moved behind the ledger lock to preserve refusal ordering. The
check stayed ahead of it: the file's established convention, visible in the
out-of-range `--max-p` check and the split-drift refusal, is that
structural-validity refusals precede ledger refusals, and an incomparable pair
is unusable at any budget. Telling an operator to buy budget for a comparison
that can never be valid is worse advice than telling them the pair is wrong. The
reviewer's underlying concern was satisfied by the header-only read, which is
what actually caused the ordering problem.

The limit is now stated in both the README and the ADR rather than left to be
discovered: the split is caller-supplied and its pin sits outside the
fingerprint, so a caller who edits two files together can still get an
incomparable pair through. This defends against omission, not against an
adversary. Naming the bound is the difference between a claim and a measured
one.

Worth generalizing: when a guard has a "cannot determine" state, check what it
costs to reach that state deliberately. If the answer is one obvious command,
the guard is advisory.

## Defect shape 19: a guard that documented a property it did not have

A sixteenth adversarial review, run against `gpt-5.6-terra` after the corpus
guard was hardened, returned REJECT with five findings. All five were real and
all five were confirmed by running the code rather than by reading it.

The one worth generalizing is the first. The README and the ADR both claimed
the corpus refusal "cannot be deleted". The claim was written about the results
envelope, where it holds: stripping the envelope off either side turns a known
digest into an unknown, and an unknown beside a known one is a conflict. But the
sentence as written covered the split's pin too, and there the claim is false.
Deleting the split's `corpus` key leaves two agreeing results files and nothing
to contradict them, so the conflict rule finds no disagreement to refuse.

The tempting fix, and the one the reviewer proposed, was to require a pin before
any ACCEPT. It was not taken. A `--tasks` split pins nothing by construction,
and neither the rule path nor the hook path publishes a corpus identity at all,
so that rule would disable the gate for two of the three artifact classes the
project exists to serve in order to close a hole that needs the caller to edit a
file they supplied. The fix taken instead splits the claim into two facts the
verdict reports separately: `corpus_verified` for "the two results agree on a
known corpus", `corpus_pinned` for "the split named the corpus they carry". Two
booleans, two guarantees, neither read as the other.

The four others were ordinary and cheap, and each one falsified a sentence in a
docstring:

- The preflight read file headers and the comparison was scored from a second,
  full read, and the two were never reconciled. The conflict rule now runs again
  against the loaded values, before the charge.
- `_read_split` accepted the pin unvalidated, so a split carrying
  `"corpus": []` raised `TypeError` out of a set comprehension. It is now
  validated with the same digest check the results files get.
- `_corpus_header` promised it could not raise on content and caught only
  `ValueError`. A JSON array nested 200,000 deep raises `RecursionError`, which
  escaped as an uncaught traceback ahead of the ledger guard: the exact defect
  shape rounds one through five closed five times, in a function whose docstring
  said it was closed.
- The test asserting the preflight scrubs the digest read `capsys` after
  `_run_gate` had already drained it, then checked stderr while the error is
  emitted as JSON on stdout. It asserted a digest was absent from an empty
  string and could not have failed. It now reads the returned payload and has a
  negative control that fails when the scrubber is removed.

Worth generalizing, twice over. First: a docstring that states a safety property
is a claim, and a claim in a comment is untested unless a test names it. Three of
these five findings were sentences that had been true when written and were
falsified by a later edit, in a file where every such sentence was added by a
previous review round. Second: when a guard covers two mechanisms, write the
property for each mechanism separately. One sentence covering both is how the
weaker guarantee inherits the stronger one's language.

## Defect shape 20: the error contract is a claim like any other

Round seventeen ran a third model, `gemini-3.1-pro-preview`, chosen because
rounds fifteen and sixteen both used `gpt-5.6-terra` and agreement between two
runs of one model is one opinion sampled twice. It was told what round sixteen
found, what was fixed, which reviewer proposal was declined, and why, and asked
to attack that reasoning specifically. It did not overturn the decline. It found
three defects the earlier rounds had walked past, and all three were verified by
running the code before any of them was accepted.

Two of the three were the same shape, and the shape is new to this log. Every
finding through round sixteen was about the gate's decision: what it refuses,
what it charges, what it reveals. These two were about what the CLI does when it
fails, which the README states plainly and which nothing tested.

- `_write_atomic` called `tempfile.mkstemp` one line above the `try` that turns
  a write failure into a `ConfigError`. Its docstring is about the other
  promise, that the artifact is never left half written, and the block below is
  built to keep it. Nobody asked what happens when the temp file cannot be
  created at all. `split --tasks ... --out /nonexistent/split.json` printed a
  `FileNotFoundError` traceback: an ordinary caller mistake, reported as a
  crash, to a caller documented to parse stdout as JSON.
- `_read_json` did not name `UnicodeDecodeError`. `_read_text`, forty lines
  above, catches it with a comment explaining that it subclasses `ValueError`
  rather than `OSError` and so the `OSError` arm never sees it. The same
  sentence is true of `_read_json`, which was written with the same three arms
  minus that one. Nothing crashed, because `main` catches `ValueError`, so the
  defect surfaced only as an error document typed `UnicodeDecodeError` where
  every other unreadable input says `ConfigError`. A caller branching on `type`
  sees a class the contract never mentions.

The third finding was rated optional and is the more interesting one, because it
is defect shape 19 recurring inside the fix for defect shape 19.
`_corpus_refusal` exists so the preflight and the recheck cannot phrase the same
refusal two ways, and its docstring says exactly that: two call sites would let
the caller tell which read caught it. The recheck then emitted
`_corpus_refusal() | {"sel_consultations": spent}`. The key set alone answered
the question the docstring said it must not.

The reviewer proposed unifying the schema. The fix went further, because the
added key was not merely inconsistent, it was the wrong fact. `sel_consultations`
reports the ledger's prior spend, and `_guard` runs before the recheck, so an
exhausted budget has already refused by the time the recheck can fire. The
number was therefore never actionable at that call site: a caller told to
re-score against the right corpus does not decide differently based on how much
budget remains, because budget is known to remain. Dropping it makes the two
documents identical, which is the property the shared builder was written to
have.

Removing it broke one existing assertion, and the break was worth having. A
round-sixteen test named `test_the_recheck_refuses_before_the_consultation_is_charged`
asserted `out["sel_consultations"] == 0`. That value is prior spend, which is
zero in a fresh test ledger whether or not the run under test charged anything.
The test would have passed if the recheck had charged. It now asserts that no
ledger file exists after the refusal, which is the claim the name always made.

Three generalizations, one per shape.

First: the error contract deserves the same treatment as the decision contract.
The gate's refusals have thirty tests between them. Until this round, the
sentence "every failure prints one JSON document" had none that exercised a
write. A promise stated in a README and enforced by a single `except` clause in
`main` is one edit away from false, and the edit that breaks it will be in a
function whose docstring is about something else.

Second: when two readers consume the same bytes, the second one is written by
copying the first, and the copy loses whichever arm was added last. `_read_text`
gained its `UnicodeDecodeError` arm from an earlier review round. `_read_json`
predates that fix and never received it. Grep for the sibling before assuming a
handler is complete.

Third, and this is the one worth carrying out of this file: a helper introduced
to stop two call sites from drifting does not stop them from drifting. It only
makes drift visible as an argument at the call site. The `| {...}` was three
tokens and it defeated the entire purpose of the function it decorated. If a
shared builder is load-bearing, a test has to assert that the call sites produce
equal output, because the language will not.

## Defect shape 21: a retraction that stops at the source document

Round eighteen was not a code review. It was five unresolved threads on the
pull request, and the two that mattered were the same defect wearing two file
names: the agent-path claim this session had already retracted was still being
asserted, in full, by `.agents/memory/episodes/` and
`.agents/memory/causality/causal-graph.json`.

The retraction itself was sound and had been made the same day the claim was
published. The session log carried it. The README carried it. ADR-087 carried
it, in both the finding section and Validation Status. What none of those
reached was the generated tier below them, which had captured the claim before
the retraction and then never ran again.

The reason it never ran again is the interesting part. Every commit in this
session used `SKIP_AUTOFIX=1`, adopted because `stage_fixed: true` drags
working-tree modifications into the staged set and breaks atomic commits. That
flag skips `extract-session-episodes` and `update-causal-graph`. So the
workaround for one hook's staging behavior silently disabled the two hooks whose
whole job is keeping derived memory consistent with the session log. The cost
did not show up as a failure. It showed up as a stale assertion surviving in a
committed artifact for eleven phases, and it took an external reviewer to find
it.

Regeneration was tried first and could not fix it. The hook invokes the
extractor with `--preserve`, which merges a fresh extraction over the existing
file rather than replacing it, so an event whose text is no longer derivable
from the session log is never dropped. Re-running the hook confirmed the stale
event survived untouched. The `--force` path does rebuild purely from the
session log and does remove the claim, but it drops four events recording the
round-sixteen and round-seventeen work and renumbers the rest. Regenerating
would have destroyed more truth than it restored, so the stale event was
corrected in place and the extractor re-run to prove `--preserve` carries the
correction forward instead of reverting it.

Three things generalize.

First, a retraction is complete when every artifact that repeats the claim
repeats the retraction, not when the source document does. Derived tiers are
where a withdrawn claim goes to keep living, because nobody re-reads them and
the generator that would fix them only runs on a commit path somebody may have
opted out of.

Second, a convenience flag that skips a class of hooks deserves an inventory of
what it skips. `SKIP_AUTOFIX=1` reads like formatting. It is also memory
consistency. The name describes the mechanism, not the blast radius.

Third, an append-only generator is a design choice with a failure mode, and the
failure mode is unreachable stale content. `--preserve` exists to protect
accumulated detail that the source no longer carries, which is a real need, and
the price is that nothing derived can ever be retracted by regeneration alone.
Where that price is paid, the artifact needs a correction path that is not
"run the generator again."

A fourth, smaller finding from the same round is worth recording next to the
round-fourteen entry it corrects. Defect shape 15 produced a refusal naming both
the family bar and the corrected per-comparison bar, and a test asserting both
numbers appear in the reason. Both numbers did appear. Neither was labeled, and
the sentence read as though a word were missing, so a reader could not tell
which number they had asked for and which one the Bonferroni correction had
produced. Asserting that a value appears in a message is not the same as
asserting the message is legible. The test now pins the labels and the
arithmetic, including the family-of-one edge where the two numbers are equal and
the division has to stay visible anyway.

Two later threads in the same round corrected the arithmetic that defect shape
15 rests on, and the correction is worth keeping next to the original. Every
statement of the problem, in the docstring, the README, the ADR, the test
rationale, and the Serena memory, quoted `1 - 0.95**5`, about 0.226, as the
family-wise false accept probability of five consultations at 0.05. That figure
is exact only if the five comparisons are independent. They are not: all five
look at the same selection group, and successive candidates are correlated
edits of one artifact. The dependence-agnostic union bound is `5 * 0.05 = 0.25`.

The conclusion does not move. Both numbers are roughly five times the 0.05 the
operator asked for, so a per-comparison threshold still fails to bound a family
and Bonferroni is still the right correction. What was wrong was the precision:
the text quoted an exact value derived from an assumption the enforcement
deliberately does not make. Bonferroni was chosen precisely because it holds
under any dependence, so citing an independence-only figure to justify it
argued for the mechanism on grounds the mechanism rejects.

The shape generalizes past this file. A number carried into five documents by
copying is corrected in five places or in none, and the one most likely to be
missed is the test docstring, because nobody greps rationale prose when they
change a claim. That is the same tier problem as defect shape 21, one level up:
derived prose drifts from a corrected source exactly like derived artifacts do.

## Round nineteen: a reviewer with no access to the docs

Round nineteen ran on `gpt-5.6-terra`, a model family used in no previous round,
read-only, at extended reasoning. It returned six findings. Two were marked
Critical and both were false positives against the stated threat model. Four
were real and are fixed below.

The two Criticals are the interesting result. The first said the optimizer can
read held-out outcomes directly from `extract` output. The second said
`EVAL_LEDGER_DIR` lets a caller reset the budget. Both are true. Both are also
already written down: the first is ADR-087 Open Requirement 1 and is stated in
`scripts/eval/README.md` under "What the seam does and does not protect", which
ends with the sentence "do not cite a run of this loop as evidence against an
adversarial optimizer". The second is Open Requirement 10, "A ledger root the
loop cannot relocate", and is documented in `_ledger_root`'s own docstring.

That is the disclosure working. A reviewer reading only code will re-report
every deliberately deferred limit as a Critical vulnerability, because from
inside the code there is nothing to distinguish a hole nobody noticed from a
hole somebody measured, wrote down, and left open on purpose. The distinction
lives in the prose. The correct response is not to fix them, since they are the
user's deferred decisions, and not to argue with the reviewer, since the
reviewer is right about the mechanism. It is to check that the disclosure
actually says what it needs to say, which it did, verbatim, in three places.

### Defect shape 22: the count that answers the operator's question was missing where the answer was nonzero

Round nineteen said the verdict's `sel_consultations` was wrong. It was not,
and the way it was wrong is instructive. The reviewer believed the key should
hold the *prior* total; the code's own contract, in the `_corpus_refusal`
docstring, defines `consultations` as this run's charge and `sel_consultations`
as the running total including it. Under that contract the value the reviewer
flagged is correct.

The real defect was next to it. `consultations` was absent from both charged
sites, so the one key answering "what did this run cost me" was missing from
exactly the two verdicts where the answer is not zero. And the ledger-mismatch
refusal emitted `sel_consultations: 0`, a number that is never true: the ledger
was parsed and its count is known by the time the mismatch raises, so zero is
not ignorance, it is a false claim. On a key mismatch that count belongs to a
different selection group, which the refusal deliberately withholds, so absence
is the honest report and zero is not.

`consultations` now appears at every emit site. `sel_consultations` appears only
where the total is both known and this group's. The charged value is derived as
`spent_after - spent` rather than written as a literal `1` in two places,
because this session has already shipped one defect caused by copying a number
into several documents and correcting it in some of them.

### Defect shape 23: cleanup that replaces the failure it cleans up after

`_write_atomic` unlinked its temp file inside a bare `except BaseException`,
with the unlink itself unguarded. `main` catches only `ConfigError`,
`AdapterError`, and `ValueError`, so an `OSError` raised by that unlink escaped
as a traceback, and the traceback named the cleanup rather than the write. A
parent directory whose permissions are revoked after `mkstemp` succeeds fails
both calls, which is exactly the pair that produces it. The unlink is now
suppressed on `OSError` while every other class still escapes, so a real bug in
cleanup is still visible and a cleanup failure can no longer stand in for the
failure it was cleaning up after.

The same handler carried a comment claiming it closed the descriptor when
`os.fdopen` failed. Nothing called `os.close`. The comment described an
intention that was never implemented, and the path leaked a descriptor while
the code above it said otherwise. The reviewer did not report this; it surfaced
while writing the test for the reported half, which is the argument for writing
the test rather than applying the patch.

### Defect shape 24: durable bytes behind a rename that is not

`_write_atomic` fsynced the temp file and then renamed it, and never fsynced the
parent directory. The bytes reached the disk; the directory entry pointing at
them did not have to. A host that loses power after the gate reports a charge
can come back with the rename undone and the consultation available again, for
free.

That is precisely the outcome the charge-before-scoring ordering exists to
prevent. The ordering was chosen so a crash between charging and answering
costs the caller a consultation rather than granting one, and a charge a crash
can erase inverts it. The rename is now followed by a directory fsync, inside
the guarded block so a failure becomes a `ConfigError` document rather than a
traceback. Windows cannot open a directory as a descriptor and `os.replace` is
atomic there regardless, so that platform skips the step; a directory that
opens and then refuses to sync is a different case and is reported, because
claiming a durability guarantee that did not hold is the shape this file keeps
correcting.

### Defect shape 25: a correction stated more strongly than it holds

The fix shipped two rounds earlier said Bonferroni "holds under any
dependence", which is why it was preferred to the sharper
independence-dependent bound. That is half a sentence. Bonferroni controls the
family-wise error rate under arbitrary dependence *among the p-values*, but
only given that each per-comparison p-value is valid on its own. The exact
McNemar tail earns that validity only if the discordant pairs behave as
independent fair coin flips under the null, and correlated scorer noise breaks
it.

This harness has direct evidence that its outcomes are correlated. The
rule-path null control restored the artifact byte for byte and reproduced both
of the gains the real edit had produced. So the unqualified claim overstated a
guarantee in the same document that had just finished correcting an overstated
guarantee, which is the whole shape: a correction is a claim, and it inherits
every obligation the claim it replaced had. All four sites now state the
condition and name the null control as the evidence that the condition is not
free here.

## Round twenty: a durability fix that became an availability regression

Round twenty ran on `gemini-3.1-pro-preview`, a vendor family used in no
previous round, read-only, against code that was three commits old and had had
no review at all. Three findings. Two real, one false.

The false one is worth recording because of how it failed. It claimed
`mcnemar_exact` crashes with `OverflowError` for `n >= 1024`, because `2**n`
exceeds the maximum representable float. Python's int-by-int true division does
not work that way: it divides exactly and rounds the result, so the computation
succeeds whenever the *result* is representable. Checked directly at n = 1023,
1024, 2000 and 5000. At n = 2000 with all pairs in one direction the value
underflows to 0.0, which is the correct answer to float precision and makes the
gate stricter rather than looser. The reviewer asserted a crash it had not run.
The same discipline that caught round nineteen's two false Criticals catches
this: run the claim before filing it, in both directions.

### Defect shape 26: a durability fix that spends what it was protecting

Defect shape 24 added a parent-directory fsync after `os.replace`. Round twenty
pointed out that raising `ConfigError` when that fsync fails is wrong twice
over.

The message was false. It read "could not write <path>", and by the time the
directory sync runs the bytes are written, the mode is set, and the rename has
succeeded. Claiming a failed write when the write succeeded is the same
code-contradicts-prose shape this log has recorded five times.

The behaviour was worse than the message. Before shape 24, `os.replace` was the
last operation in the function, so every failure path preceded the rename and
left the destination untouched: refusing cost the caller nothing. The directory
fsync is the first step that can fail *after* the write has landed, and in the
ledger's case after a consultation has already been charged, since the gate
writes the ledger before it scores. So a raise there spends a look and returns
no verdict. Charging before scoring exists so that a crash costs the caller a
consultation rather than granting one; aborting after the charge is the same
trade pointing the other way, and the fix for one had quietly created the
other.

Staying silent is not the alternative. That leaves the caller believing a
durability guarantee that did not hold, which is what shape 24 existed to stop.
The loss is now named on stderr, which the exit-code contract keeps free while
stdout carries the one JSON document a caller parses, and the write stands.
Every failure that precedes the rename still refuses, and a test pins that
distinction so the change reads as a correction rather than a loosening.

The general shape: a fix that adds a step to a sequence inherits responsibility
for where in the sequence it sits. Shape 24 reasoned about what the new step
guarantees and not about what its failure now costs, and the cost was created
entirely by the position, not by the step.

### Defect shape 27: advice that names an invocation the parser rejects

The exhausted-budget refusal ended "refresh the split or report on the test
group". `score --group` accepts only `opt`, and argparse rejects anything else
before the command runs. So an operator who had just run out of budget was
directed into a dead end that the tool statically refuses.

The interesting part is which way to fix it. Widening the choice would make the
sentence true and would also hand the loop unmetered reads of the one group
held back as a final unbiased look, and "`score --group opt` refuses to read
any other group" is listed in the README among the properties enforced whether
or not the optimizer cooperates. Making a message true by weakening the
boundary it describes is not a fix.

So the advice is removed and the gap it pointed at is filed as #3552. The
methodological point behind the sentence is sound: after a selection budget is
spent, the honest number is one read of a group no selection decision has
touched. The CLI has no path to that read. That is a missing capability, not a
wrong string, and it belongs on the Open Requirements list rather than in the
PR that found the symptom.

Shapes 26 and 27 share a root with much of this log. Prose asserted something
the mechanism did not do. What is new is that in both cases the honest repair
was to change the mechanism's *contract* rather than its words: shape 26 by
deciding what a post-rename failure should cost, shape 27 by deciding that the
boundary outranks the sentence describing it.

### Defect shape 28: a diagnostic held to weaker rules than the thing it reports

Shape 26 replaced a raise with a warning: the rename had already succeeded, so
aborting spent a consultation to report a stronger guarantee than the caller
needed. The fix was right about the cost and wrong about what a warning is.

Two properties the raise path already had did not follow it across.

The first is that it cannot fail. `print` raises when stderr is closed, and the
enclosing writer converts any `OSError` from that region into a refusal. So the
abort shape 26 removed came back in through the diagnostic reporting on its
absence. Round twenty-one demonstrated it with a stderr whose `write` raises
errno 32 rather than arguing it from the source, which is why it survived
triage where several louder claims did not.

The second is that it must redact. The redaction seam is a context manager over
*raised* exceptions: it catches, scrubs the holdout key out of the message, and
re-raises. A diagnostic that prints and returns never enters it, so a
digest-bearing ledger root printed in full. The seam's own docstring had
predicted this, in the sentence explaining why it exists: "a wrapper covers the
paths someone remembered; a seam covers the one added next year." The tenth
review had already fixed this leak by hand at a different warning site. Shape 26
added a second site and the hand-fix did not generalize, which is the exact
failure the seam was introduced to prevent.

The repair is one helper both sites call. It takes no key. It reads the key
published by the active scrub through a module global, because the caller who
has no key to pass is precisely the caller who will leak, and a parameter is
another thing the next author has to remember. The print runs under suppressed
`OSError`.

The generalization worth carrying: when a failure path is downgraded to a
diagnostic, the diagnostic inherits every obligation the failure had. It is not
a lesser thing that gets lesser rules. Here that meant it must not disclose what
the raise redacts, and must not fail where the code it reports on succeeded.
Routing both sites through the helper also fixed the older unguarded print,
which had been repaired for leakage only and still carried the crash.

Twenty-one rounds in, every round has found a defect in the previous round's
fix. That is now the strongest evidence in this log for the review discipline
itself: the defect rate per round has not fallen, but the defects have moved
from the mechanism to its edges, and each round's finding has been smaller and
more specific than the last.

### Defect shape 29: guarding the exception, not the rule

Shape 28 gave the warning back the two properties the raise path already had.
Round twenty-two showed that the fix had bought the demonstration rather than
the property.

Shape 28's evidence was a stderr whose `write` raises errno 32, so the fix
suppressed `OSError`. A stream closed for real raises `ValueError: I/O
operation on closed file`, which is not an `OSError`. Closing an `io.StringIO`
and warning through it aborted a write that had already succeeded, which is the
outcome shape 26 and shape 28 were both written to prevent. The demonstration
was inside the guard and the rule was outside it.

The worse half was not a crash at all. `sys.stderr` is `None` in an embedded or
windowed interpreter, and `print(file=None)` does not skip the write. It falls
back to stdout, which is the stream carrying the JSON verdict. A caller piping
the CLI into a parser would have received a warning spliced into its payload.
Nothing raises, nothing logs, and the redaction is irrelevant because the leak
is not the failure. That is a third rule the warning has to hold, and neither
of the two earlier rounds had stated it: a diagnostic must not land on the
stream carrying the result.

The repair is stated as three named rules in the function's own docstring
rather than as three handled cases, because the previous two rounds each
handled the case in front of them and each left the next one open.

### Defect shape 30: a coverage claim no test backed

Round twenty-two also read round twenty-one's tests instead of its prose. The
commit message, the session log, and the PR body all said the fix was covered
"at both sites" and "under nesting". All eight of the tests drove
`_write_atomic`. None touched the lock-cleanup warning site, and none nested a
scrub inside another.

The code was correct at both sites; the claim about the evidence was not. That
distinction is what makes this a separate shape from the prose-versus-mechanism
failures in shapes 21, 26, and 27. Those were documents describing a mechanism
that did not match. This one is a document describing *the tests*, which is the
one claim a reader cannot check by reading the code.

The repair adds the two missing tests rather than removing the sentence, and
records the correction as a new session-log phase rather than editing the false
phase into truth. A log that silently repairs its own errors cannot be used as
evidence about the process that produced them.

### A test that could not fail, caught before it shipped

The first draft of the context-isolation test used two threads and a barrier,
and passed against the module global it was written to rule out. The reasoning
said it must fail: the barrier forces both scopes open before either reads, so
a shared global has been written twice and both readers see the second write.

The reasoning was right about the writes and wrong about the reads. The barrier
releases both threads, but they still run one at a time, and the second thread
finished its `finally` restore before the first resumed. Each then read its own
key, from a genuinely shared variable, by scheduling luck. Instrumenting the
interleaving is what showed this; three rounds of staring at the source did
not.

Round sixteen found a test asserting a digest was absent from an already
drained buffer. This is the same shape from a different direction: not a
vacuous assertion, but a real assertion the runtime declined to exercise. Both
report as covered. `copy_context` asks the same question with the scheduler
removed, and fails against the global deterministically.

The rule this adds to the mutation discipline already in use here: a test whose
discriminating power depends on scheduling has not been shown to discriminate
by passing once under mutation, or by failing once. It has to be made
deterministic or deleted.

Twenty-two rounds in, every round has still found a defect in the previous
round's fix. Round twenty-two is the first to find a defect in the previous
round's *evidence* rather than its code, which is the failure mode this log
exists to make expensive.

### Defect shape 31: the docstring found the bug the reviewer did not

Round twenty-two's `_warn` fix left `_scrub` outside the suppression and the
`print` inside it. Four reviewers had looked at that function by then and none
flagged it. Writing the sentence that justified the split is what broke it: the
draft said a redaction that fails must fail loudly rather than leak, and neither
half survived being written down.

A redaction that raises leaves the message unprinted either way, because the
exception skips the `print` with `message` still bound to its unscrubbed value.
So the split bought no leak protection. What it bought was a `_warn` that raises
from inside `_fsync_dir` after a rename has already succeeded, which is the
abort shapes 26, 28 and 29 were each spent removing, reintroduced by the fix
for shape 29.

The lesson is narrow and worth keeping. Prose that merely restates the code
catches nothing; prose that has to justify a choice will sometimes fail to, and
that failure is a finding. Three of the four rules `_warn` now states were
discovered by a reviewer. The fourth was discovered by trying to write down why
the third was implemented the way it was.

### Defect shape 32: a proposed fix is a claim like any other

Round twenty-three raised one Optional finding and it was structurally right:
the context-isolation test drove the `ContextVar` directly, so it exercised the
standard library rather than this module's scope. Its proposed repair, abandoning
a generator mid-scope through the public API, does not discriminate as written.
CPython drops the generator's last reference when the helper returns, closes it,
and runs the very `finally` the test needs left undone, so the test passes
against the module global it exists to rule out.

The review's mutation was weaker than it appeared for the same reason its fix
was: rebinding the module attribute to `None` breaks attribute access rather
than behavior, so every test touching the variable raises `AttributeError`. That
is not evidence about sharing. A mutation has to preserve the API and change
only the property under test, which is why the mutation used here is a
hand-rolled class with `get`, `set` and `reset`.

Both halves were settled by running them, in the same review round, against the
same two implementations. This log has three entries now about claims that were
argued rather than measured (shape 20's error contract, round twenty's
`OverflowError`, and this one). Two of the three came from reviewers and one
from the author, which is roughly the ratio of who writes claims here.

Taking the finding and rejecting its patch also surfaced something neither party
was looking for. Closing the abandoned generator from outside its context makes
`reset` refuse a foreign token with `ValueError`, which pytest reports as an
unraisable-exception warning. A token has a limitation the module global did not:
a scope entered in one context cannot be exited in another. Nothing in this CLI
can reach it, since every scope is a plain `with` in straight-line synchronous
code, so `_digest_scrubbed` discloses it next to the non-LIFO limitation it
already disclosed rather than guarding a path no call site has.

### Defect shape 33: the last expression nobody guarded

Four rounds in a row fixed the same rule at a different site. Round twenty found
a warning that aborted the write it was reporting on. Round twenty-one found the
guard was written to the exception the reviewer had raised rather than the class
of exceptions the rule covers. Round twenty-two found the same abort at the
second warning site and a stream whose `None` value redirected the diagnostic
onto the stream carrying the verdict. Round twenty-three moved the redaction
inside the guard after the sentence justifying its exclusion turned out false.

Round twenty-four found the abort still reachable, through the one expression
none of the four had looked at: the read of the stream itself. `sys.stderr` is
an attribute lookup. A harness that deletes it rather than blanking it raises
`AttributeError` before the guard is entered, from a line whose whole job was to
decide whether the guard should run, and it raises after the rename it is
reporting about has already succeeded.

The shape is narrower than "the guard was too small" and worth naming
separately. Each earlier round moved a statement into the guard. This one is
about an expression that was never a candidate for moving, because it reads as
a fetch rather than as work. Every reviewer, and the author, read
`stream = sys.stderr` as retrieving a value. It is a call into `sys.__dict__`
that can fail, and the docstring asserting that only the *check* sat outside the
guard is what makes the omission legible: the *read* sat outside it too, and the
sentence was false for a second time in two rounds by the same mechanism as
shape 31.

The repair adds no control flow. `getattr(sys, "stderr", None)` routes the
missing attribute into the `None` branch that already existed and was already
tested, so one expression becomes total and nothing new has to be maintained.
That is the reason to take it rather than file it. This repository's rules
forbid error handling for unreachable paths, and a deleted `sys.stderr` is
close to unreachable. But this is not error handling: it is the difference
between a partial and a total read of a value the function already branches on.

Two things about the round are worth keeping. The finding arrived labelled Nit,
attached to an otherwise clean verdict, from the same reviewer whose previous
patch had been measured and rejected; severity labels from reviewers are
estimates about importance, not about correctness, and this one was
under-labelled. And it was reproduced before it was believed, which took one
test and produced the red half of the fix for free.

## Shape 34: the sentence describing the guard was still short by one read

Round twenty-five was the first substantively clean verdict of the campaign. It
answered all five questions asked of it, labelled each as verified by running or
by reading, and probed `ContextVar` semantics rather than asserting them. It
found nothing in the code, and that reading survives: the code is correct.

The finding is in what it declined to count. Asked whether every sentence of the
amended `_warn` docstring was true, it reported that the key read is also
lexically outside the guard, then set that aside as shorthand rather than a
defect, on the ground that the read cannot raise. The ground is sound. The
conclusion does not follow, and this is the third round running in which the
docstring asserted something the code did not do.

The sentence said only the stream check sat outside the guard. Two reads sit
outside it. A reader who takes the sentence literally believes the key read is
protected. It is not protected; it is safe, which is a different property held
up by a different line. `_ACTIVE_HOLDOUT_KEY` is declared with `default=None`
fifty lines above the read that depends on it, and a `ContextVar` without a
default raises `LookupError` from `get()` outside a set scope. That is the same
abort class rounds twenty through twenty-four were each spent removing, reachable
by deleting one keyword argument on a line no docstring pointed at.

Two measurements decided the shape of the repair. Removing the default turns
thirteen tests red, so the invariant is genuinely pinned and the risk is smaller
than it first reads. But every one of those thirteen is a diagnostic test about
stderr or scrubbing, and not one names the constructor argument that caused it,
so the editor who removes the argument gets thirteen failures pointing away from
the edit. The repair is therefore prose plus one assertion: the docstring names
both reads and the reason the second is total, and a test named for the invariant
fails with `LookupError: <ContextVar name='_ACTIVE_HOLDOUT_KEY'>` so the cause is
in the failure rather than inferred from thirteen symptoms.

The generalisation is about reviewers rather than about guards. A reviewer that
notices a discrepancy and classifies it as not-a-defect has done the expensive
half of the work and stopped before the cheap half. Round twenty-four's finding
arrived under-labelled as a Nit. Round twenty-five's arrived labelled as not a
finding at all, inside an otherwise correct clean verdict, which is the harder
version of the same failure to catch: the verdict is right about the code and
wrong about the artifact the next editor will read.

## Shape 35: the sixth answer was that the question was avoidable

Round twenty-six was asked to audit round twenty-five's correction rather than
the code, on the grounds that the docstring had been false in three consecutive
rounds, each time immediately after someone corrected it. It found four things
and was right about three, and the one it was least sure of was the one worth
acting on.

Its literal reading is correct and the correction over-claimed. "Two reads sit
outside the guard" is false if read as a count of what Python evaluates before
the guard is active: the `suppress` and `Exception` lookups, the constructor
call, and `__enter__` are all out there too. Its distance check is also correct
and is the better lesson: the docstring said the declaration sat fifty lines
above the read and it sits sixty, because a number in a docstring is a claim
like any other and this one was never checked. Both of those are fixed by the
paragraph no longer existing.

The finding underneath them is that the key read had no reason to be outside
the guard. Six rounds had been spent answering "why is this one safe" about a
different expression each time, and the sixth answer is that the question was
avoidable. The key is read in exactly two places, both inside the guard, so
moving the read to its uses costs nothing and removes the need to justify it.
The stream read stays outside because it decides the early return that keeps
the message off stdout, which is a reason the key read never had. The
distinction is the point: one expression is outside for a reason and the other
was outside by habit, and five rounds of documenting the habit did not make it
a reason.

The improvement was measured rather than argued. Before the move, deleting
`default=None` from the `ContextVar` raised `LookupError` out of `_warn` and
failed thirteen tests. After it, the same deletion loses the warning, fails
six, and the caller returns normally. That is the same conversion from abort to
lost diagnostic that rounds twenty through twenty-five each performed at one
site, done once at the level of the function's shape.

Two smaller things carried over. The test added in round twenty-five contained
an assertion that built an unrelated `ContextVar` and checked that `get()`
raises, which verifies CPython and not this repository; round twenty-six called
it a tautology and it is deleted. And the count in the surviving prose had to
be re-measured after the move, because the number that made the argument in one
round stopped being true in the next, which is the same failure mode as the
line distance, one round later and caught before shipping this time.

### Coda: the paragraph was the wrong shape, not the wrong wording

Four rounds corrected this docstring and four corrections were falsified, which
is a rate high enough to be about the artifact rather than about the readers.
The common factor across all four is that the paragraph asserted quantities:
how many expressions sat outside the guard, how far the declaration sat from
the read, how many tests failed without it. Each was true when written. Each
was falsifiable by an edit somewhere else in the file, and two of them were
falsified by the very commit that corrected the previous one.

Structural claims do not behave this way. "The stream read decides the early
return, so it has to be outside the guard" is falsified only by editing this
function, which is exactly when someone is reading the docstring anyway. A
count is falsified by adding a test two thousand lines away.

So the counts moved to this log, which carries dates and is understood to be a
record of what was true at a moment, and the docstring kept the claims that a
reader of the function can check against the function. That is a smaller
docstring making fewer promises, which is the opposite of the instinct each of
the previous four rounds followed.

## Shape 36: advice that names a value the refusing input may not carry

A bot reviewer read the corpus refusal and objected to its second sentence:
"Re-score both artifacts against the corpus the split was drawn from and gate
again." Its argument was that a split can be created without a corpus pin, a
`--tasks` split for example, so that advice names something the operator does
not have.

The predicate agrees. `_corpus_conflict` refuses when more than one corpus is
declared across the split, the incumbent, and the candidate, and the split's
missing key is dropped before counting rather than treated as a value. So
`(_UNPINNED, SHA_A, SHA_B)` refuses, and that row is a pinless split beside two
results that disagree. Both the parametrised truth table and an end to end test
named `test_one_known_corpus_beside_an_unknown_one_conflicts_without_a_pin`
already covered the path. Neither covered what the refusal told that caller to
do next.

The interesting part is what the correct wording is not. The obvious repair is
"re-score both artifacts against one corpus", and that is wrong in the other
direction: when the split does pin a digest, re-scoring both files against some
other single corpus still leaves two declared values and still refuses. A
procedure phrased for one input shape is wrong for the other, and this refusal
serves both.

So the advice stopped being a procedure and became the rule: "Re-score both
artifacts so that only one corpus is named across all three, and gate again."
That sentence is the negation of the predicate directly above it. It names no
file to copy a value from, so there is no value for an input to be missing, and
it can only be falsified by editing `_corpus_conflict`, which is the one edit
that puts a reader in front of this function anyway.

That last property is the coda to shape thirty-five applied to a runtime string
rather than a docstring. The claims that rot are the ones a reader checks
against something other than the code beside them.

The README quotes this reason in a transcript and stops after the first
sentence, so it carried no stale copy. The only other match in the trees is a
dated entry in this log paraphrasing the advice as it stood, which is what a
dated log is for.

## Shape 37: a rule stated for two of the four keys it governs

Round twenty-seven (gemini-3.1-pro-preview) was pointed at what the gate
decides rather than at the diagnostic helper the previous seven rounds had
circled. It cleared the decision paths: no contamination, no off by one in the
slice boundaries, ties refuse, the Bonferroni family size is the declared cap,
the adapters raise on duplicate ids instead of dropping one, and errored tasks
record as failures rather than vanishing from the denominator. It also read the
sentinel correctly and said why it is load bearing.

Its one finding was that the REJECT payload has three shapes. That is true. An
AST pass over every emit site confirms it: the refusals decided before the lock
carry four keys, a ledger key mismatch carries six, the guard and coverage
refusals carry seven, and a verdict carries sixteen.

The proposed fix was to fill every refusal in, including by querying the ledger
so the preflight could report `sel_consultations`. Both halves of that were
already settled here and written down. Round seventeen removed
`sel_consultations` from the corpus recheck because a key set alone told the
caller which of the two reads caught the disagreement, and round nineteen fixed
the opposite failure, a key that was missing exactly where its answer was
nonzero. The README states the resulting rule: a document carries the facts the
site emitting it can state honestly, and an absent key is the honest answer
rather than a gap.

Measuring the other half of the proposal was more useful than arguing with it.
Applying it to the drift refusal, so that payload carries `group` and
`fingerprint`, produces this:

```text
"fingerprint": "0000...0000", "group": "sel", "reason": "split fingerprint does
not match the split file's own contents..."
```

The document reports a fingerprint beside a sentence saying that fingerprint
does not describe the file. The drift check is the thing that disproved the
value, so echoing it is the one field that site cannot state honestly.

So the finding was right about the observation and wrong about the remedy, and
the reason it was wrong is the part worth keeping. The README stated the
presence rule for `consultations` and `sel_consultations`, and both have a test
class. `group` and `fingerprint` vary the same way and had neither. A careful
reader given the payloads and no rule reaches exactly the conclusion this round
reached. Before this commit, applying the proposed fix broke nothing; after it,
it breaks two tests.

That is the shape: a contract documented for some of the keys it governs reads
as an accident at the keys it skipped. The rule now covers all four, and the
new class pins the one exception with its reason, which is that the corpus
refusal is a single document emitted from both sides of the lock and can carry
only what the earlier side can say.

## Shape 38: the reader that named the check it did not run

Shape 37 ended with a rule: a document carries the facts the site emitting it
can state honestly, and an absent key is the honest answer rather than a gap.
That rule was written from four keys in one command, which is a small sample to
generalise from, so round twenty-seven was asked the obvious next question.
Does any other emitted field carry a value some site cannot state honestly, and
is there a fifth field whose presence varies under no rule and no test? It was
told to enumerate the emit sites by reading them rather than infer from the
four it had been handed, and that a negative answer with the enumeration shown
would be worth more than another finding.

It found one, and it ran it rather than describing it.

`cmd_score` reads the split and prints `split["fingerprint"]` beside the score.
The comment above that line says why the fingerprint rides along: `gate`
requires it, and `score` is the only command that reads the split on the
caller's behalf, so without the echo the caller has to open the split file to
satisfy a required flag. What no line said is that `cmd_score` never checks
whether the fingerprint still describes the file. `cmd_gate` does, on the line
immediately after its read. `_split_drifted` has exactly one caller, and
`_read_split` has exactly two.

Reproduced on a real split rather than a fabricated one, because a hand-written
file with a fake digest proves less than the edit an operator would actually
make. Draw a split, drop one task from `opt`, leave the fingerprint alone, and
score both:

```text
{"fingerprint": "77e97462...", "group": "opt", "n": 6, "score": 0.333}
{"fingerprint": "77e97462...", "group": "opt", "n": 5, "score": 0.200}
```

One fingerprint, two different splits. That is the confusion the fingerprint
exists to prevent, produced by the command whose output feeds it forward.

The severity has a ceiling and it is worth stating rather than leaving to the
reader. The gate runs the check, so the tampered split is rejected and no
unsound verdict is reachable. The cost is entirely in where the operator finds
out. `gate` sits at the end of a step that has already paid for a candidate,
so a check that fires only there charges real budget for the discovery, and an
operator scoring several candidates against a broken split pays for each one.

The sharpest form of the defect is in `_read_split` itself. It refuses a file
missing any key needed to re-fingerprint it, and the message it raises says the
reason: a split file that cannot be re-fingerprinted cannot be verified. It
collects exactly the keys verification needs, says that is why it wants them,
and then does not verify. `cmd_gate` covered that by hand and `cmd_score` did
not, which is what an unenforced convention looks like when it has two callers.

The check did not move into the reader, and that is deliberate. `cmd_gate` has
to emit `decision: REJECT` on drift because its caller is a loop that branches
on the document, and a reader that raised would turn that verdict into an error
document. So the repair is at the one site that lacked it, reported the way
that site already reports a malformed split: `ConfigError`, exit 2. The two
commands now refuse the same condition in two vocabularies on purpose, and both
end on the same remedy sentence so the operator reads one instruction.

Confirmed by mutation rather than by the red-green run, because the first
red was against the wrong assertion shape and proved nothing. `main` catches
`ConfigError` and emits a document, so the tests assert on an exit code and a
payload rather than on `SystemExit`. With the corrected assertions the fix
removed turns four of the five red, and the fifth is the positive control
proving the check costs an honest caller nothing.

Round twenty-seven's other answer was that five fields vary across the three
`cmd_apply` sites under no rule and no test. That was read and left alone.
Those three documents are a tagged union discriminated by the keys present, and
every field each site omits is one the site could state honestly, which is the
opposite of the `fingerprint` case: `applied` is on all three and already
carries what a caller needs. An absence that hides nothing is not the defect
this rule was written about, and widening the rule to cover mere variation
would make it a schema-uniformity rule, which is the argument shape round
twenty-seven's first proposal was rejected for.

## Shape 39: the guard defeated by the line below it

Round twenty-nine was pointed at the newest code, since three consecutive
rounds had touched `cmd_score` and no fresh reader had seen the result. It
found that a split file holding a list where the fingerprint belongs kills the
process with a `TypeError` instead of refusing the file.

The interesting part is not that a malformed field crashes. It is that the code
had already decided it should not. `_split_drifted` wraps its redraw in
`except (TypeError, ValueError)` and converts either into a `ConfigError`, so
the author had considered this exact class and ruled on it. Two values walked
through the ruling anyway, each on a technicality.

The fingerprint comparison sits one line below the `except`, outside the block.
So `split["fingerprint"] not in compatible_fingerprints` raises the very
`TypeError` the clause names, two lines after the clause stops applying. The
guard was defeated by scope, not by omission. And `int(split["min_sel"])` on a
JSON `Infinity` raises `OverflowError`, which is a sibling of `ValueError`
rather than a subclass, so a clause written to catch unusable numbers missed
the most obviously unusable number there is.

The class was enumerated rather than accepted at the two instances reported,
by fuzzing every field of a real split with twelve wrong-typed values and
recording what failed to exit 0 or 2:

```text
fingerprint   list          exit=1  TypeError: unhashable type: 'list'
fingerprint   dict          exit=1  TypeError: unhashable type: 'dict'
fingerprint   list_of_list  exit=1  TypeError: unhashable type: 'list'
fingerprint   list_of_int   exit=1  TypeError: unhashable type: 'list'
min_sel       huge          exit=1  OverflowError: float infinity to int
total escaping: 5
```

Two fields, and the reading agrees with the running: those are the only two
operations that touch a caller-supplied value outside a guard. Every group is
already validated as a list of strings on the way in, and the ratios and seed
are inside the block.

The precedent for the repair was already in the same function. `_read_split`
validates the optional `corpus` pin, and the comment above that call records
why: unvalidated, "a list pin raised `TypeError` out of a set comprehension".
That is this bug, found and fixed once, in this function, for the neighbouring
field. `fingerprint` sat two lines away and went unfixed. So the check goes
beside its twin rather than into a new validator, and `OverflowError` joins the
clause that was already trying to catch it.

The harm has a low ceiling and saying so is part of the finding. Both commands
die before any comparison, so no unsound ACCEPT and no consultation charge is
reachable, and the tampering requires an operator to hand-edit their own split
file. What is actually lost is the contract, and the README had already written
it down: "Every verdict path prints JSON, so a caller that needs to tell a
reject from a broken input reads `decision` rather than inferring from the
code." A traceback prints no JSON and exits 1, which is the code that means the
candidate lost. A loop branching on the exit code could not tell a lost
candidate from an unreadable file. The document was right and the code was
wrong, which is the second time in three rounds that the fix was to make the
code agree with prose that already existed.

Round twenty-eight widened this from one command to two. `cmd_gate` has called
`_split_drifted` since the first commit; `cmd_score` began calling it one
commit before this one, so a fix that was owed to the older caller became owed
to a caller this branch created.

Both halves were falsified separately, because a two-part fix verified as a
unit proves only that at least one part works. M12 removes the fingerprint
check and turns three red. M13 removes `OverflowError` and turns one red. The
two remaining tests are controls: an honest split still scores, and a
fingerprint that is a usable string but simply wrong still reports drift rather
than becoming a config error, which is the case the drift refusal exists for.

## Shape 40: the guard runs after the money is spent

Round twenty-nine was asked for the general form of its own finding: enumerate
every `try` block in all three modules and answer, for each, whether an
operation that can raise a caught class sits outside the block, and whether the
except tuple omits a sibling of a class it names. It returned all twenty-six
blocks with a per-block verdict, and two of them failed. Both failures were the
same shape as shape 39, one argument surface further out.

The important one is not that `gate` crashes on a cap too large to convert to a
float. It is where the crash lands. `cmd_gate` charges the consultation to the
held-out ledger before it reads the held-out group, and that ordering is
deliberate: the comment above the write records that a crash between scoring
and the write left the group read and the consultation unrecorded, so a retry
got the comparison for free. The Bonferroni correction then divides `--max-p`
by the cap, and that division sits outside the `try` that wraps the comparison.

So the measured consequence of one mistyped argument is not a lost verdict. The
run exits 1 with a traceback and an empty stdout, having durably written
`consultations: 1` and a four-hundred-digit `max_consultations` into the
ledger. Every later run against that group is then refused, because the cap
recorded at the start no longer matches the cap being asked for, and the remedy
that refusal offers is to re-split. Re-splitting destroys the held-out group.
One typo permanently bricks the scarce resource the gate exists to protect.

That is why the fix is at the argument boundary and not at the three division
sites. Parsing finishes before any command runs, so a value refused during
parsing has charged nothing. A value caught at the division has already been
written to the ledger, and catching it there would have to unwind a durable
atomic write, which is the guarantee the write exists to provide.

The fix refuses what the arithmetic cannot carry, not what a policy dislikes.
No rule here says a budget of 10 ** 300 is wrong, and a test pins that it is
accepted, because inventing a smaller ceiling would be a policy decision
wearing a bug fix's clothes.

The method note is worth more than the fix. The first fuzz varied one argument
at a time and reported that only two of the four budget integers crashed;
`--step` exited 0 and `--min-edits` exited 2. Both escaped only because an
ordering check fired first. Pairing them so the semantic check passes
(`--min-edits BIG --max-edits BIGGER`, `--step BIG --total BIGGER`) crashes
both. A single-variable fuzz under-reported the class by half. The enumeration
was right where the sampling was wrong, which is the same lesson as shape 39
from the opposite direction: there, running confirmed what reading found; here,
reading corrected what running missed.

## Shape 41: a crash that borrowed the exit code of a real verdict

Round thirty was pointed at the argument and input boundary, the one surface
twenty-nine rounds of internal review had not systematically covered, and was
told to enumerate rather than sample. It returned a per-argument verdict for
every subcommand and every JSON field, confirmed that nothing between the
ledger write and the printed verdict can fail for a reason other than a
deliberate refusal, confirmed no input reaches an unsound ACCEPT, and found two
defects.

The first was reported as a crash: `buffer-add` and `buffer-check` pass patches
straight to `patch_fingerprint` without the field check `apply_patches` runs, so
a patch whose `text` is a number dies with an `AttributeError` out of
`_normalize_newlines`. That is true, and it is not the interesting part.

`buffer-check` returns exit 1 to mean the edit has been tried before. An
uncaught exception also leaves the process at 1. The README publishes the loop
that reads it:

```
case $? in
  0) ;;
  1) continue ;;
  *) exit 2 ;;
esac
```

So the crash did not stop the loop. It took the branch labelled "already
rejected, skip it" and the loop moved on, having silently skipped an edit it
never evaluated. The README's own comment states the contract the code broke:
"Exit 1 means this edit was already rejected, so skip it. Exit 2 means the
command itself failed and the loop must stop rather than treat a typo in a path
as a clean finish." The document was right and the code was wrong, which is now
the third time in four rounds that the fix was to make the code agree with prose
that already existed. A crash is bounded when its exit code means nothing. This
one collided with a verdict, so it produced a wrong answer instead of no answer.

The guard went into `patch_fingerprint` rather than into the two commands that
were reported. Every path that can crash routes through that function,
including `buffer_contains`, and a caller added later would need it too. Fixing
the two named callers would have left the shared function still assuming fields
it never checked. `_check_patch_fields` already ruled this class is a named
refusal, and its docstring says the point is that "the CLI can report it as a
shape problem", naming the CLI rather than one command; one of three entry
points honored it.

The second finding is the same taxonomy as shape 39, one layer out. `cmd_apply`
wraps `apply_patches` in `except ValueError` under a comment that names exactly
what the block is for: "A refused patch is a decision the loop branches on, not
a crash." A negative `--budget` raises `ValueError` from inside that call, so an
operator's argument error was published as `applied: 0`, telling the loop its
candidate proposed an unusable edit when the candidate did nothing. The check
now sits ahead of the try and answers with a `ConfigError`, matching how a
negative `--min-sel` has always been answered.

Both were falsified separately. M15 drops the fingerprint guard and turns five
red. M16 drops the budget check and turns one red. Four of the ten tests are
controls: a genuinely seen patch still reports seen at exit 1, an unseen one
still reports unseen at exit 0, a patch that genuinely cannot apply still
reports `applied: 0`, and a budget of zero is still a budget error rather than
an argument error, since the bar is negative rather than falsy.

## Shape 42: the analysis was already written, about the wrong file

The codebase already contained the correct diagnosis of this defect. It sat in
`_ledger_held`'s docstring, one screen above the function that had the bug:
"two gates started together both read the same count, both compare, and both
write count + 1", and "atomic replacement keeps the file whole; it does not
make the read-modify-write sequence a transaction." An author reasoned the
class through, fixed the ledger, and did not look at the other file in the same
module that performs the same sequence. `cmd_buffer_add` read the buffer,
appended, and replaced it with no lock at all.

The cost is asymmetric and worth stating precisely, because overstating it
would be its own defect. It does not break soundness: the ledger still caps
consultations, so no comparison runs uncharged. Losing an entry costs one
duplicate rollout, which is the cheap side of a tradeoff `patch_fingerprint`
already makes deliberately. The sharper half is the report. Both callers were
told `added: true` when one entry had been discarded, so a loop that reads the
field and moves on believes a rejection is recorded that is not.

A natural race did not prove the race. Two concurrent `buffer-add` processes
lost nothing across repeated attempts, because roughly 1.5 seconds of
interpreter and import startup dominates a read-write window measured in
microseconds. Only a forced interleaving reproduced it: a barrier between the
read and the write put both callers on the same list, and one append vanished.
The lesson generalizes past this defect. A race that does not reproduce under
load has not been shown absent; it has been shown unlikely on the machine that
ran it, which is not the property anyone wanted. The committed tests therefore
assert the property directly rather than racing: they record whether the lock
file exists at the moment of the read and at the moment of the write.

The fix extracts `_lock_held` rather than copying the ledger's twenty-five
lines. Duplicating them would have set the identical trap a second time, and
the general form of this very defect is that a shared mechanism was fixed in
one instance and not the other. The decision was not free: `_ledger_held` cites
twenty-one prior reviews inside its body, and moving reviewed code is how
reviewed behavior gets lost. What made it acceptable was the safety net, not
confidence. Existing tests pin contention, the withheld name, both release
paths, and the descriptor's release on a failed write, and mutation M18 was run
to confirm they still bind after the move: dropping the nested `finally` around
the pid write turns exactly the test that pins it red.

One property inverts between the two callers, which is why the messages are
parameters rather than constants. The ledger withholds its lock's filename
because that name digests held-out membership and an unsalted digest of an
enumerable set is that set. A buffer's path arrived on the command line, so
withholding it buys nothing and turns a stale lock into a puzzle. Both
directions are pinned by tests.

`cmd_buffer_check` deliberately takes no lock. `_write_atomic` replaces the
file, so a reader sees the whole old document or the whole new one, and
serializing readers would let a stale lock block the question the loop asks
most often. A control test pins that too.

Coverage found what review did not. Sharing the helper gave the buffer a
release path the ledger already had tests for and the buffer had none, and the
line report named it: one uncovered line, the buffer's cleanup warning. Five
tests now drive it. That is the argument for holding a hundred percent as a
floor rather than a score. At ninety-nine percent the uncovered line is
invisible.

M17 drops the buffer's lock and turns the three defect tests red. M18 drops the
pid write's nested `finally` in the extracted helper and turns the ledger's
descriptor test red. M19 drops the cleanup warning and turns six red, four
ledger and two buffer, which is the check that the shared helper is genuinely
shared rather than shared in name.

## Shape 43: the same defect inverted, and a reviewer as the witness

Round 32 ran on a third model family against the two surfaces still marked NOT
CHECKED: the adapter layer and artifact-to-results provenance. It returned two
Criticals. Both were rejected, and one of them was worth more rejected than it
would have been accepted.

The second is disposed of quickly. It restated ADR-087 Open Requirement 2 in
its own words: nothing proves `candidate.json` was produced by the edit under
test. That is true, known, written down, and tracked as #3436. The review was
told in its own instructions not to report from that section. This is the third
round in the series to spend itself on already-tracked material, after round 19
quoted the Open Requirements back verbatim as Criticals and round 31 reported a
Windows skip that its own docstring documents. The instruction is necessary and
not sufficient. What would help is unclear; a reviewer that reads the ADR
carefully enough to find the surface is reading the section that already
describes it.

The first is the interesting one. It reported that `extract --kind rule`
refuses a degraded scorer report with exit 2, and argued this overrides the
adapter layer's documented fail-closed design and crashes an autonomous loop on
a transient judge failure. The proposed fix was to delete the refusal.

The finding is wrong and the code is right. Fail-closed and refusal answer the
same threat, which is that a missing measurement must never read as an
improvement, and they differ on what a wasted consultation costs. Scoring a
failed judge as a real failure measures the judge rather than the rule. The
gate would then spend one of a small budget of held-out consultations to reach
a REJECT that carries no information about the candidate, and the budget does
not refund. The rule path is also the one that can least afford the noise: it
is single-shot against an LLM judge, and Open Requirement 6 measured identical
rule text moving 5 of 24 tasks across the pass threshold on a re-run, while the
agent path averages over runs. Exit 2 is the README's own documented signal
that the command failed and the loop must stop.

Applying the reviewer's proposed fix turns seven tests red, six of which
predate this round. A defect whose repair breaks six existing tests written by
earlier reviews is usually not a defect.

What the round produced instead is a real one, and it is the recurring shape
turned inside out. Four times in five rounds the document was right and the
code was wrong. Here the code was right and the document was wrong. The
README's adapter paragraph listed three losses as scoring false together: a
fixture the variant never ran, a scenario whose judge errored, and a skipped
test. Two of the three do. The middle one does not: on the rule path the
extraction is refused outright. The sentence had been read four rounds running
without anyone checking it against the third path.

The evidence that the prose misleads is the review itself. A capable reader,
instructed to verify by running, read that sentence, found the code disagreeing
with it, and filed a Critical against working code. An operator reading the same
sentence would have concluded the same thing with less recourse. A reviewer
misled by prose is a measurement of the prose, not only of the reviewer, and
that is the argument for treating a rejected finding as a finding about
something.

The fix is to the README and to the tests, not to the behavior. The paragraph
now separates the two policies and says why they differ, and four tests pin the
contrast rather than each path alone, since the contrast is what the prose
asserts. The fourth calls `rule_results` directly to pin that the refusal lives
in `extract` and not in the library, so moving the scan down would turn the new
prose false and turn a test red at the same time.

M20 is the reviewer's own proposed fix: delete the refusal. Seven red.

## Shape 44: an extraction can lose a property that was never written down

Round 31 extracted `_lock_held` out of `_ledger_held` and gave it a second
caller. Round 33's reviewer found what that cost. `buffer-add` into an
unwritable directory printed a `PermissionError` traceback and exited 1, where
the module docstring promises a JSON document and where exit 1 is the code the
README reserves for a reject, a decision a shell loop branches on rather than a
crash it stops for. That is the failure mode this whole branch exists to close,
arriving through a door the branch itself opened.

The instance is small. The general form is the finding. Every filesystem call
in this module converts `OSError` into `ConfigError` and says which file:
`_read_buffer` reports "could not read", `_write_atomic` reports "could not
write". Both were checked by running. `_lock_held` is the only one that does
not, and it never had to, because its only caller ran inside `_digest_scrubbed`,
whose entire job is to convert every `OSError` raised anywhere under the ledger.
The helper's safety was a property of where it was called from, not of what it
did. Extraction moved the code and left the property behind.

That the extraction is at fault, rather than the codebase carrying a standing
gap, was settled by running the pre-extraction CLI. `git archive` of the commit
before the buffer lock, against the same unwritable path, returns exit 2 and a
JSON error document. Before: correct. After: traceback. The regression is
authored, and it was authored by the fix for shape 42.

There is a rule in this. A property enforced by a wrapper is invisible at the
site it protects. Nothing at the `os.open` call says "an `OSError` here is
already handled"; the handling is two frames up and in another function, and
the comment that would have said so is in `_digest_scrubbed`'s docstring, which
is where it belongs and where nobody reading `_lock_held` will find it. So the
question to ask before extracting anything is not "does the moved code still
work", which it did, and 423 tests agreed. It is "what was true about this code
only because of where it sat". Coverage cannot ask that question either: the
extraction kept 100 percent throughout, because the uncovered path is one that
no test reached before or after.

The fix converts inside the helper, which is the argument `_digest_scrubbed`
already makes about itself: a wrapper covers the caller someone remembered, a
seam covers the one added next year. `_digest_scrubbed` catches `ConfigError`
as well as `OSError`, so the ledger caller's redaction survives, and a gate
against an unwritable ledger root still reports `<held-out group>.lock` rather
than the digest.

The reviewer's stated impact was wrong and its finding was right. It said the
crash reintroduces "crash can look like a verdict" for callers that branch on
exit codes; `cmd_buffer_add` returns only `EXIT_OK` and has no exit-1 verdict,
so exit 1 there is unambiguously a crash. The harm is the missing document, not
an ambiguous one. Correcting the impact and keeping the finding is the whole
skill: rounds 31 and 32 were both rejected on their stated impact, and this one
would have been too if the impact were the thing being judged.

M21 drops the acquire conversion, 3 red. M22 drops the pid-write conversion, 2
red. M23 lets the generic message swallow contention, 4 red, three of them
written by earlier rounds.

The round's second finding is smaller and the same species. The session log
recorded `endingCommit` twice, top-level against a nested empty string, and the
nested key is not in the schema's `session` properties while `startingCommit`
is. The symmetry was false, which is why nobody questioned it. The top-level
value was also stale by five commits, which the reviewer did not notice and the
verification did.

## Shape 45: the fix that stopped at the calls the reviewer named

Round 33 asked for the general form of each finding and then for an
enumeration of that class across the codebase. It returned four findings, the
best yield of the series, and the first of them was a residual of the fix from
the round before.

Round 32 reported that `_lock_held` could let an `OSError` escape, and named
`os.open` and `os.write`. The fix converted those two calls. `os.close`, one
stage further down the same function, kept escaping raw. The fix had been
aimed at the calls a reviewer listed rather than at the class those calls
belonged to, which is every syscall between acquiring the lock and returning
it. A reviewer's list is a sample. Treating it as the denominator leaves the
same defect one stage down, and the next round finds it there.

The remedy was a restructure, not a patch. Three levels of nested `try`
collapsed to two, and `os.close` sits deliberately outside any `finally`:
when the write has already failed, the write is the cause an operator can act
on, and a `finally` that raised would replace it with the consequence. The
write-failure path releases the descriptor through a helper that suppresses
`OSError`, because POSIX frees the descriptor even when close reports failure.
M24 drops the conversion, 3 red. M25 drops the precedence guard, 1 red.

The round's second finding is sharper than the round stated it. It reported
that an unreadable buffer reads as an empty one and called the result "a
successful unseen answer at exit 0". Measured, the same patch against the same
buffer returns `seen: true` at exit 1 when the buffer is readable and
`seen: false` at exit 0 when the buffer's directory is not. That is a verdict
flip, not a wrong value. An unreadable buffer silently un-rejects every
rejection recorded in it.

`Path.exists()` swallows every `OSError`, so its False answers two different
questions: the file is absent, and whether the file is there is unknowable
because `stat` was refused. A helper now treats only `FileNotFoundError` as
absence and converts every other `OSError` into a config error. Enumerating
rather than sampling: all three modules were grepped for `.exists()`,
`.is_file()` and `.is_dir()`, which found exactly two sites, both converted,
zero remaining.

Half of that finding is latent rather than live, and saying so was worth more
than faking a reproduction. `cmd_gate` takes the ledger lock before it reads
the ledger, in the same directory, so any barrier strong enough to refuse
`stat` on the ledger refuses the lock's `mkdir` one stage earlier. The general
form was fixed and the ledger was tested at unit level with the reachability
written into the test docstring. The first attempt at those tests passed
spuriously: a file whose own mode is `0o000` still stats fine, because only
the parent directory's execute bit gates `stat`. A test that passes for the
wrong reason is worse than one that fails.

The third finding is that pytest emits `<skipped/>` and `<error/>` under one
`<testcase>` when a fixture teardown raises behind a test that skipped, and
the `exclude` skip policy dropped that testcase whole, taking the teardown
error with it. The reviewer verified this from pytest's JUnit source. It was
re-verified by running pytest and asserting on the XML it actually emitted,
which is now the fixture the test uses. `exclude` now drops only a skip that
stands alone. M28, 3 red. M29, 4 red, one of them written by an earlier round.

The fourth finding arrived as "scores are unvalidated" and the mechanism
underneath it is more specific: the documented domain is load-bearing for the
fail-closed property. Inside `[0, 5]` fail-closed already held. A rule
scenario missing its `behavior_score` gets 0 for it, and with the other two at
the legal maximum the mean is 3.33 and fails the 3.5 bar. The same scenario
with the other two at 6 means 4.0 and passes. Only leaving the domain breaks
the property, so the domain is the thing doing the work.

That reframing settled whether enforcement was a contract change. It is not.
The producer documents the range in three places and clamps its own output to
it; the adapter was the only reader that never checked, and a saved results
file reaches the adapter without passing through the clamp. Every producer
agreed on a domain the single reader did not enforce. The bounds are required
keywords rather than defaults, because pass rates are fractions and rule
scores run to 5, and a shared default would be wrong for one of them. M30
removes the rule ceiling, 6 red. M31 removes the agent ceiling, 5 red.

All four findings understated their own impact, in the same direction, while
every finding was real. Rounds 31, 32 and 33 each stated impact wrongly and
were right about the defect. The discipline that survives all six rounds is to
judge the instance and the general form and to re-derive the impact, never to
accept or reject a finding on the sentence describing what it costs.

## Shape 46: the remedy that keeps every assertion green

A reviewer flagged that the round-31 lock tests build their barrier out of
`chmod(0o555)`, which root ignores and Windows does not carry, and proposed
replacing it with a file at the lock's parent path. The premise is right. The
remedy was checked rather than adopted, and checking it found a bug in the
code the tests cover.

Both barriers produce a `ConfigError` at exit 2 naming the lock, so every
assertion in the class stays green under either. They do not reach the same
branch. The read-only directory reports the lock as refused. The file at the
parent path reports that another buffer-add holds it.

The acquire ran two calls under one `try` and read `FileExistsError` as
contention. That is correct for `os.open` with `O_EXCL`, where a lock file
already on disk is the only evidence one holder ever has of another. It is
wrong for `mkdir`, because `exist_ok=True` swallows the error only when what
it found is a directory and re-raises otherwise. A plain file where the lock's
parent belongs raises the same errno 17 with nothing holding anything, and the
operator is told to wait for a process that does not exist or to clear a lock
that was never taken. The one message that would name the real cause is the
one the other branch prints.

Split so each call carries the reading that fits it. Preferred over checking
`is_dir()` inside the handler, which would decide the cause from a second look
at a filesystem that has been free to change since the failure. M32 reverts
the split, 5 red. M33 lets the `mkdir` handler borrow the contention message,
6 red.

The reviewer's stated impact was wrong in the same direction the last three
rounds were wrong, and worth correcting for the same reason. It said the
barrier can silently disappear and leave the test ineffective. It cannot go
quiet: every assertion in the class demands exit 2, and a missing barrier
lets the command reach its ordinary path and return exit 0, so the class fails
loudly. Skipping is still right, because a precondition that is absent should
say so rather than accuse the code, and the same file already had that guard
on its newer tests. Two conventions for one problem is how the older half got
left behind.

What generalizes is narrower than "verify before acting". A remedy is not a
finding, and it does not arrive with the finding's evidence. This one was
sound about the barrier and silently wrong about the branch, and the tests
could not have told anyone, because a test that changes which branch it
exercises while keeping its assertions green reports nothing at all. The same
property that made the substitution invisible is what made the underlying bug
survive: two causes that print at the same exit code, through the same error
class, naming the same path.

## Shape 47: the guard that held by arithmetic rather than by design

A rule report scores each scenario on three keys. The scan that refuses a
degraded report tested the mapping for emptiness. The reduction that turns
the mapping into a number read each key with `get(key, 0)`. Three keys means
eight presence combinations, the scan caught one, and the reduction quietly
filled the other six.

The claim that this is safe is that a missing key scores zero and zero drags
the mean down, so a partial report fails closed. Check the arithmetic. Two
fives and one absent key average 3.33. The default bar is 3.5, so that report
is rejected, and for four rounds that was the whole of the evidence. But
`--min-score` is a documented flag. One absent key clears any bar below 3.34.
Two absent keys clear any bar below 1.67. The property held at one value of a
parameter the operator is invited to change, which is not the property anyone
meant to claim.

The fix is not the clamp. It is asking who could have produced the input.
`eval-rule-activation.py:218` writes all three keys unconditionally, each
through `_clamp_score`, which is `max(0, min(5, n))` and maps a string, a
`None`, or a negative to zero. So the producer cannot emit a partial mapping,
and a partial mapping is therefore a statement about the report rather than
about the candidate. That is what makes it exit 2 and not exit 1: nothing was
measured, so there is no verdict to give. It also explains why zero stays a
legal score. Zero is a value the producer really emits, so it cannot double as
the marker for a value it never wrote.

Both seams needed it, and the mutation says why in one number. M41 removes
the adapter check and takes 19 red. M42 reverts the scan to emptiness alone
and takes only 2. Two looks like a weak test until the two are named: they are
exactly the tests asserting the enumerated, namespaced message. The adapter
refuses the first scenario it cannot reduce and the scan enumerates every one,
so with the adapter still in place the verdict is right and only the diagnostic
is poorer. A low mutation count is evidence when you can say which property it
isolates and evidence of nothing when you cannot.

Writing the tests first surfaced two defects the reviewer had not reported.
`_extract_rules_envelope` collected degraded ids and scored in the same loop,
so an `AdapterError` from the first rule replaced the enumeration of all of
them; it now collects, refuses, then scores, which is what the single-rule
path already did. And a test named for judge-failure verdicts had a fixture
that never matched its own docstring: the prose said every scenario scored,
the fixture gave one scenario a single key. It passed only because a partial
mapping used to look clean. A fixture that contradicts its docstring is a
defect while it is green, and it stays invisible until the contract it
accidentally depends on moves.

Grep found two of the five tests that depended on the old behavior. It is
line-scoped, and a dict literal with its keys on separate lines does not match
a pattern that wants two of them on one. The test run found the other three.
The grep is a head start. The suite is the enumerator.

## Shape 48: the question that resolved before it answered

`_absent` decided whether a file is there by calling `Path.stat` and reading
`FileNotFoundError` as "no". `stat` follows a symlink before it answers, so a
link whose target is gone raised that error and was reported absent, about a
path `ls` displays and `readlink` explains.

Both callers fail open on absence, and each does so for a reason that is right
on its own. A missing buffer is an empty buffer, because nothing has been
rejected yet. A missing ledger is an unspent budget, because no consultation
has been charged yet. Neither reason survives the premise being false. A
dangling buffer link un-rejects every patch recorded in it. A dangling ledger
link resets the consultation count, which is the single integrity property the
ledger exists to hold, and it resets it silently, on a path whose whole purpose
is to start counting from zero.

The way in is not an attack. It is a state directory symlinked onto a volume
that did not mount. The operator has made an ops mistake and wants the run to
stop, not to quietly hand back the budget.

`lstat` asks about the directory entry instead of the target, which is the
question the function was always trying to ask. That alone fixes the verdict.
M45 keeps `lstat` and drops the branch that names the broken link, and three
tests go red rather than none, which is the interesting part: two of them are
about the message, and the third is the symlink loop. With `lstat` alone a
loop is an entry that exists, so absence is false, and nothing raises until
some later reader trips ELOOP. The branch that exists to produce a good
message is also the branch that asks whether the target is reachable at all.

The naming branch reads the link with `os.readlink` inside an exception
handler, and that call can fail if the entry changes underneath it. An
`OSError` raised there would escape `main`, which does not catch `OSError`,
and exit 1. Exit 1 is the reject verdict. That is the same defect this branch
of the work opened with, one function away, so the read is guarded and falls
back to naming no target rather than losing the verdict.

One behavior was found on the way and left alone. `os.replace` over a
symlinked destination replaces the link, not the file it points at, so a
symlinked buffer is swapped for a real file and its old target keeps its
contents. That is what POSIX rename does, and writing through the link
instead would follow it out of the directory the caller named, which is the
reason rename does not. It is now a characterization test, so the suite
teaches it and a deliberate change fails there first, without this branch
pretending to have decided the question.

## Shape 49: the true sentence that answers a different question

`_fsync_dir` returns early on Windows, and the reason recorded for the skip
was that `os.replace` is atomic there regardless. The sentence is true. Every
line above it in the same docstring is about durability.

Fsyncing the temp file makes its bytes durable. Fsyncing the parent directory
makes the rename durable, because the entry pointing at those bytes lives
there, and a host that loses power first comes back with the rename undone.
Atomicity is the promise that no reader sees a half-written entry. It says
nothing about surviving a crash. The skip was justified by the one property
nobody was relying on.

CPython 3.13 `Modules/posixmodule.c:5801` sets
`flags = is_replace ? MOVEFILE_REPLACE_EXISTING : 0`, and line 5824 hands that
to `MoveFileExW`. `MOVEFILE_WRITE_THROUGH`, which Microsoft documents as
waiting for the move to reach disk, is absent. So a Windows host loses a
recorded charge to a power cut the same way an unsynced POSIX host does, and
that is the one outcome charging before scoring exists to prevent.

What is fixed here is the claim, not the gap. Closing the gap needs a
write-through path this repo's CI cannot exercise, and it is tracked rather
than guessed at. The skip stays silent rather than warning like the POSIX
failure path beside it, and the distinction is worth stating: that path warns
because it reports an anomaly in this run, and this one holds for every write
on the platform, so a warning per write would spend the channel's signal and
teach the reader to skip it. A permanent condition belongs in the document a
reader consults, not in the stream reserved for the exceptional.

The README carried the same sentence and one more problem of its own. Its
bullet opened "a recorded charge survives a crash" and then spent a paragraph
explaining a platform where it does not. A heading that contradicts its own
body is worse than either half, because a reader who stops at the heading is
told the opposite of what the text says, and stopping at the heading is what
headings are for.

A false claim in a comment costs more than no claim. No claim leaves the next
reader to look. A confident one answers the question they came with, and this
one had already answered it wrong for every reader since it was written,
including the person who wrote the paragraph above it.
