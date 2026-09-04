"""Unit tests for the fail-safe test-selection logic."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.test_selection import select_tests

# Every test below that calls _pull_request_fixture shells out to git with
# check=True, so a host without git would fail them for a reason unrelated to
# selection logic. Same guard the repo already uses in tests/ci.
requires_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _make_repo(root: Path) -> Path:
    """A repo where a change to pkg/core.py must reach tests/test_feature.py."""
    _write(root, "pyproject.toml", "[project]\nname = 'demo'\n")
    _write(root, "pkg/__init__.py", "")
    _write(root, "pkg/core.py", "VALUE = 1\n")
    _write(root, "pkg/mid.py", "from pkg import core\n")
    _write(root, "pkg/leaf.py", "STANDALONE = 2\n")
    _write(root, "pkg/orphan.py", "UNUSED = 3\n")
    _write(root, "tests/test_feature.py", "from pkg import mid\n")
    _write(root, "tests/test_leaf.py", "from pkg import leaf\n")
    return root / ".cache" / "graph.json"


def _patterns(root: Path) -> Path:
    path = root / "patterns.txt"
    path.write_text("# comment\ndocs/**\nlockfile.txt\n", encoding="utf-8")
    return path


def _select(root: Path, changed: list[str]) -> select_tests.Selection:
    cache = root / ".cache" / "graph.json"
    return select_tests.select(changed, root, cache, _patterns(root))


def test_non_python_change_is_full(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    result = _select(tmp_path, ["README.md"])
    assert result.full
    assert "non-Python" in result.reason


def test_conftest_change_is_full(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    _write(tmp_path, "tests/sub/conftest.py", "x = 1\n")
    result = _select(tmp_path, ["tests/sub/conftest.py"])
    assert result.full
    assert "conftest" in result.reason


def test_runtime_read_pattern_is_full(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    result = _select(tmp_path, ["docs/guide.py"])
    assert result.full
    assert "runtime-read pattern" in result.reason


def test_dynamic_import_is_full(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    _write(tmp_path, "pkg/dyn.py", "import importlib\nm = importlib.import_module('pkg.core')\n")
    result = _select(tmp_path, ["pkg/dyn.py"])
    assert result.full
    assert "dynamic import" in result.reason


def test_unmapped_file_is_full(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    result = _select(tmp_path, ["pkg/ghost.py"])
    assert result.full
    assert "unmapped" in result.reason


def test_leaf_change_selects_single_test(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    result = _select(tmp_path, ["pkg/leaf.py"])
    assert not result.full
    assert result.tests == ("tests/test_leaf.py",)


def test_transitive_change_selects_dependent_test(tmp_path: Path) -> None:
    # Regression for issue #4408: a shared module reached only through an
    # intermediate import must still select the test above it. Missing this
    # edge is the false-negative the whole system exists to prevent.
    _make_repo(tmp_path)
    result = _select(tmp_path, ["pkg/core.py"])
    assert not result.full
    assert result.tests == ("tests/test_feature.py",)


def test_literal_dynamic_import_test_is_selected(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    _write(
        tmp_path,
        "tests/test_dynamic_literal.py",
        'import importlib\nMODULE = importlib.import_module("pkg.core")\n',
    )
    result = _select(tmp_path, ["pkg/core.py"])
    assert not result.full
    assert result.tests == ("tests/test_dynamic_literal.py", "tests/test_feature.py")


def test_unresolvable_dynamic_import_test_is_selected_for_any_python_change(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    _write(
        tmp_path,
        "tests/test_dynamic_wildcard.py",
        (
            "import importlib\n"
            "module_name = 'pkg.core'\n"
            "MODULE = importlib.import_module(module_name)\n"
        ),
    )
    result = _select(tmp_path, ["pkg/orphan.py"])
    assert not result.full
    assert result.tests == ("tests/test_dynamic_wildcard.py",)


def test_unresolvable_dynamic_import_helper_selects_its_importing_test(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    _write(
        tmp_path,
        "pkg/dynamic_loader.py",
        (
            "import importlib\n"
            "module_name = 'pkg.core'\n"
            "MODULE = importlib.import_module(module_name)\n"
        ),
    )
    _write(tmp_path, "tests/test_dynamic_helper.py", "from pkg import dynamic_loader\n")
    result = _select(tmp_path, ["pkg/orphan.py"])
    assert not result.full
    assert result.tests == ("tests/test_dynamic_helper.py",)


def test_change_with_no_dependent_test_is_full(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    result = _select(tmp_path, ["pkg/orphan.py"])
    assert result.full
    assert "no test" in result.reason


def test_no_changed_files_is_full(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    result = _select(tmp_path, [])
    assert result.full


def test_multiple_changes_union_tests(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    result = _select(tmp_path, ["pkg/core.py", "pkg/leaf.py"])
    assert not result.full
    assert result.tests == ("tests/test_feature.py", "tests/test_leaf.py")


def test_has_dynamic_import_flags_importlib(tmp_path: Path) -> None:
    path = tmp_path / "d.py"
    path.write_text("from importlib import import_module\n", encoding="utf-8")
    assert select_tests.has_dynamic_import(path)


def test_has_dynamic_import_flags_dunder_import(tmp_path: Path) -> None:
    path = tmp_path / "d.py"
    path.write_text("m = __import__('os')\n", encoding="utf-8")
    assert select_tests.has_dynamic_import(path)


def test_has_dynamic_import_ignores_static_import(tmp_path: Path) -> None:
    path = tmp_path / "d.py"
    path.write_text("import os\nfrom pathlib import Path\n", encoding="utf-8")
    assert not select_tests.has_dynamic_import(path)


def test_has_dynamic_import_treats_unparseable_as_dynamic(tmp_path: Path) -> None:
    path = tmp_path / "d.py"
    path.write_text("def (:\n", encoding="utf-8")
    assert select_tests.has_dynamic_import(path)


def test_load_runtime_read_patterns_skips_comments_and_blanks(tmp_path: Path) -> None:
    patterns = _patterns(tmp_path)
    assert select_tests.load_runtime_read_patterns(patterns) == ("docs/**", "lockfile.txt")


def test_changed_from_git_returns_none_outside_repo(tmp_path: Path) -> None:
    assert select_tests.changed_from_git(tmp_path, "origin/main") is None


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return result.stdout.strip()


def _pull_request_fixture(root: Path) -> tuple[str, str]:
    """A local repo shaped like a pull_request checkout. Returns base and head.

    Models issue #5378 and the PR #5341 report: the pull request branches from
    the base at ``base``, adds ``pkg/x.py``, and the base branch then advances
    on its own with ``.github/workflows/claude.yml``. HEAD is left on the
    synthetic merge commit Actions checks out for `refs/pull/N/merge`, whose
    parents are the advanced base tip and the pull request head. No network:
    every commit is local.
    """
    _git(root, "init", "-q", "-b", "main", ".")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "test")
    _write(root, "README.md", "start\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "base fork point")
    base = _git(root, "rev-parse", "HEAD")

    _git(root, "checkout", "-q", "-b", "pr")
    _write(root, "pkg/x.py", "VALUE = 1\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "pull request change")
    head = _git(root, "rev-parse", "HEAD")

    _git(root, "checkout", "-q", "main")
    _write(root, ".github/workflows/claude.yml", "on: push\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "unrelated base-branch change")

    _git(root, "checkout", "-q", "-b", "merge-ref", "main")
    _git(root, "merge", "-q", "--no-ff", "pr", "-m", "Merge pr into main")
    return base, head


@requires_git
def test_changed_from_git_excludes_base_branch_change_when_head_is_explicit(
    tmp_path: Path,
) -> None:
    base, head = _pull_request_fixture(tmp_path)
    assert select_tests.changed_from_git(tmp_path, base, head) == ["pkg/x.py"]


@requires_git
def test_changed_from_git_leaks_base_branch_change_without_explicit_head(
    tmp_path: Path,
) -> None:
    """Negative control: the pre-#5378 call shape is what pulled the leak in.

    This is the behavior PR #5341 observed. Revert the explicit head argument
    and the assertion above produces this list instead, so the unrelated
    workflow file forces the full suite.
    """
    base, _ = _pull_request_fixture(tmp_path)
    assert select_tests.changed_from_git(tmp_path, base) == [
        ".github/workflows/claude.yml",
        "pkg/x.py",
    ]


@requires_git
def test_changed_from_git_returns_none_for_unfetchable_head(tmp_path: Path) -> None:
    base, _ = _pull_request_fixture(tmp_path)
    assert select_tests.changed_from_git(tmp_path, base, "0" * 40) is None


@requires_git
def test_changed_from_git_returns_none_for_unfetchable_base(tmp_path: Path) -> None:
    _, head = _pull_request_fixture(tmp_path)
    assert select_tests.changed_from_git(tmp_path, "0" * 40, head) is None


def test_cli_prints_full_suite_sentinel(tmp_path: Path, capsys) -> None:
    _make_repo(tmp_path)
    code = select_tests.main(["--repo-root", str(tmp_path), "README.md"])
    assert code == 0
    assert capsys.readouterr().out.strip() == select_tests.FULL_SUITE


def test_cli_prints_selected_tests(tmp_path: Path, capsys) -> None:
    _make_repo(tmp_path)
    code = select_tests.main(["--repo-root", str(tmp_path), "pkg/leaf.py"])
    assert code == 0
    assert capsys.readouterr().out.splitlines() == ["tests/test_leaf.py"]


def test_cli_json_format(tmp_path: Path, capsys) -> None:
    import json

    _make_repo(tmp_path)
    code = select_tests.main(["--repo-root", str(tmp_path), "--format", "json", "pkg/leaf.py"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "full": False,
        "reason": "import-graph subset",
        "tests": ["tests/test_leaf.py"],
    }


def test_cli_from_git_bad_base_is_full(tmp_path: Path, capsys) -> None:
    _make_repo(tmp_path)
    code = select_tests.main(["--repo-root", str(tmp_path), "--from-git", "origin/main"])
    assert code == 0
    assert capsys.readouterr().out.strip() == select_tests.FULL_SUITE
