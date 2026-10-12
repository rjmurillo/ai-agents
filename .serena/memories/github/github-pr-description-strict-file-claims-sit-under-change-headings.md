# Only paths under a change heading must be in the diff, and the reverse direction is a warning

## What the validator checks

`scripts/validation/pr_description.py` runs two checks.

Check 1 is CRITICAL. A file the description claims changed that is not in the PR diff fails "File mentioned but not in diff" (lines 1149 to 1156).

Check 2 is a WARNING. A changed file in a significant directory and extension that the description never names produces a warning only (line 1176 onward). It does not fail the check.

## What counts as a claim

The strict set is narrower than every backticked path. The message at line 1161 says inline-backtick paths outside the change headings are informational. The headings in `_CHANGE_CLAIM_SECTION_NAMES` are `Changes`, `Per-file changes`, `Files Changed`, `Changed Files`, and `What changed`. A path counts as a claim under one of them as a bullet, bold text, or inside a code fence.

## The mistake on 2026-10-11

One agent in the P2 sweep read the rule as "every file in the diff must be named". The direction is the reverse for failure: a file named under a change heading must be in the diff, and an unnamed changed file only warns.

`pr-review/pr-validator-needs-prepare-body-file-and-diff-backed-paths` records the failing direction but words it as any backticked path. This memory records the heading scope and the warning-only reverse.

## Sources

- `scripts/validation/pr_description.py` lines 1 to 8, 113 to 125, 1149 to 1176, read 2026-10-12.
- Retrospective `.project-toolkit/retrospective/2026-10-12-v070-p2-sweep-resource-and-contract.md` (PR #6334), Five Whys item 7. The agent's mistake itself is relayed and has no artifact.
