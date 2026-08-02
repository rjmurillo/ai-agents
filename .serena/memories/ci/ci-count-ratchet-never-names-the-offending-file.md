# Skill: Locating the file a count ratchet is failing on (95%)

## Statement

The count ratchets report a delta and never name the file. `taste count ratchet: baseline is 602 but current tree has 603 violations` tells you nothing about where. The suggested remedy command prints the same aggregate.

Find the offender by diffing per-file violation counts against `origin/main`. Do not bisect.

## Recipe

```bash
L=.claude/skills/taste-lints/scripts/taste_lints.py
for tree in <branch-worktree> <main-worktree>; do
  (cd "$tree" && uv run --frozen python "$L" --format json -- $(git ls-files) \
    | python3 -c "
import json,sys,collections
d=json.load(sys.stdin); rows=d if isinstance(d,list) else d.get('violations',[])
print(json.dumps(collections.Counter(
    r['file'] for r in rows if str(r.get('severity','')).lower()=='error')))
") > "cnt_$(basename $tree).json"
done
# then diff the two Counters; the file whose count rose is the offender
```

The linter needs `--format json -- <files>`; with no file arguments it scans nothing and reports zero, which reads as a clean tree.

## Evidence

2026-08-01: four separate branches blocked by this in one session. Each cost a manual offender diff to locate, because the failure names no path.

- `lefthook.yml` sat at exactly 500 lines on `main`, so the next hook added crossed the limit
- three branches crossed it with their own new test files (513, 507, 552 lines)

Attribution is worth proving rather than inferring: `git rm --cached <suspect>` then re-running the ratchet returns `OK` if that file is the whole delta.

## Gotcha: the updater is not the checker

`scripts/ci/count_ratchet.py --update ruff` reports success and leaves the baseline unchanged. The working updater is the per-ratchet script:

```bash
uv run --frozen --extra dev python scripts/ci/ruff_count_ratchet.py --update
# -> ruff count ratchet: improved 329 -> 326 (-3). Baseline lowered.
```

## Anti-Pattern

Raising the baseline to clear the block. The gate exists to refuse a new error-severity violation; raising it defeats the purpose. Split the file or fix the violation. Lowering a baseline after a genuine improvement is required, though: an unrecorded improvement leaves slack that lets the next regression up to the stale number pass silently.

## Related

- Issue #4207 (the ceiling plus the missing filename in the message)
- Issue #3902 (show new violations when the ratchet fails)
- Issue #3779 (`# taste-lint: ignore <rule>` escape with a reason)
