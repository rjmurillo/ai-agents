# Triage: Confirming a PR Was Overtaken by `main`

## Problem

A PR that sits long enough gets fixed by other work. Nothing in this repository
surfaces that. `mergeable_state` reports `dirty` for an ordinary textual
conflict and for a PR whose entire reason to exist is gone, so the field cannot
tell the two apart. The cost shows up as a rebase spent re-landing work `main`
already has.

In one pass over six open PRs, three were already fixed on `main`: #4164, #4102,
and #3979. See #4355 for the pattern.

## Direction

This is the complement of `triage-001-verify-before-stale-closure.md`, not a
restatement. That memory guards against closing something as superseded when the
code only ever lived on an unmerged branch. This one is the positive case: how to
confirm supersession is real before closing, and how to recognize the false
positive.

## Screen, cheapest first

1. **Read the linked issue's state.** Extract `Fixes #N` from the PR body. If
   issue N is CLOSED, suspect supersession. Caught 2 of 3.

2. **Check what closed it.** Read the issue timeline for the closing commit. If a
   *different* PR closed it, this PR may still be live. **#4163 is exactly this
   false positive**: its issue is closed, but by other work, and the PR still
   carries an unlanded change. Step 1 alone would have closed real work.

3. **Read `main` directly for the fix.** Do not infer from the issue state.

   ```bash
   git show origin/main:path/to/file | grep -n 'the thing the PR adds'
   ```

   An empty match is only evidence if the command works. Confirm the detector by
   checking that the same `git show` returns the file and locates a nearby anchor
   you know is present. An empty grep against a path that does not exist on that
   ref looks identical to a real absence.

4. **Check `main` has the tests and docs too**, not just the implementation. A
   partial landing is not supersession.

5. **Start a rebase.** The conflict is the evidence. Both sides asserting the
   same corrected fact in different words means `main` got there first.

## Partial supersession

A PR that closes several issues can be partly overtaken. #4208 listed three:
one open, two closed. The correct action is neither close nor rebase. Split the
live piece out against current `main` and drop the rest. Rebasing 259 files to
re-land two settled fixes spends the whole cost for a third of the value.

## The risk that no conflict warns about

Merging a stale base can overwrite a newer state with an older one while parsing
cleanly. #4164 was 27 commits behind and would have merged a ratchet baseline
fixture (`tests/fixtures/guard_corpus_baseline.json`) from before `main` moved.
GitHub reported `blocked`, not `dirty`, so no conflict marker would have
appeared.

**Not every baseline carries this risk, and the difference is checkable.** The
counted ratchets defend themselves. `scripts/ci/count_ratchet.py`, shared by
`ruff_count_ratchet.py` and `taste_count_ratchet.py`, exposes `baseline_at_ref`
and exits 1 on "baseline raised vs `--base-ref`", which is what makes the
baseline monotonic rather than merely advisory.
`scripts/validation/check_skill_md_portability.py` does the same. So a stale
branch carrying a looser count is caught, not silently merged. #4117 is a live
instance: it carries `ruff_count_baseline.txt` at 320 while `main` has tightened
to 315, and the ratchet will reject that rather than let it through.

`tests/fixtures/guard_corpus_baseline.json` is the opposite case. Its only
reader is `tests/test_guard_diff.py`, which performs no base-ref comparison at
all, so nothing detects an older copy replacing a newer one.

The test to apply, rather than treating every baseline as equally dangerous:

```bash
grep -cE 'base_ref|baseline_at_ref|git show' <the file's reader>
```

Zero means the file is defended only by textual conflict, which a clean merge
does not produce. Generated fixtures and lockfiles usually land in that group;
counted ratchets usually do not.

## Do not

- Close on step 1 alone. That is how real work gets thrown away.
- Trust an empty grep without checking the detector runs.
- Rebase a large PR before screening it. The screen costs a minute; the rebase
  costs an hour and can silently revert newer work.
