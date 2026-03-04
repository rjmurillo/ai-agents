"""Shared fixtures for GitHub skill script tests."""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add this test directory to sys.path for test_helpers imports
_test_dir = str(Path(__file__).resolve().parent)
if _test_dir not in sys.path:
    sys.path.insert(0, _test_dir)

# Add the github_core lib to sys.path for imports
_project_root = Path(__file__).resolve().parents[3]
_lib_dir = _project_root / ".claude" / "lib"
if str(_lib_dir) not in sys.path:
    sys.path.insert(0, str(_lib_dir))

# Add scripts directories to sys.path for direct imports
_scripts_dir = _project_root / ".claude" / "skills" / "github" / "scripts"
for subdir in ("issue", "milestone", "reactions", "utils", ""):
    path = str(_scripts_dir / subdir) if subdir else str(_scripts_dir)
    if path not in sys.path:
        sys.path.insert(0, path)


@pytest.fixture
def mock_gh_authenticated():
    """Mock assert_gh_authenticated to always pass."""
    with patch("github_core.api.assert_gh_authenticated"):
        yield


@pytest.fixture
def mock_resolve_repo():
    """Mock resolve_repo_params to return test values."""
    with patch(
        "github_core.api.resolve_repo_params",
        return_value={"owner": "test-owner", "repo": "test-repo"},
    ) as mock:
        yield mock


@pytest.fixture
def mock_subprocess_run():
    """Mock subprocess.run for controlling CLI calls."""
    with patch("subprocess.run") as mock:
        yield mock


def make_completed_process(
    stdout: str = "", stderr: str = "", returncode: int = 0,
):
    """Create a mock CompletedProcess.

    Re-exported from test_helpers for backward compatibility.
    Prefer importing from test_helpers directly.
    """
    from test_helpers import make_completed_process as _make
    return _make(stdout=stdout, stderr=stderr, returncode=returncode)
