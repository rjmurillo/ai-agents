# Utility: Precommit Hook Autofix

## Skill-Utility-002: Pre-commit Hook Auto-Fix

- **Atomicity**: 90%
- **Location**: the `markdown-autofix` job in `lefthook.yml`, shimmed into `.git/hooks/pre-commit` by `lefthook install`

### Purpose

Automatically fixes markdown linting issues and re-stages corrected files before commit.

### Features

- Runs `markdownlint-cli2 --fix` on staged markdown files
- Automatically re-stages corrected files
- Blocks commit only if unfixable violations remain
- Bypass with `SKIP_AUTOFIX=1` or `--no-verify`

### Setup

```bash
uv run --frozen lefthook install
```

Do not set `core.hooksPath` by hand. `.githooks` is not tracked here, and a
`core.hooksPath` naming a missing directory makes git run no hook and print no
warning (issue #5090). Repair an affected clone with `uv run --frozen lefthook install --reset-hooks-path`.

### Security Features

- Uses arrays and proper quoting to prevent command injection
- Handles filenames with spaces safely
- Checks for symlinks to prevent TOCTOU attacks
- Prefers local installation over npx for dependency security

---