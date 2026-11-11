"""A new Markdown file re-selects the tests that scan the tracked tree (issue #7286).

testmon 2.2.0 records Python lines only. A test that runs ``git grep`` over the
tree has no dependency on a docs page, and a brand-new page is named by no test,
so a docs-only push selected nothing while CI failed
the decommission-scope test on PR #7263. These tests cover the
tree-scanner detector, the Markdown diff, the selection change, and a replay with
real testmon (with and without xdist) whose control run shows the gap.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.validation import testmon_data_inputs as inputs
from tests.validation.testmon_repo_helpers import (
    OTHER_TEST,
    PLUGIN_FLAG,
    Select,
    git,
    make_repo,
    run_pytest,
    write,
)

CORPUS = "tests/evals/profile-behavior-runtime-fixtures.json"
READER = "tests/test_profile_behavior_fixtures.py"
READER_TEXT = 'PATH = ROOT / "tests" / "evals" / "profile-behavior-runtime-fixtures.json"\n'
SCANNER = "tests/test_scope_scan_example.py"
SCANNER_TEXT = 'subprocess.run([git, "grep", "-ic", TOKEN, "--", "."], cwd=repo)\n'


# --- tree scanners ----------------------------------------------------------


def test_a_test_that_runs_git_grep_is_a_tree_scanner() -> None:
    sources = {SCANNER: SCANNER_TEXT, "tests/test_other.py": "def test_x(): pass\n"}
    assert inputs.tree_scanner_modules(sources) == {SCANNER}


def test_a_test_that_runs_git_ls_files_is_a_tree_scanner() -> None:
    sources = {"tests/test_tracked.py": "run(['git', 'ls-files', '-z'])\n"}
    assert inputs.tree_scanner_modules(sources) == {"tests/test_tracked.py"}


def test_a_helper_that_runs_git_grep_is_not_returned() -> None:
    assert inputs.tree_scanner_modules({"tests/scan_helpers.py": SCANNER_TEXT}) == set()


def test_prose_that_mentions_grep_is_not_a_tree_scanner() -> None:
    sources = {"tests/test_prose.py": '"""We grep the tree and list ls-files."""\n'}
    assert inputs.tree_scanner_modules(sources) == set()


def test_a_new_markdown_file_is_reported(tmp_path: Path) -> None:
    root = make_repo(tmp_path, {"tests/test_other.py": "pass\n"})
    write(root, "docs/training/new-page.md", "# New\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "docs")
    assert inputs.changed_markdown(root) == ["docs/training/new-page.md"]


def test_python_only_diff_reports_no_markdown(tmp_path: Path) -> None:
    root = make_repo(tmp_path, {"tests/test_other.py": "pass\n"})
    write(root, "tests/test_other.py", "pass  # edited\n")
    assert inputs.changed_markdown(root) == []


def test_markdown_without_a_base_ref_reports_unknown(tmp_path: Path) -> None:
    assert inputs.changed_markdown(tmp_path) is None


def _docs_project(root: Path) -> Path:
    return make_repo(
        root,
        {
            SCANNER: SCANNER_TEXT,
            "tests/test_other.py": "def test_x(): pass\n",
            "docs/index.md": "# Docs\n",
        },
    )


def test_reselect_runs_tree_scanners_when_a_docs_file_is_added(tmp_path: Path) -> None:
    root = _docs_project(tmp_path)
    write(root, "docs/training/memory-and-learning.md", "# New\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "docs")
    select = Select([SCANNER, "tests/test_other.py"], [f"{SCANNER}::test_a"])
    assert inputs.reselect(select, root) == {SCANNER}
    assert select.deselected_files == ["tests/test_other.py"]
    assert select.deselected_tests == []


def test_reselect_runs_tree_scanners_when_a_staged_docs_file_is_added(tmp_path: Path) -> None:
    root = _docs_project(tmp_path)
    write(root, "docs/new.md", "# New\n")
    git(root, "add", "docs/new.md")
    select = Select([SCANNER], [])
    assert inputs.reselect(select, root) == {SCANNER}


def test_reselect_leaves_tree_scanners_deselected_for_a_python_only_diff(tmp_path: Path) -> None:
    root = _docs_project(tmp_path)
    write(root, "tests/test_other.py", "def test_x(): assert True\n")
    select = Select([SCANNER, "tests/test_other.py"], [f"{SCANNER}::test_a"])
    assert inputs.reselect(select, root) == set()
    assert select.deselected_files == [SCANNER, "tests/test_other.py"]
    assert select.deselected_tests == [f"{SCANNER}::test_a"]


def test_reselect_with_an_unknown_diff_runs_every_tree_scanner(tmp_path: Path) -> None:
    write(tmp_path, SCANNER, SCANNER_TEXT)
    write(tmp_path, "tests/test_other.py", "def test_x(): pass\n")
    select = Select([SCANNER, "tests/test_other.py"], [])
    assert inputs.reselect(select, tmp_path) == {SCANNER}
    assert select.deselected_files == ["tests/test_other.py"]


def test_reselect_unions_corpus_readers_and_tree_scanners(tmp_path: Path) -> None:
    root = make_repo(
        tmp_path,
        {CORPUS: "{}\n", READER: READER_TEXT, SCANNER: SCANNER_TEXT, "docs/index.md": "# D\n"},
    )
    write(root, CORPUS, '{"a": 1}\n')
    write(root, "docs/index.md", "# Edited\n")
    select = Select([READER, SCANNER], [])
    assert inputs.reselect(select, root) == {READER, SCANNER}
    assert select.deselected_files == []


# --- replay: a new docs file and a tree-scanning test ------------------------

_SCANNER_TEST = """
import subprocess


def test_no_file_names_the_retired_backend():
    result = subprocess.run(
        ["git", "grep", "-il", "retired" + "-backend", "--", "."],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.stdout == ""
"""


def _docs_replay(project: Path, *flags: str) -> tuple[int, str]:
    """Record a passing run, then commit a new docs page that names the token."""
    pytest.importorskip("testmon")
    make_repo(
        project,
        {
            "tests/test_scanner.py": _SCANNER_TEST,
            "tests/test_other.py": OTHER_TEST,
            "docs/index.md": "# Docs\n",
            ".gitignore": ".testmondata*\n__pycache__/\n.pytest_cache/\n",
        },
    )
    code, output = run_pytest(project, *flags)
    assert code == 0, output
    write(project, "docs/training/new-page.md", "This page names retired-backend.\n")
    git(project, "add", "-A")
    git(project, "commit", "-q", "-m", "docs: add page")
    return run_pytest(project, *flags)


def test_control_without_the_plugin_testmon_skips_the_scanner_for_a_new_docs_page(
    tmp_path: Path,
) -> None:
    """Pins the gap behind issue #7286. If an upgrade makes this fail, testmon tracks git reads."""
    code, output = _docs_replay(tmp_path)
    assert code == 0, output
    assert "no tests ran" in output
    assert "failed" not in output


def test_the_plugin_runs_the_scanner_for_a_new_docs_page(tmp_path: Path) -> None:
    code, output = _docs_replay(tmp_path, PLUGIN_FLAG)
    assert code == 1, output
    assert "test_no_file_names_the_retired_backend" in output
    assert "1 failed" in output


def test_the_plugin_runs_the_scanner_for_a_new_docs_page_under_xdist(tmp_path: Path) -> None:
    pytest.importorskip("xdist")
    code, output = _docs_replay(tmp_path, PLUGIN_FLAG, "-n", "2")
    assert code == 1, output
    assert "1 failed" in output
