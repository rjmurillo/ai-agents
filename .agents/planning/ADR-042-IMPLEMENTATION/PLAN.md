# ADR-042 Python Migration Implementation Plan

**Status**: READY FOR EXECUTION
**Created**: 2026-01-18
**Epic**: [#965](https://github.com/rjmurillo/ai-agents/issues/965)
**ADR**: [ADR-042](https://github.com/rjmurillo/ai-agents/blob/main/.agents/architecture/ADR-042-python-migration-strategy.md)
**Timeline**: 12-24 months (phased)
**Priority**: P1

---

## Purpose

This document is the authoritative implementation plan for migrating ai-agents from PowerShell to Python as the primary scripting language. It is designed to be self-contained. An agent with no prior context can execute this plan using only the information provided here.

---

## Background

### Why This Migration Exists

1. **70-second PowerShell startup times**: Each PowerShell tool call starts an independent shell, causing significant latency
2. **No CodeQL for PowerShell**: Deterministic security analysis is unavailable for PowerShell scripts
3. **AI/ML ecosystem is Python-native**: Anthropic SDK, MCP servers, LangChain are all Python
4. **Python is already a prerequisite**: PR #962 introduced skill-installer, which requires Python 3.10+ and UV

### Current State

| Metric | Value |
|--------|-------|
| PowerShell scripts (.ps1) | 222 files |
| PowerShell modules (.psm1) | 13 files |
| Pester test files (.Tests.ps1) | 104 files |
| Total PowerShell LOC | ~48,000 |
| Existing Python files (.py) | 17 files |
| Python version configured | 3.12.8 (`.python-version`) |

### Key Files Requiring Updates

| File | Current State | Required Change |
|------|---------------|-----------------|
| `pyproject.toml` | Does not exist | Create |
| `uv.lock` | Does not exist | Create with hash pinning |
| `tests/conftest.py` | Does not exist | Create pytest infrastructure |
| `.github/workflows/pytest.yml` | Does not exist | Create CI workflow |
| `.github/dependabot.yml` | GitHub Actions only | Add pip ecosystem |
| `.agents/governance/PROJECT-CONSTRAINTS.md` | "MUST NOT create Python" | Change to "SHOULD prefer Python" |
| `CRITICAL-CONTEXT.md` | "PowerShell only" | Change to "Python-first (ADR-042)" |
| `.githooks/pre-commit` | May block Python | Allow .py files |

---

## Phase 1: Foundation (P1 - Execute First)

**Objective**: Establish Python infrastructure so new development can use Python.

**Duration**: 1-2 weeks

**Blocking**: Must complete before Phase 2.

### Task 1.1: Create pyproject.toml

**File**: `pyproject.toml` (repository root)

**Content**:

```toml
[project]
name = "ai-agents"
version = "0.1.0"
description = "AI agent orchestration framework"
readme = "README.md"
requires-python = ">=3.10"
license = {text = "MIT"}

dependencies = [
    "anthropic>=0.39.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-cov>=4.1.0",
    "bandit>=1.7.0",
    "pip-audit>=2.6.0",
    "ruff>=0.1.0",
    "mypy>=1.8.0",
]

[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = "-v --tb=short"
markers = [
    "unit: Unit tests",
    "integration: Integration tests",
    "security: Security-focused tests",
]

[tool.coverage.run]
source = [".claude", "scripts"]
omit = ["**/tests/*", "**/__pycache__/*"]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "if TYPE_CHECKING:",
    "raise NotImplementedError",
]

[tool.bandit]
exclude_dirs = [".venv", "tests", ".git"]
skips = []

[tool.ruff]
target-version = "py310"
line-length = 100
select = ["E", "F", "W", "I", "N", "UP", "B"]
ignore = []

[tool.mypy]
python_version = "3.10"
warn_return_any = true
warn_unused_configs = true
ignore_missing_imports = true
```

**Verification**: `uv pip install -e ".[dev]"` succeeds without errors.

---

### Task 1.2: Generate uv.lock with Hash Pinning

**Purpose**: Supply chain security (Security P0 requirement).

**Command**:

```bash
uv pip compile pyproject.toml --generate-hashes --output-file=uv.lock
```

**Verification**: File `uv.lock` exists and contains SHA256 hashes for all dependencies.

**Important**: Commit `uv.lock` to the repository.

---

### Task 1.3: Create pytest Infrastructure

**File**: `tests/conftest.py`

**Content**:

```python
"""Shared pytest fixtures and configuration."""

import sys
from pathlib import Path

import pytest

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def project_root() -> Path:
    """Return the project root directory."""
    return PROJECT_ROOT


@pytest.fixture
def temp_test_dir(tmp_path: Path) -> Path:
    """Create and return a temporary directory for test files."""
    test_dir = tmp_path / "test_workspace"
    test_dir.mkdir(parents=True, exist_ok=True)
    return test_dir
```

**Verification**: `pytest --collect-only` shows existing tests discovered.

---

### Task 1.4: Create CI Workflow for pytest

**File**: `.github/workflows/pytest.yml`

**Content** (follow existing patterns from `.github/workflows/pester-tests.yml`):

```yaml
name: Python Tests

on:
  push:
    branches: [main, "feat/**", "fix/**"]
  pull_request:
    branches: [main]

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  check-paths:
    runs-on: ubuntu-24.04-arm
    outputs:
      python-changed: ${{ steps.filter.outputs.python }}
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
      - uses: dorny/paths-filter@de90cc6fb38fc0963ad72b210f1f284cd68cea36 # v3.0.2
        id: filter
        with:
          filters: |
            python:
              - '**/*.py'
              - 'pyproject.toml'
              - 'uv.lock'
              - 'tests/conftest.py'
              - '.github/workflows/pytest.yml'

  test:
    needs: check-paths
    if: needs.check-paths.outputs.python-changed == 'true'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2

      - name: Set up Python
        uses: actions/setup-python@0b93645e9fea7318ecaed2b359559ac225c90a2b # v5.3.0
        with:
          python-version: "3.12"

      - name: Install UV
        run: curl -LsSf https://astral.sh/uv/install.sh | sh

      - name: Install dependencies
        run: |
          source $HOME/.local/bin/env
          uv pip install -e ".[dev]"

      - name: Run pytest
        run: |
          source $HOME/.local/bin/env
          pytest --cov --cov-report=xml --junitxml=artifacts/pytest-results.xml

      - name: Run pip-audit
        run: |
          source $HOME/.local/bin/env
          pip-audit --requirement pyproject.toml

      - name: Run Bandit
        run: |
          source $HOME/.local/bin/env
          bandit -r .claude/ scripts/ -f sarif -o artifacts/bandit-results.sarif || true

      - name: Upload test results
        uses: actions/upload-artifact@b4b15b8c7c6ac21ea08fcf65892d2ee8f75cf882 # v4.4.3
        if: always()
        with:
          name: pytest-results
          path: artifacts/
          retention-days: 7

  skip-tests:
    needs: check-paths
    if: needs.check-paths.outputs.python-changed != 'true'
    runs-on: ubuntu-24.04-arm
    steps:
      - run: echo "No Python changes detected, skipping tests"
```

**Verification**: Workflow appears in Actions tab and passes on push.

---

### Task 1.5: Add pip Ecosystem to dependabot.yml

**File**: `.github/dependabot.yml`

**Add after existing github-actions section**:

```yaml
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
      day: "monday"
      time: "09:00"
      timezone: "America/Los_Angeles"
    commit-message:
      prefix: "chore(deps)"
      include: "scope"
    labels:
      - "dependencies"
      - "python"
    groups:
      python-dependencies:
        patterns:
          - "*"
        update-types:
          - "minor"
          - "patch"
    open-pull-requests-limit: 5
```

**Verification**: Dependabot creates PRs for Python dependency updates.

---

### Task 1.6: Update PROJECT-CONSTRAINTS.md

**File**: `.agents/governance/PROJECT-CONSTRAINTS.md`

**Current (around lines 19-22)**:

```markdown
| MUST NOT create bash scripts (.sh) | ADR-005 | Pre-commit hook, code review |
| MUST NOT create Python scripts (.py) | ADR-005 | Pre-commit hook, code review |
| MUST use PowerShell for all scripting (.ps1, .psm1) | ADR-005 | Pre-commit hook, code review |
```

**Replace with**:

```markdown
| MUST NOT create bash scripts (.sh) | ADR-005, ADR-042 | Pre-commit hook, code review |
| SHOULD prefer Python (.py) for new scripts | ADR-042 | Code review |
| MAY use PowerShell (.ps1, .psm1) for existing scripts | ADR-042 | Code review |
```

**Verification**: Grep shows no "MUST NOT create Python" in the file.

---

### Task 1.7: Update CRITICAL-CONTEXT.md

**File**: `CRITICAL-CONTEXT.md`

**Current (first constraint in table)**:

```markdown
| **PowerShell only** (.ps1/.psm1) | ADR-005: Cross-platform consistency | No bash/Python in scripts/ |
```

**Replace with**:

```markdown
| **Python-first** (.py preferred) | ADR-042: AI/ML ecosystem alignment | New scripts in Python; PowerShell grandfathered |
```

**Verification**: File mentions "Python-first" and "ADR-042".

---

### Task 1.8: Update Pre-commit Hook (if needed)

**File**: `.githooks/pre-commit`

**Check for Python blocking logic** (search for `.py` blocking):

```bash
grep -n "\.py" .githooks/pre-commit
```

If blocking logic exists, remove or comment it out.

**Add Python linting section** (non-blocking initially):

```bash
# Python linting (ADR-042)
PYTHON_FILES=$(git diff --cached --name-only --diff-filter=ACM | grep '\.py$' || true)
if [ -n "$PYTHON_FILES" ]; then
    echo "Running Python checks on staged files..."
    if command -v ruff &> /dev/null; then
        echo "$PYTHON_FILES" | xargs ruff check --fix || true
    fi
fi
```

**Verification**: Committing a `.py` file does not fail pre-commit.

---

### Phase 1 Completion Checklist

- [ ] `pyproject.toml` exists and `uv pip install -e ".[dev]"` succeeds
- [ ] `uv.lock` exists with hash pinning
- [ ] `tests/conftest.py` exists
- [ ] `.github/workflows/pytest.yml` exists and passes
- [ ] `.github/dependabot.yml` includes pip ecosystem
- [ ] `PROJECT-CONSTRAINTS.md` says "SHOULD prefer Python"
- [ ] `CRITICAL-CONTEXT.md` says "Python-first"
- [ ] Pre-commit hook allows `.py` files

---

## Phase 2: New Development Guidelines (P2)

**Objective**: Enable Python-first development with proper patterns and security controls.

**Duration**: 2-4 weeks

**Blocking**: Phase 1 must be complete.

### Task 2.1: Document CI/CD Migration Patterns

**File**: `.agents/guides/python-cicd-patterns.md`

**Content**: Document how to:

- Invoke Python modules from GitHub Actions: `python -m module.name` or `python path/to/script.py`
- Handle errors: Use `sys.exit(1)` for failures, log to stderr
- Pass parameters: Use `argparse` for command-line arguments
- Comply with ADR-006: Workflow YAML = orchestration only, Python modules = all logic

---

### Task 2.2: Create Python Security Checklist

**File**: `.agents/security/python-security-checklist.md`

**Content**:

1. **Path Validation (CWE-22)**: Use `pathlib.Path.resolve()`, check path starts with base directory
2. **Input Sanitization**: Validate all CLI args, use `subprocess` with list args (not shell=True)
3. **Secrets Handling**: Use `os.getenv()` for required secrets, never hardcode
4. **Dependency Security**: Pin in `pyproject.toml`, use `uv.lock`, run `pip-audit` in CI

---

### Task 2.3: Create Path Validation Utility

**File**: `scripts/utils/path_validation.py`

**Content**:

```python
"""Path validation utilities for CWE-22 protection."""

from pathlib import Path
import re


def validate_safe_path(path: str | Path, base_dir: str | Path) -> Path:
    """
    Validate that a path is safe and within the base directory.

    Args:
        path: The path to validate
        base_dir: The base directory that path must be within

    Returns:
        Resolved Path object

    Raises:
        ValueError: If path is unsafe or outside base_dir
    """
    resolved_path = Path(path).resolve()
    resolved_base = Path(base_dir).resolve()

    if not str(resolved_path).startswith(str(resolved_base)):
        raise ValueError(f"Path {path} is outside base directory {base_dir}")

    return resolved_path


def is_safe_filename(filename: str) -> bool:
    """
    Check if a filename is safe (no path traversal characters).

    Args:
        filename: The filename to check

    Returns:
        True if safe, False otherwise
    """
    if ".." in filename:
        return False
    if "/" in filename or "\\" in filename:
        return False
    if not re.match(r'^[a-zA-Z0-9_.-]+$', filename):
        return False
    return True
```

**Tests**: Create `tests/test_path_validation.py` with tests for traversal attacks, symlinks, edge cases.

---

### Task 2.4: Create Developer Migration Guide

**File**: `.agents/guides/python-for-powershell-developers.md`

**Content**: Side-by-side comparison of:

| PowerShell | Python |
|------------|--------|
| `$variable` | `variable` |
| `function Verb-Noun {}` | `def verb_noun():` |
| `if ($x -eq $y)` | `if x == y:` |
| `foreach ($item in $list)` | `for item in list:` |
| `try {} catch {}` | `try: except:` |
| `Get-Content $file` | `Path(file).read_text()` |
| `ConvertFrom-Json` | `json.loads()` |
| `Describe/It` (Pester) | `def test_*()` (pytest) |

---

### Phase 2 Completion Checklist

- [ ] CI/CD migration patterns documented
- [ ] Python security checklist documented
- [ ] Path validation utility created with tests
- [ ] Developer migration guide created

---

## Phase 3: Migration (P3 - Future)

**Objective**: Incrementally migrate existing PowerShell scripts to Python.

**Duration**: 12-24 months

**Approach**: "Leave campsite better than found" - migrate scripts when touching them.

### Task 3.1: Identify Migration Priorities

**Command to find high-churn scripts**:

```bash
git log --since="90 days ago" --name-only --pretty=format: | grep '\.ps1$' | sort | uniq -c | sort -rn | head -20
```

**Tier Classification**:

- **Tier 1** (>10 commits in 90 days): Migrate first
- **Tier 2** (5-10 commits): Migrate when convenient
- **Tier 3** (<5 commits): Migrate opportunistically

---

### Task 3.2: Migration Process Per Script

For each script to migrate:

1. Create Python equivalent: `script.ps1` -> `script.py`
2. Port logic using migration guide patterns
3. Add type hints for parameters and return values
4. Create pytest tests (80%+ coverage)
5. Update CI workflows to call Python version
6. Run parallel for 30-90 days (both versions)
7. Deprecate PowerShell version (add header comment)
8. Delete PowerShell version after verification period

---

### Task 3.3: Deprecation Timeline

| Phase | Duration | Action |
|-------|----------|--------|
| Parallel | 30-90 days | Both versions exist, Python is primary |
| Deprecation | 30 days | PowerShell marked deprecated, Python exclusive |
| Deletion | After verification | Remove PowerShell file |

**Deletion Criteria**:

- Python version stable for 30+ days
- No open issues related to Python version
- All tests passing
- Team approval

---

## Security Controls Summary

| Control | Priority | Phase | Status |
|---------|----------|-------|--------|
| uv.lock with hash pinning | P0 | 1 | Required |
| pip ecosystem in Dependabot | P0 | 1 | Required |
| pip-audit in CI | P1 | 1 | Required |
| Bandit in CI | P1 | 1 | Required |
| Path validation utility | P1 | 2 | Required |
| Security checklist | P1 | 2 | Required |

---

## References

| Document | URL |
|----------|-----|
| ADR-042 | https://github.com/rjmurillo/ai-agents/blob/main/.agents/architecture/ADR-042-python-migration-strategy.md |
| Epic #965 | https://github.com/rjmurillo/ai-agents/issues/965 |
| PR #963 (ADR acceptance) | https://github.com/rjmurillo/ai-agents/pull/963 |
| PR #962 (skill-installer) | https://github.com/rjmurillo/ai-agents/pull/962 |
| Feasibility Analysis | https://github.com/rjmurillo/ai-agents/blob/main/.agents/analysis/ADR-042-python-migration-feasibility.md |
| Security Review | https://github.com/rjmurillo/ai-agents/blob/main/.agents/critique/ADR-042-security-review.md |
| Debate Log | https://github.com/rjmurillo/ai-agents/blob/main/.agents/critique/ADR-042-debate-log.md |

---

## Execution Notes

1. **Start with Phase 1** - Do not skip to Phase 2 or 3
2. **One task at a time** - Complete and verify each task before moving to the next
3. **Test everything** - Run verification commands after each task
4. **Commit incrementally** - Small, focused commits with conventional commit messages
5. **Follow existing patterns** - Match the style of existing Python files in `.claude/hooks/`

---

*Plan synthesized from: traycerai analysis, AI PRD generation, ADR-042 debate artifacts*
*Last updated: 2026-01-18*
