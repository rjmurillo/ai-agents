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

No round returned ACCEPT. Every finding was verified at source before being
acted on, rather than accepted on the reviewer's authority; all of them held.
The ADR is recorded with its defeats visible because twelve consecutive
falsifications are evidence about the claim, not noise to be smoothed over.

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
