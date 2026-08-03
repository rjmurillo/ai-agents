# Find existing coverage by mutation, not by name

## Claim

To learn whether some behavior is already pinned by a test, break the behavior
and run the suite. Do not grep for a test class or function name. The grep
answers whether a particular *spelling* exists; the mutation answers whether
the *guarantee* exists. Those diverge whenever trunk reached the same outcome
under a different name.

## The incident

A merge from main flattened a commit on `fix/ci-least-privilege` that had
added `TestBotSkipClassification` to `tests/ci/test_pr_validation_workflow.py`.
That class pinned `Run ADR-006 run-block ratchet` as unconditional, so bot
authored workflow PRs could not skip it.

Grepping trunk for `TestBotSkipClassification` returned nothing. Read as
absent coverage, that justified restoring 121 lines. The restore was staged
and passed.

The mutation disproved it. Re-adding `if: steps.should-run.outputs.skip !=
'true'` to the ratchet step and rerunning the file failed three tests. Two
belonged to `TestBotSkipGuardClassification`, a trunk class the grep never
matched because `Guard` sits in the middle of the name.

Trunk's version was also better. It normalizes `${{ ... }}` wrappers and
splits on `&&`, so a step that adds a second condition alongside the bot skip
guard is still classified as guarded. The dropped class compared the whole
`if:` string for equality and would have missed that. Shipping the restore
would have added duplicate and weaker tests.

## Why the grep is the wrong instrument

Independent authors converge on the guarantee, not the identifier. Names drift
across renames, extractions, and parametrization. Coverage can also live in a
module level function, a parametrized case id, or a different file entirely.
A name search has to guess all of those; a mutation has to guess none.

This is the coverage-shaped instance of the general rule that an empty grep is
not absence. It has a cheap positive control built in: if the mutation fails
nothing, the behavior really is unpinned.

## Procedure

1. Apply the mutation to the real shipped artifact.
2. Assert the edit applied before trusting the result (a failed patch reports a
   false green).
3. Run the candidate test file, or the suite when the owner is unknown.
4. Read the failures. They name the guardians and their real spelling.
5. Restore, and confirm the working tree is clean.

If nothing fails, the coverage is genuinely missing and writing it is
justified. If something fails, read that test before writing a sibling.

## Related

- `.claude/rules/testing.md` SHOULD 9 states this as a binding convention.
- `mutation-testing-false-green.md` covers step 2, the assert-then-apply
  discipline.
- `git-diff-direction-on-a-stale-branch.md` covers the neighbouring trap that
  produced the false lost-work signal in the first place.
