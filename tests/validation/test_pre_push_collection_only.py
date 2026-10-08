"""Pre-push runs pytest collection only, with no test selection.

Issue #6239 AC5: the default pre-push pytest step runs the existing collection
command over ``tests/``, in one process, and a collection error fails the push.
The ``AI_AGENTS_PYTEST_FULL_SUITE_LOCALLY=1`` opt-in still executes the full
suite. Issue #6239 AC1: nothing in the hook module imports the selector.
"""

from __future__ import annotations

import ast
import inspect
import subprocess
from pathlib import Path

import pytest

from scripts.validation import git_hook_policy

COLLECTION_ERROR_EXIT = 2


def _collection(tmp_path: Path) -> list[list[str]]:
    return [git_hook_policy._pytest_collection_command(tmp_path)]


@pytest.fixture(autouse=True)
def _default_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, raising=False)
    monkeypatch.delenv(git_hook_policy.PYTEST_WORKERS_ENV, raising=False)
    monkeypatch.delenv(git_hook_policy.PYTEST_WORKER_CAP_ENV, raising=False)


def _record_runs(
    monkeypatch: pytest.MonkeyPatch, returncode: int = 0, stderr: str = ""
) -> list[list[str]]:
    """Replace the subprocess boundary and return the argv list it receives."""
    seen: list[list[str]] = []

    def fake(command: list[str], *_a: object, **_k: object) -> subprocess.CompletedProcess[str]:
        seen.append(list(command))
        return subprocess.CompletedProcess(command, returncode, "", stderr)

    monkeypatch.setattr(git_hook_policy, "_run_command", fake)
    monkeypatch.setattr(git_hook_policy, "_print_process_output", lambda _r: None)
    return seen


def test_the_hook_module_does_not_import_the_selector() -> None:
    """AC1: neither an import statement nor a module attribute names the selector."""
    source = Path(inspect.getfile(git_hook_policy)).read_text(encoding="utf-8")
    imported = [
        name
        for node in ast.walk(ast.parse(source))
        for name in (
            [alias.name for alias in node.names]
            if isinstance(node, ast.Import)
            else [node.module or "", *(alias.name for alias in node.names)]
            if isinstance(node, ast.ImportFrom)
            else []
        )
    ]
    assert not [name for name in imported if "test_selection" in name or "select_tests" in name]
    assert not hasattr(git_hook_policy, "select_tests")


def test_run_pytest_takes_no_changed_files_parameter() -> None:
    """AC5: the hook never receives a diff, so nothing can narrow the run."""
    assert list(inspect.signature(git_hook_policy.run_pytest).parameters) == ["repo_root"]
    assert list(inspect.signature(git_hook_policy._resolve_pytest_commands).parameters) == [
        "repo_root"
    ]


def test_default_pre_push_resolves_to_the_collection_command_only(tmp_path: Path) -> None:
    """AC5: one command, collect-only, over ``tests/``, with no worker pool."""
    commands = git_hook_policy._resolve_pytest_commands(tmp_path)
    assert commands == _collection(tmp_path)
    (command,) = commands
    assert "--collect-only" in command
    assert command[-1] == str(tmp_path / "tests")
    assert "-n" not in command


def test_default_pre_push_runs_one_process_and_asks_git_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """AC5: ``run_pytest`` spawns the collection command once and consults no diff."""
    seen = _record_runs(monkeypatch)
    monkeypatch.setattr(
        git_hook_policy,
        "_run_git",
        lambda *_a, **_k: pytest.fail("pre-push pytest must not ask git for a diff"),
    )
    assert git_hook_policy.run_pytest(tmp_path) == 0
    assert seen == _collection(tmp_path)


@pytest.mark.parametrize("exit_code", [1, 2, 4])
def test_a_collection_error_fails_the_push(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, exit_code: int
) -> None:
    """AC5: pytest exits nonzero on a collection error and the hook passes it on."""
    _record_runs(monkeypatch, returncode=exit_code)
    assert git_hook_policy.run_pytest(tmp_path) == exit_code


def test_the_opt_in_runs_the_full_suite_without_selection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """AC5: ``=1`` executes every partition, never the collection stand-in."""
    monkeypatch.setenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, "1")
    seen = _record_runs(monkeypatch)
    assert git_hook_policy.run_pytest(tmp_path) == 0
    assert seen == git_hook_policy._pytest_commands(tmp_path)
    assert not any("--collect-only" in command for command in seen)


@pytest.mark.parametrize("value", ["0", "true", "TRUE", "yes", " 1 x"])
def test_the_opt_in_rejects_values_other_than_one(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, value: str
) -> None:
    """A flag whose purpose is "run more" must not quietly run less."""
    monkeypatch.setenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, value)
    with pytest.raises(ValueError, match="must be '1' or unset"):
        git_hook_policy._resolve_pytest_commands(tmp_path)


@pytest.mark.parametrize("value", ["", "   ", "1", " 1 "])
def test_the_opt_in_accepts_unset_blank_and_one(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, value: str
) -> None:
    """Blank is unset by another name; a padded ``1`` is still a ``1``."""
    monkeypatch.setenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, value)
    expected = (
        git_hook_policy._pytest_commands(tmp_path)
        if value.strip() == "1"
        else _collection(tmp_path)
    )
    assert git_hook_policy._resolve_pytest_commands(tmp_path) == expected


def test_a_rejected_opt_in_value_exits_config_error_not_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``run_pytest`` turns the raise into exit 2 and spawns nothing."""
    monkeypatch.setenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, "true")
    seen = _record_runs(monkeypatch)
    assert git_hook_policy.run_pytest(tmp_path) == COLLECTION_ERROR_EXIT
    assert seen == []


def test_an_invalid_worker_override_is_reported_on_the_collection_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The collection command takes no ``-n``, so validation must not ride on it."""
    monkeypatch.setenv(git_hook_policy.PYTEST_WORKERS_ENV, "half")
    with pytest.raises(ValueError, match=git_hook_policy.PYTEST_WORKERS_ENV):
        git_hook_policy._resolve_pytest_commands(tmp_path)


def test_the_collection_notice_names_the_opt_in_and_what_collection_misses(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    git_hook_policy._resolve_pytest_commands(tmp_path)
    err = capsys.readouterr().err
    assert git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV in err
    assert "does NOT catch a missing fixture" in err
    assert "import-graph" not in err
    assert "selection" not in err


def test_collection_command_runs_no_test_bodies(tmp_path: Path) -> None:
    command = git_hook_policy._pytest_collection_command(tmp_path)
    assert "--collect-only" in command
    assert "not integration" in command
    assert str(tmp_path / "tests") in command
    assert "-n" not in command


def test_collection_command_silences_the_node_listing(tmp_path: Path) -> None:
    """``pyproject.toml`` sets ``addopts = "-v ..."``, so one ``-q`` nets to zero.

    Measured: 31765 lines of node listing into the hook output with one ``-q``,
    878 with three. Hook output is a token cost this stand-in exists to cut.
    """
    assert git_hook_policy._pytest_collection_command(tmp_path).count("-q") == 3


def test_collection_gets_the_collection_budget_not_the_suite_budget(tmp_path: Path) -> None:
    """A collection hang must not be able to block a push for 29 minutes."""
    assert (
        git_hook_policy._pytest_budget_seconds(_collection(tmp_path))
        == git_hook_policy.TEST_COLLECTION_TIMEOUT_SECONDS
    )
    assert (
        git_hook_policy.TEST_COLLECTION_TIMEOUT_SECONDS < git_hook_policy.TEST_SUITE_TIMEOUT_SECONDS
    )


def test_executing_commands_keep_the_suite_budget(tmp_path: Path) -> None:
    assert (
        git_hook_policy._pytest_budget_seconds(git_hook_policy._pytest_commands(tmp_path))
        == git_hook_policy.TEST_SUITE_TIMEOUT_SECONDS
    )


def test_a_pytest_internal_error_is_not_reported_as_a_timeout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exit 3 is overloaded: pytest INTERNALERROR and ``_run_command``'s timeout kill.

    ``run_pytest`` reads the timeout marker ``_run_command`` appends, not the
    bare code, so a genuine pytest crash is not announced as a budget problem.
    """
    _record_runs(monkeypatch, returncode=3, stderr="INTERNALERROR> Traceback\n")
    assert git_hook_policy.run_pytest(tmp_path) == 3
    err = capsys.readouterr().err
    assert "timed out" not in err
    assert "budget" not in err


def test_a_collection_timeout_names_the_collection_ceiling(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The timeout message is all a developer whose push just died has to go on."""
    monkeypatch.setattr(
        git_hook_policy,
        "_run_command",
        lambda *_a, **kw: subprocess.CompletedProcess(
            ["pytest"],
            3,
            "",
            git_hook_policy._timeout_message(["pytest"], kw["timeout_seconds"]),
        ),
    )
    monkeypatch.setattr(git_hook_policy, "_print_process_output", lambda _r: None)
    assert git_hook_policy.run_pytest(tmp_path) == 3
    err = capsys.readouterr().err
    assert str(git_hook_policy.TEST_COLLECTION_TIMEOUT_SECONDS) in err
    assert str(git_hook_policy.TEST_SUITE_TIMEOUT_SECONDS) not in err
