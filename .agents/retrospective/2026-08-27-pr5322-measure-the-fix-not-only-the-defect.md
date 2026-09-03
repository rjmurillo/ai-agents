# Retrospective: PR #5322, measure the fix and not only the defect

## Session Info

- **Date**: 2026-08-27
- **Agent**: Claude Code, driving PR #5322 on branch `claude/deterministic-model-evaluation-followup`
- **Task Type**: Review-round remediation on a differential-oracle Markdown fence scanner. Rounds 15 to 21.
- **Outcome**: Seventeen defects fixed, six reported claims refuted with measurement, three bugs found in the test suite's own guards, one spec-derived fix measured and rejected before it shipped.

## Phase 1: Insights Generated

### Finding 1: A proposed fix is a hypothesis, exactly like a reported defect

The working rule for twenty rounds was "never reason about whether a finding is real; measure."
That rule had a hole. It covered the DEFECT and not the FIX.

Two instances, one from a reviewer and one from me.

A reviewer proposed clearing two pending flags in a container-pop loop. The site was real. Measured
before applying, over a 19,288-document corpus, the patch took writes-to-balanced-documents from 42
to 78 and broke the reviewer's own document. Not applied.

Then I did the same thing to myself. A backslash in a link destination escapes whatever follows it,
where CommonMark escapes only ASCII punctuation. I implemented the spec rule, and only then measured:

    shipped, escape anything       62 of 64 agree,  0 corruptions
    spec rule, punctuation only    34 of 64 agree, 30 corruptions

The reference parser accepts a backslash before a control character; the spec-derived rule rejects
it, and every one became a `--write` corruption. Nothing shipped, but only because the battery ran
before the commit rather than after.

**Root cause**: "measure the finding" and "measure the change" are different disciplines, and only
the first had been made explicit. A specification is not the oracle. The oracle is the oracle.

### Finding 2: Three separate guards asked the thing they were guarding

Each was found one level below the last, and none by a gate.

1. The fuzz ratchet could disarm itself: `FUZZ_BASELINE` was both the expected value and the seed
   list the tests parametrized over, so emptying it left both ratchets inert and all green.
2. The curated case table could shrink silently: deleting a key deleted a contract instead of
   failing one. The suite went from 584 passed to 582 passed with zero failures.
3. The pin protecting the case table hashed case NAMES only, so swapping a demanding fixture body
   for a trivially balanced one under the same key was invisible.

And a fourth of the same species: `test_repair_is_a_no_op_on_balanced_documents` decided whether to
skip by asking `find_fence_defects` whether it had reported a mistaken closer. A regression that
INVENTS one therefore exempted its own document from the corruption assertion.

**Root cause**: a guard whose scope is computed from the system under test has no scope. The
remedy in each case was to make the scope DATA, or to assert a property that needs no question put
to the system at all.

### Finding 3: The predicate under every claim had a bug, and it had survived two corrections

`_has_unclosed_fence` decides what counts as a corruption, in the suite and in every number quoted
on the PR. It counted a fence body with `content.count("\n")`, which is one short when a document
does not end in a newline.

A false "balanced" is the worst direction for that predicate to fail in: it does not report a bad
write, it EXCUSES one.

Its own docstring already recorded two earlier bugs in the same helper. The third was found by
sweeping all 4,531 tracked Markdown files, not by any test, and it briefly made the repository look
like it held a corrupting file. It does not:

    correct repairs, the oracle agrees the file is unclosed      14
    appends to an oracle-balanced file, the corruption class       0
    middle rewrites, the documented mistaken-closer divergence    48

Re-derived later in the session as a cross-tab of shape against oracle balance, which is the
form the PR now carries, over 4,532 files: 4,470 untouched, 48 middle rewrites of balanced files,
11 middle rewrites of unclosed ones, 3 appends to unclosed ones, and 0 appends to balanced ones.
The 14 above is the 3 plus the 11, grouped by balance rather than by shape. Same measurement, two
groupings, and the grouping has to be stated or the two look like a contradiction.

### Finding 4: Two loops implementing the same grammar, with nothing holding them together

Three mutations of the detector's closing branch moved no repair behaviour at all. The reason was
structural: `find_fence_defects` and `repair_markdown_fences` are separate loops, two hundred lines
apart, each with its own copy of the branch. The tool could report a defect it would not fix, or
fix one it would not report.

Found while mutation-checking something else. That is the pattern worth keeping: a mutation that
changes NOTHING is a finding, not a dud.

### Finding 5: Reports named real sites and predicted the wrong consequence, four times

An unescaped bracket in a multi-line label, an unescaped parenthesis in a multi-line title, a
container-pop site, and an over-indented continuation were all reported as `--write` corruptions.
Measured, the first two are misses, the third does not reproduce at all, and the fourth is a
corruption but was first misclassified as a miss BY ME, because my probe asked whether the tool
reported no defect and the tool reported a false one.

The site and the consequence are two claims. Verifying one does not verify the other.

### Finding 6: A probe that compared two module copies invented a divergence in every file

Round 22 reported a quadratic accumulation in the multi-line label. To prove the rewrite changed
no behaviour I loaded the committed scanner and the reworked one side by side and compared their
output over all 4,532 tracked Markdown files. Every single file came back different, with the two
lists printing identically:

    committed: [Defect(line=474, kind='malformed_closing', text='```markdown'), ...]
    reworked:  [Defect(line=474, kind='malformed_closing', text='```markdown'), ...]

`Defect` is a dataclass, and the two modules were loaded under different names, so the two classes
are different types and no two instances ever compare equal. The probe was measuring module
identity, not scanner behaviour. Comparing field tuples instead gave the real answer: zero files
differ, across both `find_fence_defects` and `repair_markdown_fences`.

This is the fifth hand-rolled probe on this PR to be wrong, and the failure direction is the one
that matters. Here it was harmless because 4,532 of 4,532 is obviously absurd. Had the rewrite
touched a handful of files, a per-file "differs" verdict would have looked exactly like a real
regression, and the fix would have been to the scanner rather than to the probe.

(The same session hit its sibling: loading a module containing `slots=True` dataclasses raises
`AttributeError` inside `dataclasses` unless the module is registered in `sys.modules` before
`exec_module` runs. That one fails loudly, which is why it cost a minute and not a conclusion.)

### Finding 7: Two thirds of a review round was already fixed before it arrived

Round 22 filed four comments. Two were real and current. Two named an asymmetry that had been
fixed three commits earlier: the review ran against the previous head, and the fix was pushed
between the review starting and its comments landing.

Answering them still took a lookup, because "I already fixed that" is a claim like any other. The
check that settled it was `git show <reviewed-sha>:<file> | grep -c <guard>` against the same count
at HEAD: one occurrence there, two here, and `git log -S` naming the commit that added the second.

Worth stating because the cheap move is to assume a review is current, and the second-cheapest is
to assume a stale one is wrong. Both were false here: the finding was real AND already closed.

## Phase 2: Remediation

1. **Measure the fix, not only the defect.** Before adopting any change derived from a
   specification, a review comment, or reasoning, run the full battery and report agreement and
   corruption counts both ways. Recorded in `SKILL.md` and the oracle module for the one rejected
   fix, with both sets of numbers, so the next reader does not re-run the experiment.
2. **A guard must not compute its own scope from the system under test.** Membership became data
   (`MISTAKEN_CLOSER_CASES`), or an independent property: on an oracle-balanced document the repair
   may rewrite the middle but never grow at the end.
3. **Pin what a duplicated implementation shares.** Parity now covers the container class, the link
   grammar helpers and patterns, and the detector against the repair.
4. **Classify a corruption against the oracle's view of balance, never the tool's defect list.**
5. **Stop restating counts.** A count that lived in three places gave three different answers,
   because whether two related fixes are one defect or two is a judgement, not a measurement. The
   cases are the enumeration now.

## Evidence

- PR: <https://github.com/rjmurillo/ai-agents/pull/5322>
- Rejected spec fix and both measurements: commit `e970c7f35`.
- The three self-disarming guards: `be929cdc2`, and the case-inventory pin in `c821993eb`.
- The balance-predicate bug and the corpus sweep that found it: `ee6079de7`.
- Detector-versus-repair pin, and the file split it forced: `2cedc44d3`.
- Refuted container-pop patch, 42 to 78 writes: PR comment 5431946446.
- Quadratic label accumulation, measured 42.1us per line at 32,000 lines and 6.1 after: `6af10daa3`.
- The dataclass-identity probe bug: same commit's verification, corrected before it was believed.

## Correction, 2026-08-27, later the same day

Appended rather than edited in place, per `.claude/rules/retros.md` MUST NOT 1.
Two of this file's own MUSTs were missing when it landed, which a review caught,
and the scope line was stale by two rounds.

**Scope.** The Session Info above says rounds 15 to 21. Findings 6 and 7 came
from round 22, and rounds 23 onward produced the material below. Read the scope
as rounds 15 to 26.

### Failure mode classification (MUST 2)

Classified against `.agents/governance/FAILURE-MODES.md`:

- **FM-9, confident-incorrectness recurrence (High).** The primary class.
  Findings 1, 3, 5 and 6 are all instances: a claim asserted with confidence and
  never checked against the source. The sharpest is not in the original list. I
  cited a commit SHA, `5eee4c1`, in two review replies before the commit existed
  and never ran `git cat-file -t` on it. That is the same defect this PR spent
  twenty rounds finding in other people's claims, committed by the author of the
  finding, in the reply reporting it. Corrected publicly rather than edited away.
- **FM-10, silent defaults and guard-clause suppression (High).** Finding 2 and
  everything downstream of it. Five guards on this branch could not fail: the
  fuzz baseline that was its own seed list, the case table that could shrink
  silently, the digest that hashed names and not bodies, the skip predicate that
  asked the system under test, and the digest that did not cover the exemption
  list. A sixth was mine, written while fixing the other five: a corruption pin
  set to its own maximum, so the direction its failure message promised could
  never fire.

No new class is needed, so no ADR is proposed.

### The finding that outranks the original five

A gap filed as "a miss" is a claim about the OUTPUT, and for four rounds nobody
measured the output. Four gaps were recorded as misses and every one of them
writes: blockquote interrupting a paragraph, raw HTML at 20 of 20 shapes, a
setext underline under a list item at 6 of 9, and an escaped tab at 9 of 11.

Round 21 fixed the balance predicate that caused the first misclassification. I
applied the correction to the entry that prompted it and not to the list it sat
in, so the identical error survived one sentence away for two more rounds and
two more entries. **A correction applied to the instance and not to the class is
half a fix**, and that generalises past this file.

Then the same shape appeared in the ratchet. The corruption assertion classified
a repair by EDIT SHAPE (`repaired.startswith(text)`), so a repair that rewrote
the middle AND grew the document was counted as a middle rewrite and never
reached the zero-append assertion. Asserting the OUTCOME instead, that a
balanced document stays balanced, found a corruption in a tracked file:
`.serena/memories/prompting/prompt-engineering-merge-conflict-analysis.md`, the
only one of 4,533. Every earlier gap on this PR was hand-constructed.

### Remediation with owners (MUST 4)

Each item names an owner and a state. "Author" means the agent driving PR #5322;
items left open are owner decisions and are named as such on the PR.

| # | Action | Owner | State |
|---|---|---|---|
| 1 | Measure the fix, not only the defect, before adopting any change derived from a spec, a review, or reasoning | Author | Done. Both measurements recorded in `SKILL.md` and the oracle module for the one rejected fix |
| 2 | No guard may compute its scope from the system under test | Author | Done. Scope is data in every pin; six guards repaired |
| 3 | Assert the outcome, not the edit shape, wherever a corruption is defined | Author | Done, `test_write_never_mutates_a_balanced_generated_document` |
| 4 | Every gap that corrupts gets a pin holding shapes as data, an unsaturated count, and a not-parametrized scope assertion | Author | Done, `test_fix_fences_known_corruptions.py`, four classes plus the tracked-file case |
| 5 | Verify every commit SHA with `git cat-file -t` before citing it | Author | Done for this PR; carried into the session check-in prompt |
| 6 | Decide whether raw HTML, blockquotes and escaped tabs are built rather than documented | Repository owner | OPEN, three explicit decisions on PR #5322 |
| 7 | Decide whether the duplicated container class and link grammar move to the plugin shared lib per ADR-047 | Repository owner | OPEN, on PR #5322 |
| 8 | Decide whether `markdown-it-py` is the right authority for the six refuted claims | Repository owner | OPEN, on PR #5322 |

### Additional evidence

- Fabricated SHA and its public correction: PR #5322 review comments
  `3867992057` and `3867992401`.
- The three audit-found corruptions and their fix: `44e3503d2`.
- Guards that could not fail in the promised direction: `c4a0ee621`.
- Edit-shape blind spot and the tracked-file corruption: `32eb3e603`.
