# Pre-commit Hook Auto-Fix

**Statement**: Automatically fix markdown linting issues and re-stage corrected files

**Context**: Git pre-commit hook setup

**Atomicity**: 90%

**Impact**: 8/10

**Location**: `.githooks/pre-commit`

## Features

- Runs `markdownlint-cli2 --fix` on staged markdown files
- Automatically re-stages corrected files
- Blocks commit only if unfixable violations remain
- Bypass with `SKIP_AUTOFIX=1` or `--no-verify`

## Setup

```bash
git config core.hooksPath .githooks
```

## Security Features

- Uses arrays and proper quoting to prevent command injection
- Handles filenames with spaces safely
- Checks for symlinks to prevent TOCTOU attacks
- Prefers local installation over npx for dependency security
