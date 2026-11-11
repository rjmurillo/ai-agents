"""A changed eval corpus re-selects the tests that read it (pre-push gap).

testmon 2.2.0 tracks Python lines only, so editing ``tests/evals/*.json`` selected
nothing and four failing tests reached a push on PR #7126.
``scripts.validation.testmon_data_inputs`` closes that. These tests cover the
pure helpers, the git diff against a throwaway repository, the selection hooks
with fakes, and a replay with real testmon (with and without xdist) whose control
run shows the gap.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from scripts.validation import testmon_data_inputs as inputs
from scripts.validation import testmon_scoped_sync as sync
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


# --- reader_modules ---------------------------------------------------------


def test_a_test_naming_the_changed_corpus_is_a_reader() -> None:
    sources = {READER: READER_TEXT, "tests/test_other.py": "def test_x(): pass\n"}
    assert inputs.reader_modules([CORPUS], sources) == {READER}


def test_a_test_that_does_not_name_the_corpus_is_not_a_reader() -> None:
    sources = {"tests/test_other.py": 'x = "tests/evals/other.json"\n'}
    assert inputs.reader_modules([CORPUS], sources) == set()


def test_a_directory_loader_is_a_reader_of_a_file_in_that_directory() -> None:
    changed = ["tests/evals/rule-scenarios/voice.json"]
    sources = {
        "tests/test_loader.py": 'D = ROOT / "tests" / "evals" / "rule-scenarios"\n',
        "tests/test_unrelated.py": 'D = "rule-scenarios"\n',
    }
    assert inputs.reader_modules(changed, sources) == {"tests/test_loader.py"}


def test_a_helper_that_names_the_corpus_makes_its_importers_readers() -> None:
    sources = {
        "tests/corpus_support.py": READER_TEXT,
        "tests/test_via_helper.py": "from tests.corpus_support import load\n",
        "tests/test_other.py": "def test_x(): pass\n",
    }
    assert inputs.reader_modules([CORPUS], sources) == {"tests/test_via_helper.py"}


def test_a_helper_is_never_returned_as_a_reader() -> None:
    assert inputs.reader_modules([CORPUS], {"tests/corpus_support.py": READER_TEXT}) == set()


def test_nothing_changed_means_no_readers() -> None:
    assert inputs.reader_modules([], {READER: READER_TEXT}) == set()


# --- git discovery ----------------------------------------------------------


def test_an_edited_corpus_is_reported(tmp_path: Path) -> None:
    root = make_repo(tmp_path, {CORPUS: "{}\n", "tests/test_x.py": "pass\n"})
    write(root, CORPUS, '{"a": 1}\n')
    assert inputs.changed_data_inputs(root) == [CORPUS]


def test_a_committed_edit_on_the_branch_is_reported(tmp_path: Path) -> None:
    root = make_repo(tmp_path, {CORPUS: "{}\n"})
    write(root, CORPUS, '{"a": 1}\n')
    git(root, "commit", "-q", "-am", "edit")
    assert inputs.changed_data_inputs(root) == [CORPUS]


def test_python_and_unrelated_paths_are_not_reported(tmp_path: Path) -> None:
    root = make_repo(
        tmp_path, {CORPUS: "{}\n", "tests/evals/test_t.py": "a = 1\n", "docs/a.md": "a\n"}
    )
    write(root, "tests/evals/test_t.py", "a = 2\n")
    write(root, "docs/a.md", "b\n")
    assert inputs.changed_data_inputs(root) == []


def test_an_unchanged_tree_reports_nothing(tmp_path: Path) -> None:
    assert inputs.changed_data_inputs(make_repo(tmp_path, {CORPUS: "{}\n"})) == []


def test_a_repository_without_a_base_ref_reports_unknown(tmp_path: Path) -> None:
    git(tmp_path, "init", "-q", "-b", "other")
    assert inputs.changed_data_inputs(tmp_path) is None


def test_a_missing_git_binary_reports_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_args: Any, **_kwargs: Any) -> None:
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", boom)
    assert inputs.changed_data_inputs(tmp_path) is None


def test_a_timeout_reports_unknown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def slow(*_args: Any, **_kwargs: Any) -> None:
        raise subprocess.TimeoutExpired("git", 1)

    monkeypatch.setattr(subprocess, "run", slow)
    assert inputs.changed_data_inputs(tmp_path) is None


def test_all_data_inputs_lists_non_python_files_only(tmp_path: Path) -> None:
    write(tmp_path, CORPUS, "{}\n")
    write(tmp_path, "tests/evals/agents/a.md", "a\n")
    write(tmp_path, "tests/evals/test_t.py", "a = 1\n")
    assert inputs.all_data_inputs(tmp_path) == ["tests/evals/agents/a.md", CORPUS]


def test_all_data_inputs_without_the_directory_is_empty(tmp_path: Path) -> None:
    assert inputs.all_data_inputs(tmp_path) == []


# --- reselect ---------------------------------------------------------------


def _project(root: Path) -> Path:
    return make_repo(
        root,
        {CORPUS: "{}\n", READER: READER_TEXT, "tests/test_other.py": "def test_x(): pass\n"},
    )


def test_reselect_runs_the_readers_of_an_edited_corpus(tmp_path: Path) -> None:
    root = _project(tmp_path)
    write(root, CORPUS, '{"a": 1}\n')
    select = Select(
        [READER, "tests/test_other.py"], [f"{READER}::test_a", "tests/test_other.py::t"]
    )
    assert inputs.reselect(select, root) == {READER}
    assert select.deselected_files == ["tests/test_other.py"]
    assert select.deselected_tests == ["tests/test_other.py::t"]


def test_reselect_leaves_the_selection_alone_when_no_corpus_changed(tmp_path: Path) -> None:
    root = _project(tmp_path)
    select = Select([READER], [f"{READER}::test_a"])
    assert inputs.reselect(select, root) == set()
    assert select.deselected_files == [READER]
    assert select.deselected_tests == [f"{READER}::test_a"]


def test_reselect_with_an_unknown_diff_runs_every_reader(tmp_path: Path) -> None:
    write(tmp_path, CORPUS, "{}\n")
    write(tmp_path, READER, READER_TEXT)
    write(tmp_path, "tests/test_other.py", "def test_x(): pass\n")
    select = Select([READER, "tests/test_other.py"], [])
    assert inputs.reselect(select, tmp_path) == {READER}
    assert select.deselected_files == ["tests/test_other.py"]


def test_reselect_with_a_changed_corpus_nobody_reads_changes_nothing(tmp_path: Path) -> None:
    root = make_repo(tmp_path, {"tests/evals/orphan.json": "{}\n", "tests/test_other.py": "pass\n"})
    write(root, "tests/evals/orphan.json", '{"a": 1}\n')
    select = Select(["tests/test_other.py"], [])
    assert inputs.reselect(select, root) == set()
    assert select.deselected_files == ["tests/test_other.py"]


# --- hooks ------------------------------------------------------------------


class _Manager:
    def __init__(self, select: Select | None) -> None:
        self._select = select

    def get_plugin(self, name: str) -> object | None:
        return self._select if name == "TestmonSelect" else None


class _Config:
    def __init__(self, select: Select | None, root: Path | None, workerinput: dict | None) -> None:
        self.pluginmanager = _Manager(select)
        if root is not None:
            self.rootpath = root
        if workerinput is not None:
            self.workerinput = workerinput


def _broadcast(config: Any) -> Any:
    return sync._SelectionBroadcast(config)


class _Node:
    def __init__(self) -> None:
        self.workerinput: dict[str, Any] = {}


def test_the_controller_sends_workers_a_selection_that_includes_the_readers(tmp_path: Path) -> None:
    root = _project(tmp_path)
    write(root, CORPUS, '{"a": 1}\n')
    select = Select([READER, "tests/test_other.py"], [])
    node = _Node()
    _broadcast(_Config(select, root, None)).pytest_configure_node(node)
    assert node.workerinput[sync.WORKERINPUT_KEY]["files"] == ["tests/test_other.py"]


def test_the_controller_reselects_once_for_many_workers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path)
    calls: list[Path] = []

    def record(_select: Any, path: Path) -> set[str]:
        calls.append(path)
        return set()

    monkeypatch.setattr(inputs, "reselect", record)
    hook = _broadcast(_Config(Select([READER], []), root, None))
    for _ in range(3):
        hook.pytest_configure_node(_Node())
    hook.pytest_sessionstart(object())
    assert calls == [root]


def test_a_single_process_run_reselects_at_session_start(tmp_path: Path) -> None:
    root = _project(tmp_path)
    write(root, CORPUS, '{"a": 1}\n')
    select = Select([READER], [])
    _broadcast(_Config(select, root, None)).pytest_sessionstart(object())
    assert select.deselected_files == []


def test_a_worker_adopts_the_controller_and_does_not_reselect(tmp_path: Path) -> None:
    root = _project(tmp_path)
    write(root, CORPUS, '{"a": 1}\n')
    select = Select([], [])
    payload = {sync.WORKERINPUT_KEY: {"files": [READER], "tests": []}}
    _broadcast(_Config(select, root, payload)).pytest_sessionstart(object())
    assert select.deselected_files == frozenset({READER})


def test_without_a_root_path_the_hook_changes_nothing() -> None:
    select = Select([READER], [])
    _broadcast(_Config(select, None, None)).pytest_sessionstart(object())
    assert select.deselected_files == [READER]


# --- replay with real testmon -----------------------------------------------

_READER_TEST = """
import json
from pathlib import Path

CORPUS = Path(__file__).parent / "evals" / "corpus.json"


def test_corpus_says_ok():
    assert json.loads(CORPUS.read_text(encoding="utf-8"))["verdict"] == "ok"
"""


def _replay(project: Path, *flags: str) -> tuple[int, str]:
    """Record a passing run, then edit the corpus so the reader fails; return the rerun."""
    pytest.importorskip("testmon")
    make_repo(
        project,
        {
            "tests/test_reader.py": _READER_TEST,
            "tests/test_other.py": OTHER_TEST,
            "tests/evals/corpus.json": '{"verdict": "ok"}\n',
            ".gitignore": ".testmondata*\n__pycache__/\n.pytest_cache/\n",
        },
    )
    code, output = run_pytest(project, *flags)
    assert code == 0, output
    write(project, "tests/evals/corpus.json", '{"verdict": "broken"}\n')
    return run_pytest(project, *flags)


def test_control_without_the_plugin_testmon_skips_the_reader_of_an_edited_corpus(
    tmp_path: Path,
) -> None:
    """Pins the testmon 2.2.0 gap. If an upgrade makes this fail, testmon tracks data files."""
    code, output = _replay(tmp_path)
    assert code == 0, output
    assert "no tests ran" in output
    assert "failed" not in output


def test_the_plugin_runs_the_reader_of_an_edited_corpus(tmp_path: Path) -> None:
    code, output = _replay(tmp_path, PLUGIN_FLAG)
    assert code == 1, output
    assert "test_corpus_says_ok" in output
    assert "1 failed" in output


def test_the_plugin_runs_the_reader_under_xdist(tmp_path: Path) -> None:
    pytest.importorskip("xdist")
    code, output = _replay(tmp_path, PLUGIN_FLAG, "-n", "2")
    assert code == 1, output
    assert "1 failed" in output
