# Skill: Search open issues for the target file before designing a fix (95%)

**Atomicity Score**: 95%
**Source**: Retrospective `.agents/retrospective/2026-08-02-wrong-fix-before-search.md`
**Date**: 2026-08-02
**Validation Count**: 2 (PR #4302 built and closed unmerged, issue #4285 already open; issue #4461 filed for a trap already documented in Serena the day before)
**Tag**: helpful
**Impact**: 9/10 (one hour of wasted work, and the wrong design shipped to review)

## Statement

Before designing a fix, search open issues for the file you are about to change. Do it even
under P0. The search costs 20 seconds; skipping it cost 64 minutes and a closed PR.

```bash
gh issue list -R rjmurillo/ai-agents --state open --limit 400 \
  --search "pre_pr_sequence" --json number,title
```

## Context

You have a clean root-cause bisection and you are about to write the remedy. Urgency is high
(a repo-wide push block, a red main, a broken gate). This is exactly when the search feels
skippable and is not.

## Evidence

2026-08-02. Pristine `origin/main` failed the taste count ratchet, blocking every push in the
repository. Bisection correctly located the offender: PR #4272 grew
`scripts/validation/pre_pr_sequence.py` from under 500 to 512 lines, past the taste-lint
file-size ceiling.

I designed the remedy directly off that bisection: extract six fast gates into a new module,
512 -> 455 lines. Built it, wrote two guard tests, mutation-proved both, ran the full pre-push
suite green, pushed, opened PR #4302.

Issue **#4285 was already open** and its title alone would have redirected me:

> "pre_pr_sequence.py is a registration list measured by a complexity ceiling; extraction only
> resets the counter."

That is a verbatim rejection of the design I had just shipped. I closed PR #4302 unmerged.
Nothing was salvageable: both new tests assert against `run_fast_gates`, a function that will
not exist under the registry #4285 prescribes.

## Why extraction was wrong

`run_all_validations` is a 408-line function whose body is 48 ordered `run_validation` calls.
Its line count tracks how many gates the project has, not how hard it is to read. Extraction
moves 57 lines to a new file; the counter drops below the ceiling and nothing gets simpler
(408 -> ~350). The repo's own `code-quality` rule already prescribes the real fix: "replace a
long sequence with a table."

## Second validation: the two indexes are not interchangeable

2026-08-03. The inverse failure, same cost. I lost about 20 minutes to `new_pr.py` rejecting a
PR with `Session End validation failed`, a message naming no file. I root-caused it to `--base`
defaulting to the local `main` ref, which never advances inside a worktree, so the changed-file
set spanned 797 files instead of 3 and pulled in a session log the branch never touched.

Before filing I searched the issue tracker, which is what this memory tells you to do:

```bash
gh issue list -R rjmurillo/ai-agents --state all --search "new_pr in:title,body"
```

One hit, closed, unrelated. So I filed issue #4461.

I never searched Serena. The trap was already there in full:
`.serena/memories/tools/github-skill-scripts-reference.md`, section "Gotcha: pass
`--base origin/main`, not the default", added by **PR #4331 on 2026-08-02**, whose own title is
"docs(memory): two new_pr.py traps that each cost a fleet session". Written down one day before
I hit it. It even carries the better workaround: pass `--base origin/main` rather than fetching.

**The issue tracker and Serena are separate indexes over the same problem space, and they hold
different things.** The tracker holds what is unfixed. Serena holds what is known. A trap that
someone documented but never filed exists in exactly one of them, and that is the common case,
because writing the memory is the cheaper act. Searching one and finding nothing tells you
nothing about the other.

Search both. The second search is another 20 seconds:

```bash
grep -rn "new_pr" .serena/memories/
```

The filing was still correct here, and knowing this made it stronger: documentation demonstrably
failed to prevent a recurrence within 24 hours, which is the argument for changing the default
rather than writing the gotcha down a third time. But the 20 minutes were avoidable, and I used
the worse of the two workarounds because I found it myself instead of reading the better one.

## Related

- `.serena/memories/analysis/analysis-002-rca-before-implementation.md` verifies the premise of
  an issue you were handed. This memory is the inverse: discover the issue you were not handed.
- `.serena/memories/knowledge/chestertons-fence.md` says search memory before changing code. It
  never names the issue tracker, which is where this fence's sign was posted.
- `.serena/memories/process/process-diagnosis-is-not-remedy.md` is the deeper cause.
