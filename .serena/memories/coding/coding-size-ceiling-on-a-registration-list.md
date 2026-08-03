# Skill: When a size ceiling fires on a registration list (85%)

## Statement

`scripts/validation/pre_pr_sequence.py` holds one function whose body is 48
ordered `run_validation(...)` calls. When it crossed the 500 line `file-size`
ceiling, the rule's own remediation text proposed extracting helper functions.

That advice is wrong for this file, and the file itself proves it. Its
docstring reads:

> Ordered pre-PR validation sequence (extracted from `pre_pr.py`, Issue #3073).
> [...] Extracted so `pre_pr.py` stays under the module size ceiling while a new
> governance gate is added.

So this file exists **because** `pre_pr.py` hit the same ceiling. The
extraction reset the counter without reducing anything, and the extracted file
then hit the ceiling itself. A second extraction produces a third file with the
same property.

## The contradiction

Conventional wisdom: a long file is a complexity signal, so split it.

First principles: for a registration list, the line count tracks **how many
gates the project has**, not how hard the module is to read. Adding a gate is
supposed to add lines. Splitting the list also destroys the one property the
file exists to express, which is ordering: the sequence is deliberately ordered
so the cheapest push-blocking signal arrives first, and that ordering stops
being local the moment it spans two modules.

## What to do instead

The repo's own code-quality rule already names the right fix, under
"Table-Driven Logic": replace the call sites with a table and one loop, so
adding a gate is a one line edit. That takes the file far under the ceiling and
makes the ordering readable as data. Filed as issue #4285.

Until that lands, suppress with a rationale, per the code-quality rule's
last-resort guidance: `# taste-lint: ignore file-size` in the **first 10 lines**
of the file, followed by a comment stating what the check wants, why the
idiomatic fix does not apply, and the issue that will remove the suppression.
Precedent: `.claude/skills/orphan-ref-validator/scripts/scan.py`.

Verify the suppression took effect rather than assuming it:

```bash
uv run --frozen python .claude/skills/taste-lints/scripts/taste_lints.py \
  --format json -- <file>          # want "error_count": 0
uv run --frozen python scripts/ci/taste_count_ratchet.py --base-ref origin/main
```

## Generalization

Before obeying a size ceiling, ask what the count measures. If the file is a
list whose length tracks the size of the domain rather than the difficulty of
the code, extraction is a rename. Convert the list to data, or suppress with a
reason. Do not extract, because the next author inherits the same wall one file
further out.
