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

## Cheaper diagnosis when you already know what you changed

The recipe above scans `git ls-files` in two trees, which is the right tool when
the offender is unknown. When you caused the regression yourself, you already
know the candidate set, so lint just those files in both trees:

```bash
L=.claude/skills/taste-lints/scripts/taste_lints.py
# in your worktree, and again in a clean worktree at the PR base SHA
uv run --frozen python3 "$L" <your changed files> --format text
```

The rule prints the measured size, so the before/after pair names the crossing
directly. 2026-08-05: this located a `+1` regression in two commands.
`scripts/ci/build_ai_review_context.py` read `499/500 lines` (WARNING,
"approaching limit") at the PR base and `511 lines` (ERROR) after a 12-line fix.

## When no correct fix fits under the limit

`lefthook.yml` at exactly 500 lines is not the only instance of this shape.
`scripts/ci/build_ai_review_context.py` reached 499 of 500 on PR #4589, which
made the file unfixable in place: the smallest correct form of the fix it needed
was three lines (one regex, one blank, one condition) and landed at 502. Every
correct version exceeded the limit.

That is the case issue #3779 exists for. `# taste-lint: ignore <rule>` in the
first 10 lines with a stated reason is the sanctioned escape, and there is broad
precedent: 15 Python scripts carry it, for example
`scripts/validation/pr_commit_count.py:2` and `scripts/github_core/api.py:1`.

Two conditions before reaching for it, from the repo's own suppression rule:

1. The idiomatic fix has to be genuinely unavailable, not merely inconvenient.
   Measure the smallest correct version and show that it still exceeds the
   limit. "Splitting is a lot of work" is not the bar.
2. Write the mini-ADR inline: what the check wants, why the idiomatic fix fails
   here, and the issue tracking the real fix. A bare suppression is a defect.

Splitting a CI-critical module inside an unrelated bug fix is adjacent scope,
not owed completeness. File the extraction issue and move on.

## Gotcha: `| tail` hides the exit code you are checking

`uv run --frozen python3 scripts/ci/taste_count_ratchet.py | tail -3; echo $?`
reports `tail`'s status, not the ratchet's. If `tail` succeeds, the pipeline
reads as a pass while the ratchet underneath it failed. The ratchet's failure
banner is its first line, so `tail` also drops the line that says REGRESSION.
2026-08-05: this reported a passing pre-push check on a tree that was already
failing, and cost a full push cycle. Redirect and check instead:

```bash
uv run --frozen python3 scripts/ci/taste_count_ratchet.py > out.txt 2>&1
echo "EXIT=$?"; head -1 out.txt
```

## Related

- Issue #4207 (the ceiling plus the missing filename in the message)
- Issue #3902 (show new violations when the ratchet fails)
- Issue #3779 (`# taste-lint: ignore <rule>` escape with a reason)
- Issue #4597 (`build_ai_review_context.py` at 499/500, the worked example above)
