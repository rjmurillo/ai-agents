from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.validation import portability_common as common


def _message(rel: str, count: int, allowed: int) -> str:
    return f"{rel}: {count} refs (baseline {allowed})"


def test_load_baseline_accepts_wrapped_files_object(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"files": {"skills/a.py": "2"}}), encoding="utf-8")

    assert common.load_baseline(baseline) == {"skills/a.py": 2}


def test_load_baseline_rejects_null_count(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"files": {"skills/a.py": None}}), encoding="utf-8")

    with pytest.raises(ValueError, match="null"):
        common.load_baseline(baseline)


def test_diff_against_baseline_reports_regression_and_improvement() -> None:
    regressions, improvements = common.diff_against_baseline(
        {"a.py": 3, "b.py": 1},
        {"a.py": 2, "b.py": 2},
        _message,
    )

    assert regressions == ["a.py: 3 refs (baseline 2)"]
    assert improvements == ["b.py: 1 refs (baseline 2)"]


def test_resolve_baseline_rejects_path_outside_repo(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "baseline.json"
    outside.write_text("{}", encoding="utf-8")

    assert (
        common.resolve_baseline_path(
            root,
            outside,
            "default.json",
            reject_outside_root=True,
        )
        == Path("")
    )
