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

## Gotcha: the against-main diff goes blind when main is the problem

The recipe above assumes `origin/main` is clean, so a per-file count that rose
relative to main names the offender. When main itself is red, your branch and
main sit at the same number and the diff is empty. Diff against the commit that
last wrote the baseline file instead:

```bash
git log -1 --format=%h -- scripts/ci/taste_count_baseline.txt
git worktree add --detach <path> <that-sha>
```

Dump both violation lists and diff them. `list_violations()` is easier than the
JSON counter recipe when you want the raw entries rather than per-file totals,
and it sidesteps the 40-line truncation in the ratchet's own output:

```bash
uv run --frozen python -c "
import sys, pathlib; sys.path.insert(0, '.')
from scripts.ci.taste_count_ratchet import list_violations
v = list_violations(pathlib.Path('.'))
pathlib.Path('OUT.txt').write_text('\n'.join(sorted(v)) + '\n')
print(len(v))"
```

2026-08-03: this located `.agents/governance/GOTCHAS.md: [file-size] File
exceeds 500 lines (521 lines)` as the sole net-new entry between 595 and 596,
after the against-main diff came back empty because main carried the same 596.

## Gotcha: the ignore escape works in markdown, as an HTML comment

Every in-repo precedent for `# taste-lint: ignore <rule>` is a `.py` file, so
the bare `#` form is the only one you will find by grepping. The scanner reads
the first ten lines of any file and looks for the token, so a markdown file
suppresses a rule by wrapping the same directive in an HTML comment:

```markdown
<!-- # taste-lint: ignore file-size (reason) -->
```

Verified 2026-08-03: adding that line to a 521-line governance doc moved the
repo count from 596 to 595 and dropped the file from `list_violations()`.

Use parentheses or a comma to introduce the reason, never the ` -- ` separator
that the `.py` precedents use. A double hyphen is illegal inside an HTML
comment, so the line is malformed markup and does not reliably survive editing
passes. Every markdown precedent in the repo (`CONTRIBUTING.md`,
`.agents/SESSION-PROTOCOL.md`, `ADR-035`, the `memory-search` references)
already avoids it.

Losing the directive is silent, and the ratchet failure will not point at you:
re-verified 2026-08-03 by deleting it from `GOTCHAS.md`, which produced
`596 violations > baseline 595` followed by a list headed
`.agents/analysis/worktrunk-integration.md` and `... and 556 more`. The file
that actually regressed appears nowhere in the output.

## Related

- Issue #4207 (the ceiling plus the missing filename in the message)
- Issue #3902 (show new violations when the ratchet fails)
- Issue #3779 (`# taste-lint: ignore <rule>` escape with a reason)
