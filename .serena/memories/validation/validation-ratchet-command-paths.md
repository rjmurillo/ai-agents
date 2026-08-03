# Count Ratchet Commands and Their Scope

The count ratchets block a push when a tracked count rises. Running them by hand
before pushing saves a ten minute round trip, because the pre-push hook runs the
full test suite first and only then reports the ratchet failure.

## The documented pre-PR gate does not cover them

`scripts/validation/pre_pr.py` runs no ratchet. `grep -c ratchet
scripts/validation/pre_pr.py` returns 0. It does run the portability and
model-pin *checkers*, which is why it reads like a superset and is not one:
those are a different family from the four count ratchets below.

So `pre_pr.py` passing is not evidence that a push will succeed. Run the four
commands below as well. Filed as issue #4251.

Measured cost of skipping them, from a real failed push here: the failing
ratchet took 0.21 seconds, and learning that it failed took 674, because
lefthook reports the group only after the 615 second test suite finishes.

## Where they actually live

They are under `scripts/ci/`, not `scripts/validation/`. Guessing the latter
produces `Errno 2`, which is easy to misread as "no such check exists."

```bash
uv run --frozen --extra dev python scripts/ci/ruff_ratchet.py
uv run --frozen --extra dev python scripts/ci/ruff_count_ratchet.py --base-ref origin/main
uv run --frozen python scripts/ci/taste_count_ratchet.py --base-ref origin/main
uv run --frozen python scripts/ci/type_ignore_count_ratchet.py --base-ref origin/main
```

Canonical source for these invocations is `lefthook.yml` under the pre-push
group. Read it there rather than trusting any copy, including this one.

Note `ruff_ratchet.py` takes no `--base-ref`; the other three do. The underlying
`taste_lints.py` also rejects `--base-ref`. Only the `*_count_ratchet.py`
wrappers accept it.

## The scope trap

**A ratchet run without `--base-ref origin/main` is a different check.**
Standalone, it compares against the baseline file in the working tree. With the
flag, it additionally rejects a baseline that has been *raised* relative to the
ref. A change that lifts the baseline to accommodate new debt passes the first
form and fails the second, which is the form the hook runs.

Always pass `--base-ref origin/main` when the question is "will this push
succeed."

**A tracked-file ratchet cannot see a new file until you `git add` it.** Run
`git add -A` before the ratchet, or a newly created file contributes zero and
the local run disagrees with the hook.

**The type-ignore ratchet counts tests.** Its own docstring says "Scope is
git-TRACKED Python files", which includes everything under `tests/`. A single
`# type: ignore` in a new test file trips it. The idiomatic fix is usually to
delete whatever forced the suppression: a sentinel default typed as `object`,
for instance, splits cleanly into two helpers that each need no ignore.

## Reading a failure

The taste ratchet reports only the delta, for example
`602 violations > baseline 601 (+1)`. To find which file moved, run the linter
directly on the files you changed:

```bash
uv run --frozen python .claude/skills/taste-lints/scripts/taste_lints.py <files>
```

The script is inside the skill, not in `scripts/`. File size is the usual
culprit: an ERROR fires above 500 lines, a WARNING at 400. Exactly 500 passes.
Adding a handful of tests to an existing 470 line test file is enough to trip
it, and the fix is a split along a seam that already exists rather than a
suppression.

That last sentence is scoped to test files, and the scope is load bearing. A
test file grows by accumulating independent cases, so a seam always exists and
splitting along it genuinely reduces what a reader has to hold. A registration
list does not work that way. `scripts/validation/pre_pr_sequence.py` holds one
function whose body is 48 ordered `run_validation` calls, so its line count
tracks how many gates the project has, not how hard it is to read. Splitting it
moves lines and resets the counter without making anything simpler.

PR #4302 tried exactly that split and its author closed it, writing that "the
suppression's rationale is correct on the merits, not just expedient" and that
`run_all_validations` stays a 408 line function afterward, 350 instead. Issue
#4285 carries the same position in its title and tracks the real fix, a
table-driven registry. So for a registration list the remedy is a table, not a
split and not a suppression. Quote this section with its population attached.
