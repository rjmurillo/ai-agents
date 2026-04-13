# PostToolUse Hooks

## Overview

PostToolUse hooks are triggered automatically by Claude Code after file Write/Edit operations. They enable non-blocking, automatic workflows like linting, formatting, and security scanning.

## Execution Model

**Trigger**: After `Write` or `Edit` tool use
**Input**: JSON via stdin containing tool parameters and context
**Exit Requirement**: **Always exit 0** (non-blocking)

PostToolUse hooks must never fail the primary operation. All errors should be logged as warnings, and the hook should always exit with code 0.

## Available Hooks

| Hook | Purpose | File Types | Performance |
|------|---------|------------|-------------|
| `invoke_markdown_auto_lint.py` | Auto-format markdown files | `*.md` | <2s |
| `invoke_codeql_quick_scan.py` | Security scan for code files | `*.py`, `*.yml` (workflows) | 5-30s |

## Hook Input Format

Hooks receive JSON via stdin:

```json
{
  "tool_input": {
    "file_path": "/absolute/path/to/file.ext",
    "content": "file content..."
  },
  "cwd": "/project/directory",
  "tool_name": "Write"
}
```

**Key Fields:**

- `tool_input.file_path`: Absolute path to the file that was written/edited
- `cwd`: Project directory (fallback: use `os.environ.get("CLAUDE_PROJECT_DIR")`)
- `tool_name`: Tool that triggered the hook (`Write` or `Edit`)

## Writing a New Hook

### Template

```python
#!/usr/bin/env python3
"""
Brief description of what the hook does.

Hook Type: PostToolUse
Matcher: Write|Edit
Filter: File type criteria (e.g., *.py, *.md)
Exit Codes:
    0 = Always (non-blocking hook, all errors are warnings)

Related documentation or planning documents.
"""

import json
import logging
import os
import sys

# Non-blocking hook: verbose output only, never raise to caller
logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

if "--verbose" in sys.argv:
    logger.setLevel(logging.DEBUG)


def get_file_path(hook_input: dict) -> str | None:
    """Extract file_path from hook input."""
    return hook_input.get("tool_input", {}).get("file_path")


def get_project_dir(hook_input: dict) -> str | None:
    """Return project directory, preferring the environment variable."""
    return os.environ.get("CLAUDE_PROJECT_DIR") or hook_input.get("cwd")


def should_process_file(file_path: str | None) -> bool:
    """Determine if the file should trigger hook logic."""
    if not file_path:
        return False

    if not os.path.exists(file_path):
        logger.debug("File does not exist: %s", file_path)
        return False

    # Add file type filtering logic here.
    # Example: return file_path.lower().endswith(".ext")

    return True


def main() -> None:
    if sys.stdin.isatty():
        sys.exit(0)

    raw = sys.stdin.read()
    if not raw.strip():
        sys.exit(0)

    hook_input = json.loads(raw)
    file_path = get_file_path(hook_input)

    # Filter: only process relevant file types.
    if not should_process_file(file_path):
        sys.exit(0)

    project_dir = get_project_dir(hook_input)
    original_dir = os.getcwd()

    try:
        if project_dir:
            os.chdir(project_dir)

        # TODO: Implement hook logic here.
        # Example: run linter, formatter, scanner, etc.

        print(f"\n**Hook Name**: Processed `{file_path}`\n")
    finally:
        os.chdir(original_dir)


try:
    main()
except (json.JSONDecodeError, ValueError) as exc:
    logger.debug("Hook: Failed to parse input JSON - %s", exc)
except OSError as exc:
    logger.debug("Hook: File system error - %s", exc)
except Exception as exc:  # noqa: BLE001
    logger.debug("Hook unexpected error: %s - %s", type(exc).__name__, exc)

# Always exit 0 (non-blocking hook).
sys.exit(0)
```

### Best Practices

1. **Always Exit 0**: Hooks must never block the user's primary operation
2. **Fast Execution**: Target <5 seconds; use timeouts for longer operations
3. **Graceful Degradation**: If dependencies missing, exit silently
4. **Verbose Logging**: Use `logger.debug()` for debugging (not `print` to stderr)
5. **User-Facing Messages**: Use `print()` for status messages shown to user
6. **File Type Filtering**: Only process files relevant to the hook
7. **Error Handling**: Catch all exceptions, log as warnings, never raise

### File Type Filtering Examples

```python
from pathlib import Path

# Markdown files only
if Path(file_path).suffix.lower() != ".md":
    sys.exit(0)

# Python files only
if Path(file_path).suffix.lower() != ".py":
    sys.exit(0)

# GitHub Actions workflows only
p = Path(file_path)
if p.suffix.lower() in (".yml", ".yaml"):
    # Normalize to forward slashes for cross-platform matching.
    normalized = p.as_posix()
    if ".github/workflows/" in normalized:
        # Process workflow file.
        pass
```

### Performance Guidelines

| Hook Type | Target Time | Max Time |
|-----------|-------------|----------|
| Formatting/Linting | <2s | 5s |
| Quick Security Scan | <15s | 30s |
| Full Analysis | Avoid in PostToolUse | Use pre-commit instead |

Use timeouts for operations that may exceed target time:

```python
import subprocess

try:
    result = subprocess.run(
        ["your-tool", "--flag", file_path],
        capture_output=True,
        text=True,
        timeout=30,
    )
    # Process result.stdout / result.returncode here.
except subprocess.TimeoutExpired:
    print("\n**Hook WARNING**: Operation timed out\n")
except FileNotFoundError:
    logger.debug("Tool not found; skipping hook.")
```

## Testing Hooks

### Manual Testing

```bash
# Create test input and pipe to hook
test_input='{"tool_input": {"file_path": "/path/to/test/file.py"}, "cwd": "/path/to/project", "tool_name": "Write"}'
echo "$test_input" | python3 .claude/hooks/PostToolUse/your_hook.py
```

### Automated Testing

Use pytest for automated testing:

```python
import json
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).parent / "your_hook.py"


def run_hook(tool_input: dict) -> subprocess.CompletedProcess:
    payload = json.dumps(tool_input)
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
    )


def test_exits_zero_nonblocking(tmp_path):
    """Hook must always exit 0 (non-blocking)."""
    target = tmp_path / "test.py"
    target.write_text("x = 1\n")
    result = run_hook({"tool_input": {"file_path": str(target)}, "cwd": str(tmp_path)})
    assert result.returncode == 0


def test_gracefully_handles_missing_file(tmp_path):
    """Hook must not raise when the target file does not exist."""
    result = run_hook({"tool_input": {"file_path": "/nonexistent.py"}, "cwd": str(tmp_path)})
    assert result.returncode == 0
```

## Debugging

### Enable Verbose Output

```bash
python3 .claude/hooks/PostToolUse/your_hook.py --verbose
```

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| Hook not running | File type not matched | Check file extension filter |
| Hook running slow | No timeout on long operation | Add `timeout=` to `subprocess.run()` |
| User sees errors | Unhandled exception raised to caller | Wrap in `try/except`, always `sys.exit(0)` |
| Hook blocks user | Not exiting with 0 | Ensure all code paths call `sys.exit(0)` |

## References

- **invoke_markdown_auto_lint.py**: Reference implementation for simple hooks
- **invoke_codeql_quick_scan.py**: Reference implementation for complex hooks with timeouts
- **ADR-035**: Exit code standardization
- **Claude Code Hooks Documentation**: <https://code.claude.com/docs/en/hooks>
