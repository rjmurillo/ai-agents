"""public_export.py writes its summary atomically (epic #7248, M4)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import public_export
import pytest

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "audit" / "report.json"


def test_failed_replace_keeps_the_previous_summary_and_leaves_no_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = tmp_path / "report.json"
    shutil.copy(FIXTURE, report)
    out = tmp_path / "public.json"
    out.write_text("previous\n", encoding="utf-8")

    def refuse(src: str, dst: str) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", refuse)

    code = public_export.main([str(report), "--out", str(out)])

    assert code == 2
    assert out.read_text(encoding="utf-8") == "previous\n"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["public.json", "report.json"]


def test_successful_export_replaces_the_previous_summary(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    shutil.copy(FIXTURE, report)
    out = tmp_path / "public.json"
    out.write_text("previous\n", encoding="utf-8")

    code = public_export.main([str(report), "--out", str(out)])

    assert code == 0
    assert out.read_text(encoding="utf-8").startswith("{")
