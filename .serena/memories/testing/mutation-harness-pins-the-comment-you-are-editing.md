# Skill: A mutation harness may pin the exact comment bytes you are editing (MED)

## Statement

An inverted control in a mutation harness mutates a comment and requires the
suite to survive. It finds that comment by exact byte match. Rewording the
comment breaks the control, and the failure reads as `DID-NOT-APPLY` rather than
as a test failure, so it is easy to misread as harness rot.

Before editing a comment in a file that has a mutation harness, grep
`tests/mutation/` for a fragment of it.

## Evidence

2026-08-02, PR #4274. A reviewer asked for canonical citations in the
debate-log comment in `scripts/validation/git_hook_policy.py`. Rewriting it
produced:

```
AssertionError: DID-NOT-APPLY (IC): comment literal not found.
Update this harness to match the current comment.
```

`tests/mutation/test_mutate_debate_log_path.py` held the three comment lines
verbatim in `_IC_ORIGINAL` / `_IC_MUTANT`. Retargeting both at the two lines
that survived the rewrite restored `4 passed`.

The harness behaved correctly. `.claude/rules/testing.md` MUST-7 requires
exactly this: count occurrences before patching and refuse an absent match, so
a stale literal cannot silently grade unmutated code.

## Check before editing

```bash
grep -rn "<distinctive fragment of the comment>" tests/mutation/
```

## Cost of skipping it

Pushed the comment rewrite, then discovered the break on the next full run, so
the fix landed as a second commit on the same PR instead of one clean change.
