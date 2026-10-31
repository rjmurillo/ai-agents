"""``--evidence`` must stay inside the working directory, relative or absolute (#6506)."""

from __future__ import annotations

import json
from pathlib import Path

import api_examples as ax
import pytest
from api_fixtures import WORKED_EXAMPLE
from test_evidence_path import _link
from test_run import run_args


def test_relative_evidence_path_through_a_symlinked_dir_cannot_leave_the_cwd(
    order_api: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    work = tmp_path / "work"
    work.mkdir()
    _link(work / "out", outside)
    monkeypatch.chdir(work)
    args = run_args([WORKED_EXAMPLE], order_api)
    args.evidence = str(Path("out") / "evidence.json")

    with pytest.raises(ax.InputError, match="outside the working directory"):
        ax.cmd_run(args)

    assert list(outside.iterdir()) == []


def test_relative_evidence_path_with_dotdot_cannot_leave_the_cwd(
    order_api: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    args = run_args([WORKED_EXAMPLE], order_api)
    args.evidence = str(Path("..") / "evidence.json")

    with pytest.raises(ax.InputError, match="outside the working directory"):
        ax.cmd_run(args)

    assert not (tmp_path / "evidence.json").exists()


def test_relative_evidence_path_inside_the_cwd_is_written(
    order_api: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    args = run_args([WORKED_EXAMPLE], order_api)
    args.evidence = "evidence.json"

    _, code = ax.cmd_run(args)

    assert code == ax.EXIT_OK
    assert json.loads((tmp_path / "evidence.json").read_text(encoding="utf-8"))["verdict"] == "PASS"


def test_absolute_evidence_path_outside_the_cwd_is_refused(
    order_api: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    evidence = tmp_path / "evidence.json"

    with pytest.raises(ax.InputError, match="outside the working directory"):
        ax.cmd_run(run_args([WORKED_EXAMPLE], order_api, evidence))

    assert not evidence.exists()


def test_absolute_evidence_path_through_a_symlinked_dir_cannot_leave_the_cwd(
    order_api: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    work = tmp_path / "work"
    work.mkdir()
    _link(work / "out", outside)
    monkeypatch.chdir(work)
    evidence = work / "out" / "evidence.json"

    with pytest.raises(ax.InputError, match="outside the working directory"):
        ax.cmd_run(run_args([WORKED_EXAMPLE], order_api, evidence))

    assert list(outside.iterdir()) == []


def test_absolute_evidence_path_inside_the_cwd_is_written(order_api: str, tmp_path: Path) -> None:
    evidence = tmp_path / "evidence.json"

    _, code = ax.cmd_run(run_args([WORKED_EXAMPLE], order_api, evidence))

    assert code == ax.EXIT_OK
    assert json.loads(evidence.read_text(encoding="utf-8"))["verdict"] == "PASS"
