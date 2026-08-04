# Skill: Search open issues for the target file before designing a fix (95%)

**Atomicity Score**: 95%
**Source**: Retrospective `.agents/retrospective/2026-08-02-wrong-fix-before-search.md`
**Date**: 2026-08-02
**Validation Count**: 1 (PR #4302 built and closed unmerged; issue #4285 already open)
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

## Related

- `.serena/memories/analysis/analysis-002-rca-before-implementation.md` verifies the premise of
  an issue you were handed. This memory is the inverse: discover the issue you were not handed.
- `.serena/memories/knowledge/chestertons-fence.md` says search memory before changing code. It
  never names the issue tracker, which is where this fence's sign was posted.
- `.serena/memories/process/process-diagnosis-is-not-remedy.md` is the deeper cause.
