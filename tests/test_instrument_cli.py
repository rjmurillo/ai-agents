"""AC-DUP-2: Shared dispatch preserves the three existing instrument contracts."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Literal
from unittest.mock import Mock

import pytest

from scripts.instrument_cli import (
    InstrumentDispatcher,
    InstrumentHelp,
    checked_script_exists,
    inline_script_exists,
    python_script_exists,
    repo_paths_exist,
    target_exists,
)
from scripts.instrument_cli import (
    test_target_exists as pytest_target_exists,
)


@pytest.mark.parametrize("style", ["plain", "json", "examined"])
def test_dispatch_reads_live_tables_and_forwards_exit_codes(
    style: Literal["plain", "json", "examined"],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rows = [{"id": "original", "argv": ["python3", "missing.py"]}]
    cli = InstrumentDispatcher(
        InstrumentHelp("test-skill", "Description\nMore", "examples:\n  sample", style),
        lambda: rows,
        python_script_exists,
    )
    assert cli.main(["--repo", str(tmp_path), "list"]) == 1
    assert json.loads(capsys.readouterr().out)["missing"] == ["original"]
    rows = [{"id": "changed", "argv": ["python3", "-c", "raise SystemExit(7)"]}]

    assert cli.main(["--repo", str(tmp_path), "run", "changed"]) == 7


@pytest.mark.parametrize("style", ["plain", "json", "examined"])
def test_unknown_ids_keep_diagnostic_contract(
    style: Literal["plain", "json", "examined"],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = InstrumentDispatcher(
        InstrumentHelp("s", "Description", "help", style),
        lambda: [{"id": "known", "argv": ["not-a-binary"]}],
        python_script_exists,
    )

    assert cli.main(["--repo", str(tmp_path), "run", "unknown"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    if style == "plain":
        assert captured.err == "error: unknown instrument 'unknown' (known: known)\n"
    else:
        error = json.loads(captured.err)
        assert error["error"] == "unknown instrument id: unknown"
        assert error["known"] == ["known"]
        assert ("examined" in error) == (style == "examined")


@pytest.mark.parametrize("style", ["plain", "json", "examined"])
def test_spawn_failure_keeps_exit_three(
    style: Literal["plain", "json", "examined"],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = InstrumentDispatcher(
        InstrumentHelp("s", "Description", "help", style),
        lambda: [{"id": "bad", "argv": ["not-a-binary-readiness-test"]}],
        python_script_exists,
    )

    assert cli.main(["--repo", str(tmp_path), "run", "bad"]) == 3
    captured = capsys.readouterr()
    if style == "plain":
        assert captured.err.startswith("error: cannot start not-a-binary-readiness-test:")
    else:
        error = json.loads(captured.err)
        prefix = "cannot start " if style == "examined" else "failed to start: "
        assert error["error"].startswith(prefix)
        assert ("examined" in error) == (style == "examined")


@pytest.mark.parametrize("style", ["plain", "json", "examined"])
@pytest.mark.parametrize("separator_count", [1, 2])
def test_argument_separator_policy_is_preserved(
    style: Literal["plain", "json", "examined"],
    separator_count: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = Mock(return_value=subprocess.CompletedProcess(["echo"], 0))
    cli = InstrumentDispatcher(
        InstrumentHelp("s", "Description", "help", style),
        lambda: [{"id": "echo", "argv": ["echo"]}],
        python_script_exists,
    )
    monkeypatch.setattr(subprocess, "run", run)

    argv = ["--repo", str(tmp_path), "run", "echo"] + ["--"] * separator_count
    assert cli.main(argv + ["a", "--", "b"]) == 0
    expected = ["echo", "a", "b"] if style == "examined" else ["echo", "a", "--", "b"]
    run.assert_called_once_with(expected, cwd=tmp_path, check=False)


@pytest.mark.parametrize("style", ["plain", "json", "examined"])
@pytest.mark.parametrize("args,code", [(["--help"], 0), ([], 2), (["--invalid"], 2)])
def test_parser_exit_handling_is_preserved(
    style: Literal["plain", "json", "examined"], args: list[str], code: int
) -> None:
    cli = InstrumentDispatcher(
        InstrumentHelp("s", "Description", "examples:\n  sample", style),
        lambda: [],
        python_script_exists,
    )
    if style == "examined":
        assert cli.main(args) == code
    else:
        with pytest.raises(SystemExit) as error:
            cli.main(args)
        assert error.value.code == code


def test_plain_style_rejects_nonexistent_repo(tmp_path: Path) -> None:
    cli = InstrumentDispatcher(
        InstrumentHelp("s", "Description", "help", "plain"), lambda: [], repo_paths_exist
    )
    assert cli.main(["--repo", str(tmp_path / "missing"), "list"]) == 2


@pytest.mark.parametrize(
    "exists,argv,check_path,expected",
    [
        (repo_paths_exist, ["python3", "folder/file.py"], None, False),
        (repo_paths_exist, ["echo", "--some/path"], None, True),
        (python_script_exists, ["uv", "run", "python", "missing.py"], None, False),
        (python_script_exists, ["echo"], None, True),
        (checked_script_exists, ["echo"], "missing.py", False),
        (checked_script_exists, ["echo"], None, True),
        (inline_script_exists, ["python3", "-c", "pass", "missing.py"], None, False),
        (inline_script_exists, ["echo"], "missing.py", False),
        (inline_script_exists, ["echo"], None, True),
        (target_exists, ["python3", "missing.py"], None, False),
        (target_exists, ["uv", "run", "python", "missing.py"], None, False),
        (target_exists, ["uv", "run", "pytest", "missing.py"], None, True),
        (pytest_target_exists, ["uv", "run", "pytest", "missing.py"], None, False),
        (pytest_target_exists, ["echo"], None, True),
    ],
)
def test_path_policies_remain_distinct(exists, argv, check_path, expected, tmp_path: Path) -> None:
    row = {"id": "r", "argv": argv}
    if check_path is not None:
        row["check_path"] = check_path
    assert exists(tmp_path, row) is expected
