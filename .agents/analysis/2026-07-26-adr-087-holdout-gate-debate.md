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

No round returned ACCEPT. Every finding was verified at source before being
acted on, rather than accepted on the reviewer's authority; all of them held.
The ADR is recorded with its defeats visible because ten consecutive
falsifications are evidence about the claim, not noise to be smoothed over.

Rounds 8 through 10 are the cleanest illustration in this log of why the
count kept climbing. Round 8 found a defect inside the round-7 fix. Round 9
found one inside the round-8 fix. Round 10 found one inside the round-9 fix.
Round 10 was also given explicit permission to return ACCEPT and told that a
false finding costs more here than a missed one, so the streak is not an
artifact of the prompt asking for a defect.

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

Nine of the ten rounds found the same shape. Any part of a budget the caller
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
  reviewer across all ten rounds argued for it. Left to the user, since it
  is a redesign rather than a tweak.
