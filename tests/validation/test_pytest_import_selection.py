"""Import-graph test selection wired into the pre-push pytest runner."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.test_selection.select_tests import Selection
from scripts.validation import git_hook_policy


def _has_parallel_flag(command: list[str]) -> bool:
    return "-n" in command


def test_subset_splits_serial_and_parallel_partitions(tmp_path: Path) -> None:
    commands = git_hook_policy._pytest_commands_for_subset(
        tmp_path,
        [
            "tests/test_leaf.py",
            "tests/mutation/test_thing.py",
            "tests/test_safe_push_pr_branch.py",
            "tests/test_pr_autofix_late_live_state_gate.py",
        ],
    )
    assert len(commands) == 4
    bulk, mutation, safe_push, pr_autofix = commands
    assert _has_parallel_flag(bulk)
    assert _has_parallel_flag(mutation)
    assert not _has_parallel_flag(safe_push)
    assert not _has_parallel_flag(pr_autofix)
    assert str(tmp_path / "tests/test_leaf.py") in bulk
    assert "not integration and not safe_push_transport" in safe_push


def test_subset_emits_only_needed_partitions(tmp_path: Path) -> None:
    commands = git_hook_policy._pytest_commands_for_subset(tmp_path, ["tests/test_leaf.py"])
    assert len(commands) == 1
    assert str(tmp_path / "tests/test_leaf.py") in commands[0]


def _collection(tmp_path: Path) -> list[list[str]]:
    return [git_hook_policy._pytest_collection_command(tmp_path)]


def test_resolve_collects_when_diff_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, raising=False)
    monkeypatch.setattr(git_hook_policy.select_tests, "changed_from_git", lambda *_: None)
    commands = git_hook_policy._resolve_pytest_commands(tmp_path, None)
    assert commands == _collection(tmp_path)


def test_resolve_collects_on_full_verdict(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, raising=False)
    monkeypatch.setattr(
        git_hook_policy.select_tests,
        "select",
        lambda *_a, **_k: Selection(full=True, reason="non-Python change"),
    )
    commands = git_hook_policy._resolve_pytest_commands(tmp_path, ["README.md"])
    assert commands == _collection(tmp_path)


def test_collection_command_runs_no_test_bodies(tmp_path: Path) -> None:
    command = git_hook_policy._pytest_collection_command(tmp_path)
    assert "--collect-only" in command
    assert "not integration" in command
    assert str(tmp_path / "tests") in command
    # A parallel flag would start workers for a run that never executes a test.
    assert not _has_parallel_flag(command)


def test_opt_in_env_restores_local_full_suite_execution(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The escape hatch has to actually reach the executing partitions.

    Without this, the default could quietly become the only behavior and the
    documented override in `lefthook.yml` and ADR-104 would be a dead string.
    """
    monkeypatch.setenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, "1")
    monkeypatch.setattr(
        git_hook_policy.select_tests,
        "select",
        lambda *_a, **_k: Selection(full=True, reason="non-Python change"),
    )
    commands = git_hook_policy._resolve_pytest_commands(tmp_path, ["README.md"])
    assert commands == git_hook_policy._pytest_commands(tmp_path)


@pytest.mark.parametrize("value", ["0", "true", "TRUE", "yes", " 1 x"])
def test_opt_in_env_rejects_values_other_than_one(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, value: str
) -> None:
    """Doing less than the caller asked for, silently, is the failure here.

    A developer who exports `...=true` wants local execution. Quietly
    collecting instead gives them a fast green push and no signal that the
    flag did nothing.
    """
    monkeypatch.setenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, value)
    monkeypatch.setattr(
        git_hook_policy.select_tests,
        "select",
        lambda *_a, **_k: Selection(full=True, reason="non-Python change"),
    )
    with pytest.raises(ValueError, match="must be '1' or unset"):
        git_hook_policy._resolve_pytest_commands(tmp_path, ["README.md"])


@pytest.mark.parametrize("value", ["", "   ", "1", " 1 "])
def test_opt_in_env_accepts_unset_blank_and_one(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, value: str
) -> None:
    """Blank is unset by another name; a padded '1' is still a '1'."""
    monkeypatch.setenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, value)
    monkeypatch.setattr(
        git_hook_policy.select_tests,
        "select",
        lambda *_a, **_k: Selection(full=True, reason="non-Python change"),
    )
    commands = git_hook_policy._resolve_pytest_commands(tmp_path, ["README.md"])
    expected = (
        git_hook_policy._pytest_commands(tmp_path)
        if value.strip() == "1"
        else _collection(tmp_path)
    )
    assert commands == expected


def test_a_rejected_opt_in_value_is_reported_on_the_narrowed_path_too(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The branch the validation used to skip.

    The check lived inside `_full_suite_stand_in`, which only the fallback
    paths reach. With a narrowed import-graph selection,
    `AI_AGENTS_PYTEST_FULL_SUITE_LOCALLY=true` was silently ignored: the
    developer asked for the full suite, did not get it, and was not told. A
    contract enforced on one branch of two is not enforced.

    Every other opt-in test drives the fallback path, so all of them passed
    while this hole was open. Caught in review on PR #5319, and it is the same
    defect fixed for `AI_AGENTS_PYTEST_WORKERS` a few commits earlier by
    hoisting its validation for exactly this reason.
    """
    monkeypatch.setenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, "true")
    monkeypatch.setattr(
        git_hook_policy.select_tests,
        "select",
        lambda *_a, **_k: Selection(full=False, tests=("tests/test_x.py",), reason="narrowed"),
    )

    with pytest.raises(ValueError, match=git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV):
        git_hook_policy._resolve_pytest_commands(tmp_path, ["scripts/x.py"])


def test_a_valid_opt_in_beats_a_narrowed_selection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The branch the hoisted validation did not fix.

    Hoisting `_validated_full_suite_opt_in` made an invalid value report on
    both paths. It did not make a valid one act on both: the return was
    discarded, so with `=1` and a Python diff the graph could narrow, the
    developer got whatever subset the selector chose and was told nothing. A
    flag named FULL_SUITE_LOCALLY that quietly runs four files is the same
    doing-less-than-asked defect its own reject-anything-but-1 rule exists to
    prevent, one branch further along, and ADR-104's Implementation Notes label
    this command "whole-suite execution".

    The sibling test above drives the same narrowed selection with an invalid
    value and asserts the raise. This one drives it with the valid value, which
    is the case that stayed broken after the raise was fixed. Raised in review
    on PR #5319.
    """
    monkeypatch.setenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, "1")
    monkeypatch.setattr(
        git_hook_policy.select_tests,
        "select",
        lambda *_a, **_k: Selection(full=False, tests=("tests/test_x.py",), reason="narrowed"),
    )

    commands = git_hook_policy._resolve_pytest_commands(tmp_path, ["scripts/x.py"])

    assert commands == git_hook_policy._pytest_commands(tmp_path), (
        "a narrowed selection won over an explicit full-suite opt-in. The "
        "developer asked for the whole suite and got a subset without being "
        "told, which is what the flag exists to make impossible."
    )
    assert git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV in capsys.readouterr().err, (
        "the override took effect silently. A path chosen by an environment "
        "variable has to name the variable, or the next reader cannot tell why "
        "this push ran the whole suite."
    )


def test_a_rejected_opt_in_value_exits_config_error_not_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`run_pytest` must turn the raise into a non-zero exit, not a pass."""
    monkeypatch.setenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, "true")
    monkeypatch.setattr(git_hook_policy.select_tests, "changed_from_git", lambda *_: None)
    assert git_hook_policy.run_pytest(tmp_path) == 2


def test_run_pytest_refuses_an_empty_command_list(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A push must never pass by running zero tests.

    The invariant that keeps `commands` non-empty lives in `select_tests`, a
    different module. `run_pytest` decides whether a push is allowed, so it
    carries its own guard rather than trusting that one.
    """
    monkeypatch.setattr(git_hook_policy, "_resolve_pytest_commands", lambda *_a, **_k: [])
    assert git_hook_policy.run_pytest(tmp_path) == 2
    assert "zero tests" in capsys.readouterr().err


def test_collection_command_silences_the_node_listing(tmp_path: Path) -> None:
    """`pyproject.toml` sets `addopts = "-v ..."`, so one `-q` nets to zero.

    Measured: 31765 lines of node listing into the hook output with one `-q`,
    878 with three. Hook output is a token cost this stand-in exists to cut.
    """
    command = git_hook_policy._pytest_collection_command(tmp_path)
    assert command.count("-q") == 3


def test_collection_gets_the_collection_budget_not_the_suite_budget(tmp_path: Path) -> None:
    """A collection hang must not be able to block a push for 29 minutes."""
    collection = _collection(tmp_path)
    assert (
        git_hook_policy._pytest_budget_seconds(collection)
        == git_hook_policy.TEST_COLLECTION_TIMEOUT_SECONDS
    )
    assert (
        git_hook_policy.TEST_COLLECTION_TIMEOUT_SECONDS < git_hook_policy.TEST_SUITE_TIMEOUT_SECONDS
    )


def test_executing_commands_keep_the_suite_budget(tmp_path: Path) -> None:
    executing = git_hook_policy._pytest_commands(tmp_path)
    assert (
        git_hook_policy._pytest_budget_seconds(executing)
        == git_hook_policy.TEST_SUITE_TIMEOUT_SECONDS
    )


def test_subset_of_one_file_is_not_mistaken_for_a_collection_run(tmp_path: Path) -> None:
    """The budget switch keys on `--collect-only`, not on the command count."""
    subset = git_hook_policy._pytest_commands_for_subset(tmp_path, ["tests/test_leaf.py"])
    assert len(subset) == 1
    assert (
        git_hook_policy._pytest_budget_seconds(subset) == git_hook_policy.TEST_SUITE_TIMEOUT_SECONDS
    )


def test_resolve_uses_subset_on_narrowed_verdict(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        git_hook_policy.select_tests,
        "select",
        lambda *_a, **_k: Selection(
            full=False, reason="import-graph subset", tests=("tests/test_leaf.py",)
        ),
    )
    commands = git_hook_policy._resolve_pytest_commands(tmp_path, ["pkg/leaf.py"])
    assert commands == git_hook_policy._pytest_commands_for_subset(
        tmp_path, ("tests/test_leaf.py",)
    )
    assert "import graph" in capsys.readouterr().err


def test_resolve_explains_why_it_collected_instead_of_executing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The narrowed path announced itself and the fallback stayed silent.

    That was fine while the fallback ran everything, because silence meant the
    strongest behavior. It now means the weaker one, so a reader who sees a
    fast pre-push has to be told the suite was collected rather than run, and
    where the execution went.
    """
    monkeypatch.delenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, raising=False)
    monkeypatch.setattr(git_hook_policy.select_tests, "changed_from_git", lambda *_: None)
    git_hook_policy._resolve_pytest_commands(tmp_path, None)
    err = capsys.readouterr().err
    assert "Collecting every test" in err
    assert "pytest.yml" in err
    assert git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV in err


def test_the_collection_notice_repeats_the_selector_reason(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A selector regression and a legitimate non-Python change must read differently.

    Without the reason in the notice, a selector that silently started
    returning `full=True` for every diff would look identical to the ordinary
    Markdown case it is supposed to look different from.
    """
    monkeypatch.delenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, raising=False)
    monkeypatch.setattr(
        git_hook_policy.select_tests,
        "select",
        lambda *_a, **_k: Selection(full=True, reason="sentinel-reason-xyz"),
    )
    git_hook_policy._resolve_pytest_commands(tmp_path, ["README.md"])
    assert "sentinel-reason-xyz" in capsys.readouterr().err


def test_a_pytest_internal_error_is_not_reported_as_a_timeout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exit 3 is overloaded, and the code alone cannot tell the cases apart.

    pytest returns 3 for an internal error. `_run_command` synthesizes 3 when
    it kills a child on timeout, and again on an OSError launching the process.
    `run_pytest` used to branch on the bare code, so a genuine pytest crash was
    announced as "pytest suite timed out" and the developer was sent to the
    budget instead of the traceback the child had already printed.

    Raised in review on PR #5319. The sibling test above covers the real
    timeout; this one covers the case that was being misread as one.
    """
    monkeypatch.delenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, raising=False)
    monkeypatch.setattr(git_hook_policy.select_tests, "changed_from_git", lambda *_: None)
    monkeypatch.setattr(
        git_hook_policy,
        "_run_command",
        lambda *_a, **_k: subprocess.CompletedProcess(
            ["pytest"], 3, "", "INTERNALERROR> Traceback (most recent call last):\n"
        ),
    )
    monkeypatch.setattr(git_hook_policy, "_print_process_output", lambda _r: None)

    assert git_hook_policy.run_pytest(tmp_path) == 3, (
        "the exit code must still reach the caller; only the diagnosis changes."
    )

    err = capsys.readouterr().err
    assert "timed out" not in err, (
        "a pytest internal error was announced as a timeout. The child's own "
        f"stderr carries no timeout marker, so nothing here should: {err!r}"
    )
    assert "budget" not in err, (
        "the budget was named for a failure that has nothing to do with it, "
        f"which is where the reader gets sent next: {err!r}"
    )


def test_a_collection_timeout_names_the_collection_ceiling(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A collection hang must name the collection ceiling, not the suite one.

    The timeout message is the only thing a developer whose push just died has
    to go on. Naming the wrong ceiling sends them hunting for a 29-minute run
    that never happened.
    """
    monkeypatch.delenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, raising=False)
    monkeypatch.setattr(git_hook_policy.select_tests, "changed_from_git", lambda *_: None)
    # A bare exit 3 is no longer a timeout. `_run_command` synthesizes 3 when it
    # kills a child AND pytest returns 3 for an internal error, so `run_pytest`
    # reads the marker `_run_command` appends rather than the code. A fake that
    # returns 3 with empty stderr is a crash, not a hang, so it has to carry the
    # real message here (PR #5319).
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
