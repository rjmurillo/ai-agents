# Duplicate code detection

Python copy/paste duplication may not grow. A token-based detector
([jscpd](https://jscpd.dev), pinned in `package.json` and `package-lock.json`)
scans authored Python. Existing duplication is recorded in
`.jscpd-baseline.json`. The baseline can only shrink.

## Run it

```bash
uv run python scripts/validation/check_duplicate_code.py
uv run python scripts/validation/check_duplicate_code.py --base-ref origin/main
```

Run `npm ci --ignore-scripts` to install the integrity-locked detector.
Without that installation, the checker exits with a configuration error.
The checker runs only the locked `node_modules/jscpd` runner and ignores the environment.

## What is scanned

`.jscpd.json` scans Python only, with `minTokens` 100 and `minLines` 10.
It ignores generated mirror trees, because each has a canonical source that
stays in scope: `src/{copilot-cli,codex,hermes,muse,cursor}`,
`src/claude/{lib,hooks}`, `src/claude/skills/review/scripts`, and `.claude/hooks`.
The `.claude/lib` package mirrors and linked bootstrap files are excluded.
Its hand-written dispatcher modules remain in scope.
The spec skill's bundled `metrics_writer.py` is also excluded.
Bundle-parity tests require that copy to match `scripts/metrics_writer.py`.
The canonical script and neighboring authored skill scripts remain scanned.
See `.agents/governance/GENERATOR-FILES.md`.
Do not add hand-written paths to the ignore list. Record the debt instead.

## When it fails

| Message | Fix |
|---------|-----|
| new or occur more often than the baseline allows | Extract the shared code into one function or module. Never add a baseline entry. |
| baseline entries no longer occur | Run `check_duplicate_code.py --prune`, then commit the smaller baseline. |

Editing code inside an existing duplicated block changes its fingerprint, so
the old entry goes stale and the edited block reads as new. Consolidate the
block in the same change.

`--base-ref` caps the ceiling at the fork-point baseline, so a branch cannot
hand-edit the baseline to hide new duplication.

Exit codes follow ADR-035: 0 ok, 1 duplication grew or baseline stale,
2 config error, 3 jscpd or git failure.
