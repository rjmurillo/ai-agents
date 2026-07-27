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
