# Regression Simulation - Issue #2252 (ADR-067 Part B)

## Method

40 PRs sampled uniformly at random (seed 2252) from the 208 PRs merged
into rjmurillo/ai-agents between 2026-05-03 and 2026-06-02. For each
PR, ran the current `extract_mentioned_files` and `validate_pr_description`
Check 1 against `gh pr view --json files` under four policies:

- **baseline** - current default (all 4 patterns, anywhere not stripped)
- **strict** - only bullet-list pattern[2] inside change-claim H2
- **permissive** - all 4 patterns, only inside change-claim H2
- **hybrid** (chosen) - patterns 0 (inline-backtick) and 3 (markdown-link)
  require change-claim H2; patterns 1 (bold) and 2 (bullet-list) fire
  anywhere

Change-claim H2 set: `## Changes`, `## Per-file changes`,
`## Files Changed`, `## Changed Files` (case-insensitive).

## Results

| Policy | Total CRITICAL Check-1 findings |
|---|---|
| baseline | 4 |
| strict | 1 |
| permissive | 1 |
| hybrid | 1 |

All three candidates remove the same 3 baseline findings; one finding
(brace-expansion path in PR #1873) is unaffected by the default-flip.

## Removed findings - spot check

| PR | File | Verdict |
|---|---|---|
| #1873 | `.gemini/styleguide.md` | False positive (cited in `## Author Pre-flight` as the canonical style file, not a change claim) |
| #1873 | `scripts/eval/README.md` | False positive (cited in `## Open Follow-ups` as a deferred TODO) |
| #1903 | `SOUL.md` | False positive (cited in `## Scope` enumerating what is OUT of scope) |

Zero true drift findings removed.

## Reproducibility

`2252-pr-description-default-flip-regression-sim.py` - drop into a clone
of rjmurillo/ai-agents, populate `.agents/analysis/2252-regression-data/sample_prs.txt` with the 40 PR
numbers, fetch each PR body to `.agents/analysis/2252-regression-data/pr_bodies/{n}.md` and file list to
`.agents/analysis/2252-regression-data/pr_files/{n}.txt` via `gh api`, then run.

## Sample PR set (seed 2252)

1860, 1873, 1883, 1886, 1893, 1903, 1965, 1989, 2016, 2017, 2019, 2027,
2029, 2055, 2059, 2061, 2074, 2076, 2078, 2082, 2107, 2114, 2151, 2169,
2172, 2174, 2178, 2190, 2203, 2213, 2214, 2216, 2232, 2234, 2236, 2242,
2243, 2249, 2269, 2276
