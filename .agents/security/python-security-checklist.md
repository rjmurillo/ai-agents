# Python Security Checklist

**Reference**: ADR-042 Python Migration Strategy
**Priority**: P1 (required for all new Python code)
**Status**: Active

---

## Overview

This checklist covers security requirements for Python code in the ai-agents repository. All Python scripts MUST pass these checks before merge.

---

## 1. Path Validation (CWE-22)

Path traversal attacks are the most common vulnerability in file-handling code.

### Requirements

- [ ] All user-provided paths are validated
- [ ] Use `pathlib.Path.resolve()` to canonicalize paths
- [ ] Check resolved path starts with expected base directory
- [ ] Reject paths containing `..` before resolution

### Secure Pattern

```python
from pathlib import Path


def validate_path(user_path: str, base_dir: Path) -> Path:
    """Validate user path is within allowed base directory."""
    resolved = (base_dir / user_path).resolve()

    # Ensure path is within base_dir
    if not str(resolved).startswith(str(base_dir.resolve())):
        raise ValueError(f"Path traversal detected: {user_path}")

    return resolved
```

### Vulnerable Pattern (DO NOT USE)

```python
# WRONG: No validation
file_path = os.path.join(base_dir, user_input)
content = open(file_path).read()

# WRONG: String concatenation
file_path = f"{base_dir}/{user_input}"
```

### Shared Utility

Use the project's shared path validation utility:

```python
from scripts.utils.path_validation import validate_safe_path

safe_path = validate_safe_path(user_input, project_root)
```

---

## 2. Input Sanitization

### Requirements

- [ ] All CLI arguments validated via argparse with proper types
- [ ] No direct use of `sys.argv` without validation
- [ ] Environment variables validated before use
- [ ] JSON/YAML input validated against schema

### Secure Pattern

```python
import argparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--count",
        type=int,
        choices=range(1, 101),
        required=True,
        help="Number of items (1-100)"
    )
    parser.add_argument(
        "--format",
        choices=["json", "yaml", "text"],
        default="json",
        help="Output format"
    )
    return parser.parse_args()
```

### Vulnerable Pattern (DO NOT USE)

```python
# WRONG: Direct sys.argv access
count = int(sys.argv[1])  # No validation, can crash

# WRONG: Unchecked environment variable
token = os.environ["TOKEN"]  # Fails silently if missing
```

---

## 3. Subprocess Execution (CWE-78)

Command injection is critical when executing external commands.

### Requirements

- [ ] Use `subprocess.run()` with list arguments
- [ ] NEVER use `shell=True` with user input
- [ ] Validate and sanitize all command arguments
- [ ] Set appropriate timeout values

### Secure Pattern

```python
import subprocess


def run_git_command(repo_path: Path, *args: str) -> str:
    """Run git command safely."""
    # Arguments as list, not string
    result = subprocess.run(
        ["git", "-C", str(repo_path), *args],
        capture_output=True,
        text=True,
        timeout=30,
        check=True
    )
    return result.stdout
```

### Vulnerable Pattern (DO NOT USE)

```python
# WRONG: shell=True with user input
subprocess.run(f"git log --author={user_input}", shell=True)

# WRONG: String command
subprocess.run("git status " + branch_name, shell=True)
```

---

## 4. Secrets Handling (CWE-798)

### Requirements

- [ ] NEVER hardcode secrets, tokens, or passwords
- [ ] Use `os.getenv()` for secrets with proper error handling
- [ ] Log redacted values only
- [ ] No secrets in error messages

### Secure Pattern

```python
import os
import sys


def get_required_secret(name: str) -> str:
    """Get required secret from environment."""
    value = os.getenv(name)
    if not value:
        print(f"ERROR: Required secret {name} not set", file=sys.stderr)
        sys.exit(2)
    return value


# Usage
token = get_required_secret("GITHUB_TOKEN")

# Logging - redact secrets
print(f"Using token: {token[:4]}...{token[-4:]}")  # Show first/last 4 chars only
```

### Vulnerable Pattern (DO NOT USE)

```python
# WRONG: Hardcoded secret
API_KEY = "sk-1234567890abcdef"

# WRONG: Secret in error message
print(f"Auth failed with token: {token}")

# WRONG: Secret in exception
raise ValueError(f"Invalid API key: {api_key}")
```

---

## 5. Dependency Security

### Requirements

- [ ] All dependencies pinned in `pyproject.toml`
- [ ] Use `uv.lock` with hash pinning
- [ ] Run `pip-audit` in CI
- [ ] No unused dependencies

### Verification Commands

```bash
# Check for vulnerabilities
pip-audit --requirement pyproject.toml

# Verify lock file hashes
uv pip install --verify-hashes -r uv.lock

# Check for unused dependencies
pip-autoremove --leaves
```

### pyproject.toml Requirements

```toml
[project]
dependencies = [
    "anthropic>=0.39.0",  # Pinned minimum versions
]

[project.optional-dependencies]
dev = [
    "pip-audit>=2.6.0",  # Security scanning
    "bandit>=1.7.0",     # Static analysis
]
```

---

## 6. Error Handling (CWE-209)

### Requirements

- [ ] No sensitive data in error messages
- [ ] Use generic errors for external users
- [ ] Log detailed errors to secure logs only
- [ ] No stack traces to stdout in production

### Secure Pattern

```python
import logging
import sys

logger = logging.getLogger(__name__)


def process_file(path: Path) -> None:
    try:
        content = path.read_text()
    except FileNotFoundError:
        # Generic message to user
        print("ERROR: File not found", file=sys.stderr)
        # Detailed message to secure log
        logger.error(f"File not found: {path}")
        sys.exit(1)
    except PermissionError:
        print("ERROR: Permission denied", file=sys.stderr)
        logger.error(f"Permission denied accessing: {path}")
        sys.exit(1)
```

### Vulnerable Pattern (DO NOT USE)

```python
# WRONG: Exposes internal paths
print(f"Error reading /home/user/secrets/config.yaml: {e}")

# WRONG: Full stack trace to user
import traceback
traceback.print_exc()
```

---

## 7. Type Safety

### Requirements

- [ ] All functions have type hints
- [ ] Run mypy in CI (configured in pyproject.toml)
- [ ] Use `TypedDict` for structured data
- [ ] Avoid `Any` type where possible

### Secure Pattern

```python
from typing import TypedDict


class SessionConfig(TypedDict):
    session_id: str
    timeout: int
    debug: bool


def process_session(config: SessionConfig) -> bool:
    """Process session with validated configuration."""
    # Type checker ensures correct fields
    return config["timeout"] > 0
```

---

## 8. File Operations

### Requirements

- [ ] Use context managers (`with` statements)
- [ ] Set appropriate file permissions
- [ ] Use temporary files for intermediate data
- [ ] Clean up temporary files on exit

### Secure Pattern

```python
import tempfile
from pathlib import Path


def process_with_temp(data: str) -> Path:
    """Process data using secure temporary file."""
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        delete=False
    ) as f:
        f.write(data)
        temp_path = Path(f.name)

    try:
        # Process temp_path
        result = process_file(temp_path)
        return result
    finally:
        # Always clean up
        temp_path.unlink(missing_ok=True)
```

---

## 9. Serialization Security

### Requirements

- [ ] Never deserialize untrusted data with unsafe methods
- [ ] Use JSON for data interchange
- [ ] Validate structure after deserialization

### Secure Pattern

```python
import json
from typing import Any


def load_config(path: Path) -> dict[str, Any]:
    """Load configuration from JSON file safely."""
    content = path.read_text()
    data = json.loads(content)

    # Validate expected structure
    required_keys = {"version", "settings"}
    if not required_keys.issubset(data.keys()):
        raise ValueError("Invalid configuration structure")

    return data
```

---

## CI Integration

These checks run automatically in `.github/workflows/pytest.yml`:

| Tool | Purpose | Command |
|------|---------|---------|
| bandit | Static security analysis | `bandit -r scripts/ .claude/` |
| pip-audit | Dependency vulnerabilities | `pip-audit` |
| mypy | Type checking | `mypy scripts/` |
| ruff | Security linting rules | `ruff check --select S` |

---

## Pre-Commit Checks

The pre-commit hook runs:

```bash
# Ruff security checks (S rules)
ruff check --select S staged_files.py

# These are non-blocking during transition
# Will become blocking in Phase 3
```

---

## Quick Reference

| Vulnerability | Check | Tool |
|--------------|-------|------|
| Path traversal (CWE-22) | Use validate_safe_path() | bandit B108 |
| Command injection (CWE-78) | No shell=True | bandit B602 |
| Hardcoded secrets (CWE-798) | No literals | bandit B105 |
| SQL injection (CWE-89) | Parameterized queries | bandit B608 |
| Unsafe deserialization (CWE-502) | Use JSON, not unsafe formats | bandit B301 |
| Weak crypto (CWE-327) | No MD5/SHA1 for security | bandit B303 |

---

## References

- [ADR-042: Python Migration Strategy](../architecture/ADR-042-python-migration-strategy.md)
- [OWASP Python Security Guide](https://owasp.org/www-project-web-security-testing-guide/)
- [Bandit Documentation](https://bandit.readthedocs.io/)
- [CWE Top 25](https://cwe.mitre.org/top25/)
