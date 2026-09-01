# The count ratchets make "behind main" a practical merge blocker even though the ruleset does not

## Superseded in part by issue #5065 (2026-08-27)

The behavior below is what `_base_ref_verdict` did up to issue #5065, and the
measurements are still the record of what it cost. The verdict now reads the
fork point with `git merge-base` and compares the recorded baseline against the
value there. Seven outcomes, each with the verdict string the code prints. Read
them from `scripts/ci/count_ratchet.py` if you need to be sure; they are quoted
here so a future session does not grep for a string the code stopped emitting,
which is what an earlier draft of this section caused by collapsing the two
non-equal directions under one label.

Equal, so the branch never moved the number. Which verdict depends on the
caller's `MERGE_TREE_BACKED`, because the waiver trades this comparison for the
merge-tree gate and only a registered ratchet has one:

- Registered (ruff, taste, type-ignore, memory-index, cli-exit): prints
  `BEHIND BASE (not blocking)` to stdout and evaluates the count leg as usual.
  The 31-of-33 shape recorded under Evidence no longer blocks.
- Not registered (subprocess-encoding): `BEHIND BASE` and `EXIT_REGRESSION`.
  Nothing else would measure the merged result, so the stale ceiling stands.

Not equal. The direction is measured and the two directions do not share a
message, because a cleanup branch told to "restore" the base value is being
accused of the opposite of what it did:

- Recorded above the fork point, so this tree raised the scalar, committed or
  merely dirty: `BASELINE ABOVE BASE` and `EXIT_REGRESSION`.
- Recorded below the fork point while the base went lower still, the cleanup
  shape: `BASELINE LOWERED BEHIND BASE` and `EXIT_REGRESSION`. Names the fork
  point's value, this tree's, and the base's, and never says "restore".

The comparison failing to happen at all is three states, not one, split by
which read failed. All block; the exit code and the remedy differ:

- No fork point, the only reachability failure: `FORK POINT UNREADABLE`, exit
  3. Names a shallow clone or an unrelated history and sends you to `git fetch`.
- Fork point named, but that commit tracks no baseline file:
  `FORK POINT RECORDS NO BASELINE`, exit 2. The baseline was added after the
  branch was cut; a fetch does nothing and the remedy is a merge.
- Fork point named, file present, value will not parse:
  `FORK POINT BASELINE UNREADABLE`, exit 3.

The "must not be softened" section below still holds for what it actually
protects, and the fix does not violate it: it does not pass a branch on
`count <= base`. A higher number can only reach `main` through a diff that
writes it, and such a diff still blocks. Syncing before a push remains good
practice; it is no longer a precondition for a green baseline-above-base leg.

## Question

`main`'s branch ruleset sets `strict_required_status_checks_policy: false` (measured 2026-08-14; reverted 2026-08-10), so
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

Superseded by issue #5065, and left here because the reasoning is the record of why
the fork-point read was added. A third read now separates the two histories, so this
message only prints for the branch that really did raise the scalar. If you are merely
behind you get one of the `BEHIND BASE` lines above instead.
