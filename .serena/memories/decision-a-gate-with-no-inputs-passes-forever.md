# A Gate With No Inputs Passes Forever, And Its Green Tick Means Nothing

**Atomicity**: 92%
**Category**: CI design, first-principles contradiction
**Source**: 2026-09-06 session. Issue #5626, PR #5627, analysis at
`.project-toolkit/analysis/memory-validation-workflow-cost-analysis.md`. Subject:
`.github/workflows/memory-validation.yml`, added 2025-12-24 in `0dadc6994`
(PR #342), deleted 2026-09 after this measurement.

## The rule

A gate's pass result is evidence only when you also know how many items it
inspected. Before trusting any verifier, read its denominator. A verifier that
examined zero items reports success identically to one that examined all of
them and found nothing wrong.

## The conventional wisdom this contradicts

Standard practice treats a green check as evidence the checked property holds,
and treats gate correctness as a property of the gate's code. Review effort goes
into whether the verifier is right: does it parse correctly, does it handle the
edge cases, are there tests.

That is necessary and insufficient. A verifier can be completely correct and
still be worthless, because correctness is a claim about what it does with an
input. It says nothing about whether an input ever arrives.

## The reasoning

A gate is a consumer. Something else must be the producer. When a feature ships
the consumer and never wires up the producer, the gate enters a state where:

1. It runs on schedule, consuming CI time and PR surface.
2. It passes every time, because an empty input set has no failures in it.
3. Its green tick is read by humans and agents as "this property was verified."
4. No test catches this. Unit tests feed the verifier synthetic inputs, so they
   exercise exactly the path production never reaches.

The failure is silent, self-reinforcing, and invisible to every signal a team
normally watches. It is the inverse of a flaky gate: a flaky gate announces
itself, this one never does.

## Evidence

`memory_enhancement verify-all` verifies citations written in the bracket form
`[cite` + `:TYPE](TARGET)`. It is split here on purpose: see "This file cannot
spell its own subject" below. Measured on `origin/main` at `f2dd625`,
2026-09-06:

```
$ uv run --frozen python -m memory_enhancement verify-all --json | wc -c
3                      # the file is exactly "[]"

$ uv run --frozen python -m memory_enhancement verify-all | grep -c "no citations"
1036                   # every scanned memory, no exceptions

$ grep -rn "\[cite:" .serena/memories/ | wc -l
0

$ git log -S"[cite:" -- .serena/memories/
                       # no output, searched against full unshallowed history
```

The verifier itself is correct. Positive and negative control against the same
binary:

```
$ C='[cite'    # split so this file does not assert the citations it documents
$ printf "# Bad\n\nBody.\n\n## Citations\n\n$C:file](does/not/exist.py) - x\n" > .tmp/bad.md
$ printf "# Good\n\nBody.\n\n## Citations\n\n$C:file](README.md) - x\n" > .tmp/good.md
$ uv run --frozen python -m memory_enhancement --repo-root . --memories-dir .tmp verify-all
bad:
  [FAIL] does/not/exist.py - File not found: does/not/exist.py

good:
  [PASS] README.md - File exists
$ echo $?
1
```

So the code works. The `[cite:...]` syntax is documented in
`.claude/skills/memory-enhancement/SKILL.md` and
`.claude/skills/reflect/references/phase3-4-propose-persist.md`. No memory
writer has ever emitted it. The consumer shipped; the producer did not. The gate
ran 256 days with nothing to check and reported success on every one of them.

Second-order cost, because a silent gate is rarely only idle: the workflow also
posted its full report as a PR comment. With every memory reporting "no
citations", that comment reached 57,447 characters, roughly 14k tokens pulled
into context by every agent reading the thread, against GitHub's 65,536
character comment limit. A gate with no inputs was the single largest consumer
of PR-thread context in the repo.

## This file cannot spell its own subject

Writing this memory broke the gate it describes, on the first push. `Verify
citations` went red on PR #5800 because `parse_citation_block` in
`memory_enhancement/serena_integration.py` matches
`\[cite:(?P<source_type>\w+)\]\((?P<target>[^)]+)\)` against the raw file with
no fenced-code-block handling at all (`grep -c fence` on that module returns 0).
The negative-control example above was therefore read as a real citation, and
its deliberately missing path failed the run exactly as designed:

```
decision-a-gate-with-no-inputs-passes-forever:
  [FAIL] does/not/exist.py - File not found: does/not/exist.py
  [PASS] README.md - File exists
rc=1
```

Consequence: no memory can document the citation syntax, because documenting it
asserts it. Every example in a memory is a live claim about the repository. The
`$C` split above is the workaround, not a fix; the fix is fence-aware parsing,
tracked separately so it carries its own tests.

This is the second-order form of the rule at the top of this file. The corpus
had zero citations for 256 days, so this parser path had never once run against
real content. The first file to exercise it broke it. A gate with no inputs is
not merely uninformative: its untested paths rot, and the cost lands on whoever
finally supplies the first input.

## Detection

Ask of any gate, before trusting it:

1. **What is the denominator?** Make the gate report how many items it
   inspected, not only how many failed. `total=0` and `stale=0` must not render
   the same banner as `total=1036` and `stale=0`.
2. **Who is the producer, and is it wired up?** Name the code path that creates
   the thing being verified. If you cannot name it, the gate has no input.
3. **Does a pickaxe search find the artifact in history?**
   `git log -S"<marker>" -- <path>` returning empty across full history means
   the feature has never once been used. Run this unshallowed; a shallow clone
   silently truncates the answer and makes the absence look local to the window.

Guard rule for new gates: a gate whose input count can be zero needs an explicit
zero-input branch that is loud, not a pass. Either fail, or report
`NOT MEASURED`, but never render the success banner.

## Related

- `decision-a-whole-corpus-gate-cannot-be-path-filtered.md` is the adjacent
  failure: there the gate has real inputs but is skipped, and a companion skip
  job reports success in its place. Same outcome, a green tick that measured
  nothing, reached by a different route. That one is about *when* the gate runs;
  this one is about *what it finds when it does*.
- `ci/ci-infrastructure-006-required-check-path-filter-bypass.md` is the loud
  variant, where the check never reports at all.
- Issue #5626 carries the removal and the duplication table showing all five
  steps of the deleted workflow were enforced elsewhere.
- The citation feature still has consumers in `citation-verify.yml` and
  `memory-health.yml`. Both remain structurally silent until a producer exists.
  The open decision is whether the feature gets a producer or is retired.
