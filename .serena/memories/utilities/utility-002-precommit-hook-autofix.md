# Utility: Precommit Hook Autofix

## Skill-Utility-002: Pre-commit Hook Auto-Fix

- **Atomicity**: 90%
- **Location**: `.githooks/pre-commit`

### Purpose

Automatically fixes markdown linting issues and re-stages corrected files before commit.

### Features

- Runs `markdownlint-cli2 --fix` on staged markdown files
- Automatically re-stages corrected files
- Blocks commit only if unfixable violations remain
- Bypass with `SKIP_AUTOFIX=1` or `--no-verify`

### Setup

```bash
git config core.hooksPath .githooks
```

### Security Features

- Uses arrays and proper quoting to prevent command injection
- Handles filenames with spaces safely
- Checks for symlinks to prevent TOCTOU attacks
- Prefers local installation over npx for dependency security

---