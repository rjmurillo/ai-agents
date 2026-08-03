# Enumerating the eval harness: two naming conventions, and a glob that silently halves it

`scripts/eval/` names its command-line entry points two different ways, and the
two carry no distinction. Globbing for one style finds a subset and reports it
as the whole, so the failure is a confidently wrong answer rather than an empty
result you would notice.

## The split

Measured on `c02f61ddd2`:

| Pattern | Count | What it is |
| --- | --- | --- |
| `eval-*.py` | 12 | CLI entry point |
| `eval_*.py` | 2 | CLI entry point |
| `_*.py` | 22 | Private module, imported not run |

`eval_run_rollup.py` and `eval_skill_router.py` are the two underscore names.
Both define `__main__` and take arguments, exactly like the twelve hyphenated
ones. The underscore does not mark them private, internal, newer, or different
in any way I could find. Private modules use a leading underscore instead, which
is the convention that actually carries meaning here.

So `ls scripts/eval/eval_*.py` returns 2 of the 14 entry points, about 14% of the
surface, and returns them without error.

## Why this bites

I asked whether any eval in this repository compares a skill against a no-skill
control, globbed `scripts/eval/eval_*.py`, got two files, found one weak match,
and was about to record that no-skill baselines do not exist here.

They do. Three of the hyphenated files carry one:

- `eval-agent-vs-baseline.py` runs an arm "with no skill content".
- `eval-knowledge-integration.py:412` marks an arm "Baseline: no skill context".
- `eval-skill-overlap.py:175` documents "baseline: average score with no skill context".

A glob that returns nothing prompts you to widen it. A glob that returns a
plausible handful does not.

## How to enumerate it correctly

Match both separators and exclude private modules:

```bash
ls scripts/eval/ | grep -E '^eval[-_]'
```

Or ignore the prefix and select on behavior, which survives a future rename:

```bash
grep -l '__main__' scripts/eval/*.py
```

Prefer the second when the question is "what can I run", since it does not
depend on the naming staying as it is.

## Related trap in the same tree

Fixtures split the same way. `evals/` holds the fixture suites; `scripts/eval/`
holds the code that runs them. Searching one for the other returns empty and
looks like an answer. A scan rooted at `scripts/eval/` alone finds 7 provenance
values and misses the 189 under `evals/`.

## Do not

Do not rename these to one convention as a drive-by. Both spellings appear in
workflow files, docs, and prior session logs, so a rename is a cross-tree change
that needs its own issue and its own reference sweep. This entry exists so the
inconsistency stops producing wrong answers, not to argue for fixing it.
