# Retrospective: the held-out gate, thirty-six adversarial review rounds

**Branches**: `fix/eval-buffer-crash-exit-code`, `fix/eval-refuse-malformed-input`
**Issues**: [#3422](https://github.com/rjmurillo/ai-agents/issues/3422) (closed),
[#3577](https://github.com/rjmurillo/ai-agents/issues/3577),
[#3588](https://github.com/rjmurillo/ai-agents/issues/3588)
**PRs**: #3430, #3458, #3467, #3478 (merged), #3579 (open)
**Status**: Feature merged. Two follow-up branches carrying review findings.
**Outcome**: PARTIAL. The deliverable shipped. The review rounds after it
found a recurring defect class the original work did not anticipate.

---

## Failure Mode Classification

**Primary Failure Mode**: FM-10 (Silent Defaults and Guard-Clause Suppression)

Nine of the last twelve review findings are the same shape. A guard clause
answers a question with a default, the default is plausible, and the plausible
default is wrong for one input the guard did not consider.

| Finding | The default | What it hid |
|---|---|---|
| 2 | any float accepted as `--min-score` | a bar off the scale it is compared against, so the verdict is fixed |
| 3 | `raw_scores.get(key, 0)` | a report that measured nothing scored 3.33 and cleared any bar under 3.34 |
| 4 | `FileNotFoundError` means absent | a dangling symlink reset the consultation budget |
| 6 | atomicity offered for a durability skip | a Windows crash erases a recorded charge |

**Secondary Pattern**: FM-9 (Confident-Incorrectness Recurrence), in the
documentation rather than the code. Finding 6's comment stated a true fact
that answered a different question than the one its own function asks, and it
had been answering readers wrong since it was written, including the person
who wrote the paragraph above it.

**Reference**: [`.agents/governance/FAILURE-MODES.md`](https://github.com/rjmurillo/ai-agents/blob/main/.agents/governance/FAILURE-MODES.md)

---

## What Worked

**Mutation testing as the acceptance bar.** Forty-five mutations across the
feature, every one killed. The count is less useful than one habit it forced:
when a mutation produced only one red, the rule was to add the test that
widens the denominator before accepting the result. M43 produced one red, M43b
produced two after a two-rule test was added, and the second number is the one
worth trusting.

**Reading a low mutation count instead of dismissing it.** M42 reverted the
degraded-report scan and took only two tests red, which looks like weak
coverage. The two were exactly the tests asserting the enumerated, namespaced
message. The adapter still caught the verdict, so the mutation isolated the
diagnostic and nothing else. A low count is evidence when you can name the
property it isolates and evidence of nothing when you cannot.

**Writing tests before the implementation, without exception.** Findings 3 and
4 each had their full test class written and failing before a line of
implementation changed. Finding 3's tests then surfaced two defects the
reviewer had not reported: a function that scored inside the loop that
collected degraded ids, so one error replaced the enumeration of all of them,
and a test whose fixture contradicted its own docstring and passed only
because the contract it accidentally relied on had not moved yet.

**Verifying reviewer claims rather than accepting them.** Finding 6's reviewer
asserted CPython omits `MOVEFILE_WRITE_THROUGH`. That was checked against
`Modules/posixmodule.c:5801` before it was written into a comment. Rounds 32
through 35 each carried a correct finding with a wrong stated impact, so the
habit paid four times.

**Reading a size gate as information.** The twenty-commit pre-push ceiling
blocked a push and named its own bypass label. The bypass was not used. The
gate was saying the same thing the repo's code-review guidance says, that
about a thousand changed lines is too large and the remedy is to stack a
second change on the first. The split cost nothing because the over-limit
commit was unpushed, so moving the branch back was a fast-forward rather than
a rewrite.

---

## What Failed

**`git reset --hard` destroyed two uncommitted files.** Shape 47 of the debate
log and phase 37 of the session log were on disk and uncommitted when the
branch was reset during the split. Both were lost. `git status` before the
reset would have shown them; `git stash` would have saved them. The loss was
confirmed and reported rather than papered over, and the content was rewritten
from evidence rather than reconstructed as if it were the original draft.

**A range replacement dropped nineteen lines of prose.** A script computed the
end of a Markdown bullet with a heuristic that stopped at the next line
starting with `- `, then replaced the range. The heuristic was correct. The
range it produced was not the range that had been read, and nineteen lines
about warning redaction and stderr handling went with it. It was caught by
diffing the result against `HEAD` at word level, which reported exactly four
lost words once the block was rebuilt. The check should have run before the
write, not after.

Both failures are the same mistake twice: an operation whose blast radius was
assumed rather than measured. The second one happened after the first one had
already been recorded as a lesson in the same session.

**Grep enumerated two of five dependents.** A pattern matching two dict keys
on one line cannot see a dict literal with its keys on separate lines. Three
affected tests were found only by running the suite. The grep is a head start;
the suite is the enumerator.

**A commit swept in an unrelated change.** The Finding 4 commit included the
Finding 6 docstring rewrite because the edit had been made before staging. The
message described only Finding 4. It was caught by reading the diff stat
against the message, and split by reverting the hunk, amending, and
re-applying. A commit whose message does not describe its diff is a defect in
the history even when both halves are correct.

---

## What Generalizes

**A guard that holds by arithmetic is not a guard.** Finding 3's fail-closed
property was real at the default bar and absent at any bar below 3.34.
`--min-score` is a documented flag. Before claiming a default is safe,
compute the input that defeats it and check whether an operator can reach it.

**Ask who could have produced this input.** Finding 3's exit code turns on the
answer. The canonical producer writes all three score keys unconditionally
through a clamp, so a partial mapping cannot come from it intact, which makes
the mapping a statement about the report rather than about the candidate. That
is a config failure, not a rejection. The same reasoning fixes the floor: zero
stays legal because the producer really emits zero, so zero cannot double as
the marker for a value it never wrote.

**A diagnostic must not be able to lose the verdict.** Finding 4's fix reads a
symlink target inside an exception handler to name the broken link. That call
can fail, and an `OSError` raised there escapes `main`, which does not catch
it, and exits 1. Exit 1 is the reject verdict. The same defect class this
branch opened with, one function away, reintroduced by the fix for a different
one.

**A permanent condition belongs in a document, not in a warning.** Finding 6's
skip stays silent while the failure path beside it warns. The failure path
reports an anomaly in this run. The skip holds for every write on the
platform, so a warning per write would spend the channel's signal and teach
the reader to skip it.

**A fixture that contradicts its docstring is a defect while it is green.** It
stays invisible until the contract it accidentally depends on moves, and then
it fails for a reason unrelated to what it was written to test.

---

## Actions

| Action | Status |
|---|---|
| Findings 1 and 5 fixed | Done, PR #3579 |
| Findings 2, 3, 4, 6 fixed | Done, branch `fix/eval-refuse-malformed-input` |
| Windows durability gap | Filed as [#3591](https://github.com/rjmurillo/ai-agents/issues/3591) |
| Optimizer files over the size ceiling | Filed as [#3592](https://github.com/rjmurillo/ai-agents/issues/3592) |
| Ruff ratchet runs only in CI | Filed as [#3580](https://github.com/rjmurillo/ai-agents/issues/3580) |
| Run `git status` before any `reset --hard` | Adopted |
| Diff a computed range against its source before writing | Adopted |
| Read the diff stat against the commit message before committing | Adopted |

---

## Learnings Captured

The nine findings above share one root: a default chosen because it was the
obvious reading of a single failure, applied to a question that had more than
one failure in it. `FileNotFoundError` is the obvious reading of "absent" and
it is wrong for a symlink. A missing key is the obvious reading of "score
zero" and it is wrong for a producer that never omits keys. Atomicity is the
obvious property of `os.replace` and it is not the one a durability step
needs.

The generalization is not "be careful with defaults". It is that a guard
clause encodes a claim about the set of inputs that can reach it, and that
claim is worth writing down next to the guard, because the next reader will
otherwise infer it from the default and infer it wrong.
