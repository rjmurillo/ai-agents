"""Tests for composite action scanning in check_adr_exception_markers.py (issue #6506).

The gate reads `.github/actions/**/action.yml` and `action.yaml` beside the
workflow files, since a runner exception can sit in an action a workflow calls.

- pos: a live ADR in an action passes and the action counts as examined
- neg: a missing or retired ADR, or a near miss, in an action exits 1
- edge: nested action directories, other YAML under `.github/actions`, a
  missing actions directory, and a non-UTF-8 action file (exit 2)
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from tests.validation.test_check_adr_exception_markers import _adr, _run, _workflow


def _action(repo: Path, comment: str, name: str = "setup", file_name: str = "action.yml") -> Path:
    action_dir = repo / ".github" / "actions" / name
    action_dir.mkdir(parents=True, exist_ok=True)
    path = action_dir / file_name
    path.write_text(
        textwrap.dedent(
            f"""\
            name: {name}
            runs:
              using: composite
              steps:
                {comment}
                - run: echo hi
                  shell: bash
            """
        ),
        encoding="utf-8",
    )
    return path


def test_action_marker_naming_live_adr_passes_and_is_counted(tmp_path: Path) -> None:
    _adr(tmp_path, 55, "accepted")
    _workflow(tmp_path, "# plain")
    _action(tmp_path, "# ADR-055 Exception: composite action needs x64")
    result = _run(tmp_path)
    assert result.returncode == 0
    assert "1 marker(s) in 2 workflow and action file(s)" in result.stdout


@pytest.mark.parametrize("file_name", ["action.yml", "action.yaml"])
def test_action_marker_naming_missing_adr_fails(tmp_path: Path, file_name: str) -> None:
    _adr(tmp_path, 55, "accepted")
    _workflow(tmp_path, "# plain")
    _action(tmp_path, "# ADR-999 Exception: reason", file_name=file_name)
    result = _run(tmp_path)
    assert result.returncode == 1
    assert f".github/actions/setup/{file_name}:5: ADR-999 does not exist" in result.stdout


def test_action_marker_naming_retired_adr_fails(tmp_path: Path) -> None:
    _adr(tmp_path, 55, "accepted")
    _adr(tmp_path, 32, "superseded")
    _workflow(tmp_path, "# ADR-055 Exception: live")
    _action(tmp_path, "# ADR-032 Exception: stale")
    result = _run(tmp_path)
    assert result.returncode == 1
    assert ".github/actions/setup/action.yml:5: ADR-032 is superseded" in result.stdout


def test_action_near_miss_fails(tmp_path: Path) -> None:
    _adr(tmp_path, 55, "accepted")
    _workflow(tmp_path, "# plain")
    _action(tmp_path, "# ADR-055 Exeption: typo")
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "near-miss marker" in result.stdout
    assert ".github/actions/setup/action.yml:5" in result.stdout


def test_nested_action_file_is_scanned(tmp_path: Path) -> None:
    _adr(tmp_path, 55, "accepted")
    _workflow(tmp_path, "# plain")
    _action(tmp_path, "# ADR-999 Exception: deep", name="group/inner")
    result = _run(tmp_path)
    assert result.returncode == 1
    assert ".github/actions/group/inner/action.yml:5: ADR-999 does not exist" in result.stdout


def test_other_yaml_under_actions_is_not_scanned(tmp_path: Path) -> None:
    _adr(tmp_path, 55, "accepted")
    _workflow(tmp_path, "# plain")
    _action(tmp_path, "# plain")
    (tmp_path / ".github" / "actions" / "setup" / "config.yml").write_text(
        "# ADR-999 Exception: not an action definition\n", encoding="utf-8"
    )
    result = _run(tmp_path)
    assert result.returncode == 0
    assert "0 marker(s) in 2 workflow and action file(s)" in result.stdout


def test_missing_actions_dir_is_not_a_config_error(tmp_path: Path) -> None:
    _adr(tmp_path, 55, "accepted")
    _workflow(tmp_path, "# ADR-055 Exception: reason")
    assert not (tmp_path / ".github" / "actions").exists()
    result = _run(tmp_path)
    assert result.returncode == 0
    assert "1 marker(s) in 1 workflow and action file(s)" in result.stdout


def test_non_utf8_action_is_reported_not_crashed(tmp_path: Path) -> None:
    _adr(tmp_path, 55, "accepted")
    _workflow(tmp_path, "# plain")
    path = _action(tmp_path, "# plain")
    path.write_bytes(b"\xff\xfe# ADR-055 Exception\n")
    result = _run(tmp_path)
    assert result.returncode == 2
    assert "actions/setup/action.yml" in result.stderr
