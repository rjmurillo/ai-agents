"""The fetch command: exit codes and what it prints, with the API faked."""

from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from scripts.validation.fetch_promotion_evidence import EXIT_CONFIG, EXIT_EXTERNAL, EXIT_OK, main
from scripts.validation.promotion_applicability import APPLICABILITY_RELATIVE_PATH
from scripts.validation.promotion_fetch import GitHubApiError
from tests.validation.promotion_fetch_helpers import SHA, FakeReader, _good

REPO = "owner/repo"


def _table(root: Path, *entries: dict[str, Any]) -> None:
    path = root / APPLICABILITY_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema_version": "1", "entries": list(entries)}), encoding="utf-8")


def _row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "validator": "run_python_tests",
        "tier": "commit",
        "workflow": ".github/workflows/pytest.yml",
        "job": "Run Python Tests",
        "when": "always",
        "rationale": "test row",
    }
    row.update(overrides)
    return row


def _argv(tmp_path: Path, **overrides: str) -> list[str]:
    values = {
        "--repo": REPO,
        "--candidate-sha": SHA,
        "--default-branch": "main",
        "--evidence-dir": str(tmp_path / "ev"),
        "--repo-root": str(tmp_path / "root"),
    }
    values.update(overrides)
    return [token for pair in values.items() for token in pair]


def test_an_accepted_run_exits_zero_and_reports_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _table(tmp_path / "root", _row())
    assert main(_argv(tmp_path), _good()) == EXIT_OK
    out = capsys.readouterr().out
    assert "provenance: run_python_tests run 900 accepted accepted" in out
    assert "1 accepted, 0 rejected" in out
    assert (tmp_path / "ev" / "run_python_tests.900.json").is_file()


def test_a_rejected_run_still_exits_zero_and_is_reported(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _table(tmp_path / "root", _row())
    reader = _good()
    reader.runs[0]["head_branch"] = "feature"
    assert main(_argv(tmp_path), reader) == EXIT_OK
    out = capsys.readouterr().out
    assert "rejected run.ref_mismatch" in out
    assert "0 accepted, 1 rejected" in out


def test_a_missing_table_is_an_empty_fetch_not_an_error(tmp_path: Path) -> None:
    reader = FakeReader([])
    assert main(_argv(tmp_path), reader) == EXIT_OK
    assert reader.calls == []


def test_a_malformed_table_exits_two(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _table(tmp_path / "root", _row(workflow="pytest.yml"))
    assert main(_argv(tmp_path), FakeReader([])) == EXIT_CONFIG
    assert "workflow" in capsys.readouterr().err


@pytest.mark.parametrize(
    "overrides",
    [{"--candidate-sha": "abc"}, {"--repo": "owner"}, {"--default-branch": "a b"}],
)
def test_bad_arguments_exit_two(tmp_path: Path, overrides: dict[str, str]) -> None:
    _table(tmp_path / "root", _row())
    assert main(_argv(tmp_path, **overrides), _good()) == EXIT_CONFIG


def test_a_github_failure_exits_three(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _table(tmp_path / "root", _row())

    class Down(FakeReader):
        def get_json(self, path: str, params: Any = None) -> object:
            raise GitHubApiError("gh api exited 1: HTTP 502")

    assert main(_argv(tmp_path), Down([])) == EXIT_EXTERNAL
    assert "[BLOCKED]" in capsys.readouterr().err


def test_an_unwritable_evidence_directory_exits_three(tmp_path: Path) -> None:
    _table(tmp_path / "root", _row())
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    assert (
        main(_argv(tmp_path, **{"--evidence-dir": str(blocker / "sub")}), _good()) == EXIT_EXTERNAL
    )


def test_a_missing_required_argument_exits_two() -> None:
    with pytest.raises(SystemExit) as stop:
        main(["--repo", REPO])
    assert stop.value.code == EXIT_CONFIG


def test_the_entry_point_guard_returns_the_exit_code() -> None:
    script = Path(main.__code__.co_filename)
    with (
        patch.object(sys, "argv", [str(script), "--repo", REPO]),
        pytest.raises(SystemExit) as stop,
    ):
        runpy.run_path(str(script), run_name="__main__")
    assert stop.value.code == EXIT_CONFIG
