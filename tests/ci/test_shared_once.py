"""compute_once shares one result across xdist workers (issue #6239)."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.ci import shared_once


def _counting(values: frozenset[str]) -> tuple[list[int], Callable[[], frozenset[str]]]:
    calls: list[int] = []

    def compute() -> frozenset[str]:
        calls.append(1)
        return values

    return calls, compute


@pytest.fixture
def run_uid(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> str:
    monkeypatch.setenv("PYTEST_XDIST_TESTRUNUID", "uid-1")
    monkeypatch.setattr(shared_once.tempfile, "gettempdir", lambda: str(tmp_path))
    return "uid-1"


def test_without_xdist_the_value_is_computed_in_place(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PYTEST_XDIST_TESTRUNUID", raising=False)
    calls, compute = _counting(frozenset({"a"}))
    assert shared_once.compute_once("x", compute) == frozenset({"a"})
    assert len(calls) == 1


def test_the_second_worker_reads_the_first_workers_result(run_uid: str) -> None:
    calls, compute = _counting(frozenset({"a", "b"}))
    first = shared_once.compute_once("x", compute)
    second = shared_once.compute_once("x", compute)
    assert first == second == frozenset({"a", "b"})
    assert len(calls) == 1


def test_the_lock_is_released_after_a_write(run_uid: str, tmp_path: Path) -> None:
    _calls, compute = _counting(frozenset({"a"}))
    shared_once.compute_once("x", compute)
    assert not list(tmp_path.glob("*.lock"))
    assert not list(tmp_path.glob("*.tmp"))


def test_a_failing_compute_releases_the_lock_and_raises(run_uid: str, tmp_path: Path) -> None:
    def boom() -> frozenset[str]:
        raise RuntimeError("scan failed")

    with pytest.raises(RuntimeError, match="scan failed"):
        shared_once.compute_once("x", boom)
    assert not list(tmp_path.glob("*.lock"))
    assert not list(tmp_path.glob("x-*.json"))


def test_a_stale_lock_makes_the_waiter_compute_locally(
    run_uid: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / f"x-{run_uid}.lock").write_text("", encoding="utf-8")
    monkeypatch.setattr(shared_once, "WAIT_SECONDS", 0.3)
    monkeypatch.setattr(shared_once, "_POLL_SECONDS", 0.05)
    calls, compute = _counting(frozenset({"z"}))
    assert shared_once.compute_once("x", compute) == frozenset({"z"})
    assert len(calls) == 1
    assert os.path.exists(tmp_path / f"x-{run_uid}.lock")
