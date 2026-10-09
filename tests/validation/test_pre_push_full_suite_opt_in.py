"""The pre-push full-suite opt-in is strict, and collection says how to opt in.

Issue #6239 AC5: ``AI_AGENTS_PYTEST_FULL_SUITE_LOCALLY=1`` still executes the
full suite; any other value is a configuration error, never a quiet downgrade.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.validation import git_hook_policy
from tests.validation.pre_push_collection_helpers import (
    COLLECTION_ERROR_EXIT,
    collection,
    default_environment,  # noqa: F401  (fixture, applied by usefixtures below)
    record_runs,
)

pytestmark = pytest.mark.usefixtures("default_environment")


def test_the_opt_in_runs_the_full_suite_without_selection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """AC5: ``=1`` executes every partition, never the collection stand-in."""
    monkeypatch.setenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, "1")
    seen = record_runs(monkeypatch)
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
        git_hook_policy._pytest_commands(tmp_path) if value.strip() == "1" else collection(tmp_path)
    )
    assert git_hook_policy._resolve_pytest_commands(tmp_path) == expected


def test_a_rejected_opt_in_value_exits_config_error_not_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``run_pytest`` turns the raise into exit 2 and spawns nothing."""
    monkeypatch.setenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, "true")
    seen = record_runs(monkeypatch)
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


def test_the_opt_in_is_the_second_line_of_the_collection_notice(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A reader who stops after two lines must not take the notice for a pass."""
    git_hook_policy._resolve_pytest_commands(tmp_path)
    lines = capsys.readouterr().err.splitlines()
    assert lines[0] == "pytest: collecting every test instead of executing them."
    assert lines[1].strip() == (
        f"Set {git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV}=1 to execute the suite here. "
        "See ADR-104."
    )
