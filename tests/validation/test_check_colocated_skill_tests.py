"""Tests for scripts/validation/check_colocated_skill_tests.py (issue #4838)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "validation"))

from check_colocated_skill_tests import (
    check_paths,
    is_colocated_skill_test,
    main,
)

# ---------------------------------------------------------------------------
# is_colocated_skill_test: positive cases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        ".claude/skills/foo/tests/test_bar.py",
        ".claude/skills/my-skill/tests/test_something.py",
        "src/copilot-cli/skills/bar/tests/test_baz.py",
        "src/claude/skills/qux/tests/test_quux.py",
        ".claude/skills/deep/tests/subdir/test_nested.py",
        ".claude/skills/skill-name/tests/integration/test_e2e.py",
    ],
)
def test_positive_colocated_test(path: str) -> None:
    assert is_colocated_skill_test(path) is True


# ---------------------------------------------------------------------------
# is_colocated_skill_test: negative cases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        # Correct location under tests/skills/
        "tests/skills/foo/test_bar.py",
        # Non-test file in skill tests dir
        ".claude/skills/foo/tests/__init__.py",
        ".claude/skills/foo/tests/conftest.py",
        ".claude/skills/foo/tests/helpers.py",
        # Scripts, not tests
        ".claude/skills/foo/scripts/test_url_routing.py",
        # Not a shipped root
        "packages/skills/foo/tests/test_bar.py",
        # Too shallow (no skill name between root and tests)
        ".claude/skills/tests/test_bar.py",
        # Non-python
        ".claude/skills/foo/tests/test_bar.js",
        # Empty path
        "",
    ],
)
def test_negative_not_colocated_test(path: str) -> None:
    assert is_colocated_skill_test(path) is False


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_conftest_and_init_not_flagged() -> None:
    """__init__.py and conftest.py are not tests even inside tests/."""
    assert is_colocated_skill_test(".claude/skills/x/tests/__init__.py") is False
    assert is_colocated_skill_test(".claude/skills/x/tests/conftest.py") is False


def test_suffix_test_py_detected() -> None:
    """Files ending with _test.py are also test files."""
    assert is_colocated_skill_test(".claude/skills/x/tests/foo_test.py") is True


def test_deeply_nested_test() -> None:
    """Tests nested several levels deep under tests/ are still caught."""
    path = ".claude/skills/my-skill/tests/integration/api/test_endpoints.py"
    assert is_colocated_skill_test(path) is True


# ---------------------------------------------------------------------------
# check_paths: legacy tolerance
# ---------------------------------------------------------------------------


def test_check_paths_allows_existing(tmp_path: Path) -> None:
    """Files on HEAD are tolerated (legacy allowance)."""
    # Set up a git repo with an existing test
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path, capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path, capture_output=True, check=True,
    )
    # Create a legacy test file
    test_dir = tmp_path / ".claude" / "skills" / "foo" / "tests"
    test_dir.mkdir(parents=True)
    (test_dir / "test_legacy.py").write_text("# legacy")
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "init", "--no-verify"],
        cwd=tmp_path, capture_output=True, check=True,
    )

    # Existing file should be tolerated
    violations = check_paths(
        [".claude/skills/foo/tests/test_legacy.py"],
        repo_root=tmp_path,
        allow_existing=True,
    )
    assert violations == []


def test_check_paths_blocks_new(tmp_path: Path) -> None:
    """New files not on HEAD are blocked."""
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path, capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path, capture_output=True, check=True,
    )
    (tmp_path / "README.md").write_text("# repo")
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "init", "--no-verify"],
        cwd=tmp_path, capture_output=True, check=True,
    )

    violations = check_paths(
        [".claude/skills/new-skill/tests/test_new.py"],
        repo_root=tmp_path,
        allow_existing=True,
    )
    assert violations == [".claude/skills/new-skill/tests/test_new.py"]


# ---------------------------------------------------------------------------
# main() CLI
# ---------------------------------------------------------------------------


def test_main_no_violations() -> None:
    """Exit 0 when no colocated tests are passed."""
    assert main(["tests/skills/foo/test_bar.py"]) == 0


def test_main_with_violation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Exit 1 when a new colocated test is detected."""
    # Create minimal git repo
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@t.com"],
        cwd=tmp_path, capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "T"],
        cwd=tmp_path, capture_output=True, check=True,
    )
    (tmp_path / "x").write_text("")
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "i", "--no-verify"],
        cwd=tmp_path, capture_output=True, check=True,
    )

    result = main([
        "--repo-root", str(tmp_path),
        ".claude/skills/new/tests/test_bad.py",
    ])
    assert result == 1
