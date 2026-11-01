"""``--evidence`` must stay inside the working directory, relative or absolute (#6506)."""

from __future__ import annotations

import json
from pathlib import Path

import api_examples as ax
import pytest
from api_fixtures import WORKED_EXAMPLE
from test_evidence_path import _link
from test_run import run_args

REFUSAL = "outside the working directory"


@pytest.fixture
def work(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Run from a subdirectory of tmp_path so ``..`` and its siblings lie outside the cwd."""
    path = tmp_path / "work"
    path.mkdir()
    monkeypatch.chdir(path)
    return path


@pytest.fixture
def outside(tmp_path: Path, work: Path) -> Path:
    """A directory outside ``work`` that the ``work/out`` symlink points at."""
    path = tmp_path / "outside"
    path.mkdir()
    _link(work / "out", path)
    return path


def _run(base_url: str, evidence: Path) -> int:
    code: int
    _, code = ax.cmd_run(run_args([WORKED_EXAMPLE], base_url, evidence))
    return code


def _assert_refused(base_url: str, evidence: Path) -> None:
    with pytest.raises(ax.InputError, match=REFUSAL):
        _run(base_url, evidence)


def _assert_written(base_url: str, evidence: Path) -> None:
    assert _run(base_url, evidence) == ax.EXIT_OK
    assert json.loads(evidence.read_text(encoding="utf-8"))["verdict"] == "PASS"


def test_relative_evidence_path_through_a_symlinked_dir_cannot_leave_the_cwd(
    order_api: str, outside: Path
) -> None:
    _assert_refused(order_api, Path("out") / "evidence.json")
    assert list(outside.iterdir()) == []


def test_relative_evidence_path_with_dotdot_cannot_leave_the_cwd(
    order_api: str, tmp_path: Path, work: Path
) -> None:
    _assert_refused(order_api, Path("..") / "evidence.json")
    assert not (tmp_path / "evidence.json").exists()


def test_relative_evidence_path_inside_the_cwd_is_written(order_api: str, tmp_path: Path) -> None:
    _assert_written(order_api, Path("evidence.json"))
    assert (tmp_path / "evidence.json").is_file()


def test_absolute_evidence_path_outside_the_cwd_is_refused(
    order_api: str, tmp_path: Path, work: Path
) -> None:
    evidence = tmp_path / "evidence.json"
    _assert_refused(order_api, evidence)
    assert not evidence.exists()


def test_absolute_evidence_path_through_a_symlinked_dir_cannot_leave_the_cwd(
    order_api: str, work: Path, outside: Path
) -> None:
    _assert_refused(order_api, work / "out" / "evidence.json")
    assert list(outside.iterdir()) == []


def test_absolute_evidence_path_inside_the_cwd_is_written(order_api: str, tmp_path: Path) -> None:
    _assert_written(order_api, tmp_path / "evidence.json")
