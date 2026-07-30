from __future__ import annotations

import subprocess

from scripts.ci import count_ratchet


def test_chunk_respects_argv_budget():
    paths = [f"{'x' * 99}{index}.py" for index in range(500)]
    batches = count_ratchet.chunk(paths, budget=1000)
    assert sum(len(batch) for batch in batches) == len(paths)
    assert all(sum(len(p.encode("utf-8")) + 1 for p in batch) <= 1000 for batch in batches)
    assert all(batch for batch in batches)


def test_chunk_measures_bytes_not_characters():
    # A non-ASCII path costs more argv than it has characters. Measuring
    # characters would pack batches over the ceiling the budget exists to
    # respect. Each name here is 13 characters but 22 UTF-8 bytes.
    stem = "\u00e9" * 9
    paths = [f"{stem}{index}.py" for index in range(10)]
    assert len(paths[0]) == 13
    assert len(paths[0].encode("utf-8")) == 22
    batches = count_ratchet.chunk(paths, budget=46)
    assert sum(len(batch) for batch in batches) == len(paths)
    assert all(sum(len(p.encode("utf-8")) + 1 for p in batch) <= 46 for batch in batches)
    # Two per batch fits the byte budget; a character measure would pack three.
    assert max(len(batch) for batch in batches) == 2


def test_single_path_longer_than_budget_still_scanned():
    # A path larger than the whole budget must not be silently dropped.
    oversized = "y" * 5000 + ".py"
    assert count_ratchet.chunk([oversized], budget=100) == [[oversized]]


def test_tracked_files_returns_none_when_git_fails(tmp_path, monkeypatch):
    def _run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 128, stdout="", stderr="not a repo\n")

    monkeypatch.setattr(subprocess, "run", _run)
    assert count_ratchet.tracked_files(tmp_path, ("*.py",)) is None


def test_tracked_files_drops_the_nul_terminator(tmp_path, monkeypatch):
    def _run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout="a.py\0b.py\0", stderr="")

    monkeypatch.setattr(subprocess, "run", _run)
    assert count_ratchet.tracked_files(tmp_path, ("*.py",)) == ["a.py", "b.py"]


def test_read_baseline_rejects_a_non_integer(tmp_path):
    path = tmp_path / "b.txt"
    path.write_text("not a number\n", encoding="utf-8")
    assert count_ratchet.read_baseline(path) is None


def test_read_baseline_returns_none_when_missing(tmp_path):
    assert count_ratchet.read_baseline(tmp_path / "absent.txt") is None
