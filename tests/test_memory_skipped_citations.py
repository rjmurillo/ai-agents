"""A skipped citation check never raises recall confidence (issue #7493, decision D9)."""

from __future__ import annotations

from pathlib import Path

import pytest

from memory_enhancement import search
from memory_enhancement.verification import MAX_VERIFY_BYTES

_BODY = "Move every service behind the gateway.\n"


def _repo(tmp_path: Path) -> Path:
    (tmp_path / ".git").mkdir()
    directory = tmp_path / ".serena" / "memories"
    directory.mkdir(parents=True)
    return directory


def _memory(directory: Path, name: str, body: str = _BODY) -> Path:
    path = directory / f"{name}.md"
    path.write_text(f"# {name}\n\n" + body, encoding="utf-8")
    return path


def test_a_skipped_check_never_scores_above_a_verified_memory(tmp_path: Path) -> None:
    directory = _repo(tmp_path)
    (tmp_path / "small.py").write_text("a\nb\nc\n", encoding="utf-8")
    (tmp_path / "big.py").write_text("x\n" * (MAX_VERIFY_BYTES // 2 + 10), encoding="utf-8")
    verified = _memory(
        directory,
        "verified",
        body="Body.\n\n[cite:file](small.py:1)\n[cite:file](small.py:2)\n",
    )
    skipped = _memory(
        directory,
        "skipped",
        body="Body.\n\n[cite:file](missing.py:1)\n[cite:file](big.py:3)\n",
    )

    results = search.rank_results([verified, skipped], tmp_path, max_verify_bytes=MAX_VERIFY_BYTES)

    by_id = {r.memory_id: r for r in results}
    assert by_id["skipped"].citation_status == "unverified"
    assert by_id["verified"].citation_status == "verified"
    assert by_id["skipped"].confidence < by_id["verified"].confidence


def test_a_skipped_check_scores_like_its_failed_citations(tmp_path: Path) -> None:
    directory = _repo(tmp_path)
    (tmp_path / "big.py").write_text("x\n" * (MAX_VERIFY_BYTES // 2 + 10), encoding="utf-8")
    skipped = _memory(directory, "skipped", body="Body.\n\n[cite:file](big.py:3)\n")
    broken = _memory(directory, "broken", body="Body.\n\n[cite:file](missing.py:1)\n")

    results = search.rank_results([skipped, broken], tmp_path, max_verify_bytes=MAX_VERIFY_BYTES)

    by_id = {r.memory_id: r for r in results}
    assert by_id["skipped"].confidence == pytest.approx(by_id["broken"].confidence, abs=0.01)
