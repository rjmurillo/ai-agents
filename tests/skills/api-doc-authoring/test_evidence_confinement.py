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


def _report() -> dict[str, object]:
    return {"verdict": "PASS", "doc_sha256": {}}


def test_unrelated_file_planted_after_the_check_is_not_replaced(work: Path) -> None:
    """The write checks the target again, so a file created during the run survives."""
    evidence = ax._check_evidence_path("evidence.json")
    evidence.write_text("# planted during the run\n", encoding="utf-8")

    with pytest.raises(ax.InputError, match="not a prior evidence report"):
        ax._write_evidence(evidence, _report())

    assert evidence.read_text(encoding="utf-8") == "# planted during the run\n"


def test_parent_swapped_for_a_symlink_after_the_check_is_refused(
    tmp_path: Path, work: Path
) -> None:
    """A directory replaced by a link to outside the cwd during the run is caught at write."""
    (work / "sub").mkdir()
    evidence = ax._check_evidence_path(str(Path("sub") / "evidence.json"))
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (work / "sub").rename(work / "sub-old")
    _link(work / "sub", elsewhere)

    with pytest.raises(ax.InputError, match=REFUSAL):
        ax._write_evidence(evidence, _report())

    assert list(elsewhere.iterdir()) == []


@pytest.mark.skipif(not ax._ANCHORED_WRITES, reason="needs O_NOFOLLOW and dir_fd support")
def test_parent_swapped_after_the_write_time_check_is_still_refused(
    tmp_path: Path, work: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The no-follow walk closes the gap a path re-check alone leaves open."""
    (work / "sub").mkdir()
    evidence = Path("sub") / "evidence.json"
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    real_parts = ax._parent_parts

    def check_then_swap(raw: str, target: Path) -> tuple[str, ...]:
        parts: tuple[str, ...] = real_parts(raw, target)
        if (work / "sub").is_dir() and not (work / "sub").is_symlink():
            (work / "sub").rename(work / "sub-old")
            _link(work / "sub", elsewhere)
        return parts

    monkeypatch.setattr(ax, "_check_evidence_path", lambda raw: Path(raw))
    monkeypatch.setattr(ax, "_parent_parts", check_then_swap)

    with pytest.raises(ax.InputError, match="cannot write evidence"):
        ax._write_evidence(evidence, _report())

    assert list(elsewhere.iterdir()) == []
    assert list((work / "sub-old").iterdir()) == []


@pytest.mark.skipif(not ax._ANCHORED_WRITES, reason="needs O_NOFOLLOW and dir_fd support")
def test_nested_evidence_path_is_written_through_the_parent_handle(work: Path) -> None:
    """The walk opens each real directory in turn and the report lands in the deepest one."""
    (work / "a" / "b").mkdir(parents=True)
    evidence = Path("a") / "b" / "evidence.json"

    ax._write_evidence(evidence, _report())

    assert json.loads((work / evidence).read_text(encoding="utf-8")) == _report()
    assert [p.name for p in (work / "a" / "b").iterdir()] == ["evidence.json"]
