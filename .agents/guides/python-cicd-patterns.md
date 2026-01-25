# Python CI/CD Migration Patterns

**Reference**: ADR-042 Python Migration Strategy
**Applies To**: All Python scripts invoked from GitHub Actions workflows
**Status**: Active

---

## Overview

This guide documents patterns for integrating Python modules into GitHub Actions workflows, following ADR-006 (thin workflows, testable modules).

---

## Invoking Python from GitHub Actions

### Pattern 1: Module Invocation (Preferred)

Use `python -m` for packages with `__main__.py`:

```yaml
- name: Run validation
  run: python -m scripts.validation.check_session
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

**Why**: Enables proper imports, respects package structure, and works consistently across environments.

### Pattern 2: Script Invocation

For standalone scripts:

```yaml
- name: Run script
  run: python scripts/utils/validate_path.py --path "${{ inputs.target_path }}"
```

**When to Use**: Simple utilities that do not require package imports.

---

## Error Handling

### Exit Codes

Python scripts MUST use standard exit codes (per ADR-035):

```python
import sys

def main() -> int:
    """Main entry point. Returns exit code."""
    try:
        # Business logic
        if validation_failed:
            print("ERROR: Validation failed", file=sys.stderr)
            return 1
        return 0
    except Exception as e:
        print(f"FATAL: {e}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    sys.exit(main())
```

| Exit Code | Meaning |
|-----------|---------|
| 0 | Success |
| 1 | Validation/business logic failure |
| 2 | Unexpected error/exception |

### Logging to stderr

Errors MUST go to stderr, not stdout:

```python
import sys

# WRONG
print("Error: file not found")

# CORRECT
print("Error: file not found", file=sys.stderr)
```

**Why**: GitHub Actions captures stdout for step outputs. Errors in stdout can corrupt output parsing.

---

## Parameter Handling

### Using argparse

All scripts accepting parameters MUST use argparse:

```python
import argparse
import sys


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Validate session log format"
    )
    parser.add_argument(
        "--session-path",
        required=True,
        help="Path to session log file"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Enable strict validation mode"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    # Use args.session_path, args.strict
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

### Workflow Integration

```yaml
- name: Validate session
  run: |
    python scripts/validate_session.py \
      --session-path "${{ inputs.session_path }}" \
      ${{ inputs.strict && '--strict' || '' }}
```

---

## ADR-006 Compliance

Workflow YAML = orchestration only. All logic lives in Python modules.

### WRONG: Logic in Workflow

```yaml
- name: Check files
  run: |
    files=$(find . -name "*.py" -type f)
    for f in $files; do
      if ! python -c "import ast; ast.parse(open('$f').read())"; then
        echo "Syntax error in $f"
        exit 1
      fi
    done
```

### CORRECT: Logic in Python Module

```yaml
- name: Check Python syntax
  run: python -m scripts.validation.check_syntax
```

With corresponding Python module:

```python
# scripts/validation/check_syntax.py
"""Check Python file syntax across repository."""

import ast
import sys
from pathlib import Path


def check_file(path: Path) -> bool:
    """Check single file for syntax errors."""
    try:
        ast.parse(path.read_text())
        return True
    except SyntaxError as e:
        print(f"Syntax error in {path}: {e}", file=sys.stderr)
        return False


def main() -> int:
    """Check all Python files. Returns 0 on success, 1 on failure."""
    repo_root = Path(__file__).resolve().parents[2]
    python_files = list(repo_root.glob("**/*.py"))

    errors = [f for f in python_files if not check_file(f)]

    if errors:
        print(f"Found {len(errors)} files with syntax errors", file=sys.stderr)
        return 1

    print(f"Checked {len(python_files)} files, all valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

---

## Environment Variables

### Accessing GitHub Context

```python
import os

# Get required environment variable
github_token = os.environ["GITHUB_TOKEN"]  # Raises KeyError if missing

# Get optional environment variable with default
debug_mode = os.getenv("DEBUG", "false").lower() == "true"

# Validate required variables early
required_vars = ["GITHUB_TOKEN", "GITHUB_REPOSITORY"]
missing = [v for v in required_vars if v not in os.environ]
if missing:
    print(f"Missing required environment variables: {missing}", file=sys.stderr)
    sys.exit(2)
```

### Workflow Configuration

```yaml
- name: Run with context
  run: python -m scripts.github.process_pr
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
    GITHUB_REPOSITORY: ${{ github.repository }}
    PR_NUMBER: ${{ github.event.pull_request.number }}
```

---

## Testing Python CI Scripts

### Unit Tests with pytest

```python
# tests/test_check_syntax.py
import pytest
from scripts.validation.check_syntax import check_file
from pathlib import Path


def test_check_file_valid_syntax(tmp_path: Path):
    """Valid Python file returns True."""
    test_file = tmp_path / "valid.py"
    test_file.write_text("def foo(): pass\n")

    assert check_file(test_file) is True


def test_check_file_invalid_syntax(tmp_path: Path):
    """Invalid Python file returns False."""
    test_file = tmp_path / "invalid.py"
    test_file.write_text("def foo(\n")  # Incomplete syntax

    assert check_file(test_file) is False
```

### Integration Tests

For scripts that interact with GitHub API:

```python
# tests/integration/test_github_api.py
import pytest
import os


@pytest.mark.skipif(
    "GITHUB_TOKEN" not in os.environ,
    reason="Requires GITHUB_TOKEN for integration tests"
)
def test_github_api_connection():
    """Verify GitHub API connectivity."""
    from scripts.github.client import get_client

    client = get_client()
    assert client.get_rate_limit().remaining > 0
```

---

## Common Patterns

### Structured Output for Workflow Consumption

```python
import json
import os
import sys


def write_output(key: str, value: str) -> None:
    """Write output for GitHub Actions consumption."""
    output_file = os.getenv("GITHUB_OUTPUT")
    if output_file:
        with open(output_file, "a") as f:
            f.write(f"{key}={value}\n")
    else:
        # Fallback for local testing
        print(f"::set-output name={key}::{value}")


def main() -> int:
    result = {"status": "success", "count": 42}
    write_output("result", json.dumps(result))
    return 0
```

### Reading Workflow Inputs

```python
import os
import json


def get_input(name: str, required: bool = False) -> str | None:
    """Get GitHub Actions input value."""
    # GitHub Actions passes inputs as INPUT_<name> environment variables
    env_name = f"INPUT_{name.upper().replace('-', '_')}"
    value = os.getenv(env_name)

    if required and not value:
        raise ValueError(f"Required input '{name}' not provided")

    return value
```

---

## Migration Checklist

When migrating a PowerShell workflow script to Python:

1. [ ] Create Python module in `scripts/` with proper package structure
2. [ ] Add `__init__.py` files for package imports
3. [ ] Use `argparse` for CLI arguments
4. [ ] Use `sys.exit()` with proper exit codes
5. [ ] Log errors to stderr
6. [ ] Add type hints for all functions
7. [ ] Write pytest tests (80%+ coverage target)
8. [ ] Update workflow to call Python instead of PowerShell
9. [ ] Run parallel for 30 days before removing PowerShell version

---

## References

- [ADR-042: Python Migration Strategy](../architecture/ADR-042-python-migration-strategy.md)
- [ADR-006: Thin Workflows](../architecture/ADR-006-thin-workflows.md)
- [ADR-035: Exit Code Standardization](../architecture/ADR-035-exit-code-standardization.md)
