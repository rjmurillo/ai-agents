# The count ratchets make "behind main" a practical merge blocker even though the ruleset does not

## Question

`main`'s branch ruleset sets `strict_required_status_checks_policy: false`, so
being behind `main` does not formally block a merge. Nevertheless the count
ratchets still make stale branches fail in practice. Does branch freshness
matter even without the ruleset requiring it?

## Conventional answer

No, if `strict` is off, GitHub does not demand that the branch be current.
Merging `main` into a feature branch just to satisfy the ruleset would add a
merge commit for nothing.

## First-principles position

Yes. The ruleset is one gate; the count ratchets are another, and they enforced
freshness on their own even while `strict` was false.
`scripts/ci/count_ratchet.py::_base_ref_verdict` blocks whenever the branch's
recorded baseline is above the base ref's:

```python
if baseline <= base:
    return None
# ... otherwise EXIT_REGRESSION
```

Its docstring says so outright: "A baseline above the one at the base ref always
blocks." So the moment `main` lowers a baseline, every open branch cut before that
lowering fails `Validate PR` until it picks up the lower value.

## Evidence

2026-08-03, `scripts/ci/taste_count_baseline.txt` on `main` at 598. Of 33 open
non-draft PRs, **31 recorded a higher baseline**: mostly 600, some 599, 601, 602, and
two at 613 and 615. The queue was blocked on a bookkeeping number, not on any
violation those branches introduced.

Not specific to the taste linter. `count_ratchet.py` is shared, so every ratchet built
on it behaves identically. PR #4392 failed both at once on push: `taste count ratchet`
600 against 598, and `ruff count ratchet` 315 against 311. `pre-pr-validation` reported
them as a group, `count ratchet(s) failed: python-lint-count-ratchet,
taste-count-ratchet`. One `git merge origin/main` fixed both.

## Why the block is correct, and must not be softened

The tempting change is to pass when the measured count is at or below the base
baseline, since such a branch demonstrably added nothing. Do not make it. If a branch
merges while recording 600 and `main` records 598, the merge can carry 600 back onto
`main` and silently raise the ceiling again. That is precisely the ratchet defeat the
gate exists to prevent. The gate is right; the stale branch is wrong.

## Decision

Sync the branch before spending a push. Prefer `git merge origin/main --no-edit` over
rebase: rebase needs a force-push, and repository policy forbids force-pushing shared
branches. The failure message endorses either ("merge or rebase to pick up the lowered
value").

Verify locally, and check every ratchet rather than only the one CI named first:

```bash
git merge origin/main --no-edit
for r in taste_count_ratchet ruff_count_ratchet; do
  uv run --frozen python scripts/ci/$r.py --base-ref origin/main
done
# taste count ratchet: OK (count == baseline 598).
# ruff count ratchet: OK (count == baseline 311).
```

## Reading the failure

`BASELINE ABOVE BASE. This tree records 600, FETCH_HEAD records 598 (+2).` names two
possible causes because two histories produce identical numbers: a branch cut before
the lowering, and a branch that raised the baseline to cover violations it added. Two
endpoint reads cannot separate them, so the message carries both remedies (issue
#4066). Check whether your own diff touches the baseline file before assuming you are
merely behind.
