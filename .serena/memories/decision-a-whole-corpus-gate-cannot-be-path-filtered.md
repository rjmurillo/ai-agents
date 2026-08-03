# A Whole-Corpus Gate Cannot Be Guarded By A Per-Change Path Filter

**Atomicity**: 94%
**Category**: CI design, first-principles contradiction
**Source**: 2026-08-02 fleet session. Issue #4345, PR #4351, commits a72ee868c
through 160d1670a.

## The conventional wisdom this contradicts

Standard CI practice says to gate each job on whether the change touched files
that job cares about. `dorny/paths-filter` exists for exactly this, and for
per-file checks it is correct and saves real time.

Applied to a gate whose verdict is a **sum over the whole tree**, the same
pattern is not an optimization. It is a correctness bug, and it fails in the
most expensive direction: the workflow reports **success** without measuring
anything.

## The reasoning

A per-file check answers "is this file valid." Its truth depends only on the
files in the diff, so filtering on the diff preserves the answer.

A whole-corpus check answers "is the total under the ceiling." Its truth depends
on the entire tree, so it can change when the diff is **empty with respect to
the filter**. Filtering on the diff does not preserve the answer, it discards
it.

Worse, the failure is absorbing. Once a breach exists, every later commit that
does not touch the filtered paths re-reports green. Nothing re-measures until
someone happens to edit a filtered file. The breach is silent and unbounded in
duration.

## Evidence

`.github/workflows/instruction-budget.yml` gated `validate-budget` on whether
the change touched `.claude/rules/**` or `.github/instructions/**`. The gate
sums the always-on instruction corpus per language against a byte ceiling.

Measured at `a72ee868c`, which was `main`:

```
Ext     Files     Bytes   Ceiling   Tokens~    Usage  Status
.md         9     83201     83000     21949   100.2%    FAIL
```

The workflow run for that same SHA reported `conclusion success`, via a
`Skip budget (no changes)` job, because the squash of #4105 touched no rule
files.

The same validator runs in the pre-push hook, so while CI was green, **every
push in the repository failed**, on every branch, regardless of content. Two of
my own branches failed with diffs of `scripts/validation/pre_pr_sequence.py`
and `.serena/memories/*.md` respectively, neither of which is an instruction
file.

## The second half: an absolute ceiling plus non-strict required checks

The breach itself came from a semantic conflict, not a defective PR:

```
commit       PR      total   note
a6c16da8d    #4329   82603   397 bytes headroom
43eb2c14e    #4281   82942   +339 to knowledge-persistence, 58 left
7b5279967    #4113   83201   +259 to universal, over by 201
```

Each PR was measured against its own base and passed honestly. No two of them
touch the same file. The ceiling is a sum, so the breach exists only after both
land. `strict_required_status_checks_policy: false` on ruleset 11104075 permits
exactly this.

Any absolute (non-diff-relative) ceiling has this property. A ratchet that
compares against `origin/main` does not, which is why the count ratchets caught
their own drift and the budget did not.

## The residual risk this leaves

`PR #4351` restored green by trimming bytes only (`Refs #4345`, not `Fixes`).
Measured at `160d1670a`:

```
.md         9     82992     83000     21895   100.0%    PASS
```

That is **8 bytes** of headroom. Any rule edit adding a single short sentence
re-breaches, and because the path filter is still in place, the re-breach will
again be silent.

## How to recognize this class

Ask of any gate: **does its verdict depend on files outside the diff?** If yes,
it cannot be path-filtered, and it must run on every push and every PR. Candidates
in this repo are the instruction budget, the count ratchets, the portability
baselines, and the memory index counts.

A useful smell: a workflow that has a `Skip <thing> (no changes)` job which
reports success. For a per-file check that is correct. For a whole-corpus check,
a skipped measurement reporting success is precisely the defect.

## Diagnosis when it bites you

Symptom: a push fails on a gate that has nothing to do with your diff. Apply the
red-main diagnostic, which now stands at 5 for 5 in this repo:

```bash
git worktree add -q --detach ~/src/GitHub/rjmurillo/ai-agents-probe-<slug> origin/main
cd ~/src/GitHub/rjmurillo/ai-agents-probe-<slug>
uv run --frozen python scripts/validation/instruction_budget.py --ci
```

Reproducing on pristine `origin/main` proves the branch is innocent and moves
the investigation to `main` in one command. Do not start by reading your own
diff.

## Bisecting a byte-budget breach cheaply

Do not check out each commit. Sum blob sizes straight from the object database,
which takes seconds over 40 commits:

```bash
FILES="<space separated paths the gate measures>"
for c in $(git rev-list --first-parent -40 origin/main); do
  tot=0
  for f in $FILES; do
    s=$(git cat-file -s "$c:$f" 2>/dev/null || echo 0); tot=$((tot+s))
  done
  printf "%s %6d %s\n" "$(git rev-parse --short $c)" "$tot" "$(git log -1 --format=%s $c | cut -c1-62)"
done
```

Get the exact file list from `--format json` rather than guessing it. The `.md`
bucket and the `.py` bucket differ by which `applyTo` globs match, so the file
sets are not the same.

## Related

- `ci/ci-infrastructure-006-required-check-path-filter-bypass.md` is the
  **opposite** failure: a path filter stops a required check from ever
  reporting, so the PR waits forever. That one is loud and self-announcing.
  This one is silent and reports success. Same mechanism, opposite blast radius.
- `git/git-stale-branch-fails-repo-state-tests.md` for the branch-age variant,
  including the count ratchet that says BASELINE RAISED when `main` lowered it.
- Issue #4057 asks that required checks evaluate the actual merge tree, which is
  the second half of this defect.
