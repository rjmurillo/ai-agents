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
