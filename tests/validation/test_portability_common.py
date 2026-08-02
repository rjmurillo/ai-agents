from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts.validation import portability_common as common


def _message(rel: str, count: int, allowed: int) -> str:
    return f"{rel}: {count} refs (baseline {allowed})"


def test_load_baseline_rejects_string_count(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"files": {"skills/a.py": "2"}}), encoding="utf-8")

    with pytest.raises(ValueError, match="integer"):
        common.load_baseline(baseline)


def test_load_baseline_rejects_float_count(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"files": {"skills/a.py": 2.5}}), encoding="utf-8")

    with pytest.raises(ValueError, match="integer"):
        common.load_baseline(baseline)


def test_load_baseline_rejects_bool_count(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"files": {"skills/a.py": True}}), encoding="utf-8")

    with pytest.raises(ValueError, match="integer"):
        common.load_baseline(baseline)


def test_load_baseline_accepts_integer_count(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"files": {"skills/a.py": 2}}), encoding="utf-8")

    assert common.load_baseline(baseline) == {"skills/a.py": 2}


def test_load_baseline_rejects_null_count(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"files": {"skills/a.py": None}}), encoding="utf-8")

    with pytest.raises(ValueError, match="integer"):
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
        is None
    )


def test_git_lines_strips_git_overrides_case_insensitively(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured_env: dict[str, str] = {}

    def run_git(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        env = kwargs["env"]
        assert isinstance(env, dict)
        captured_env.update(env)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setenv("git_index_file", "/wrong/index")
    monkeypatch.setenv("Git_Dir", "/wrong/repo")
    monkeypatch.setenv("PORTABILITY_TEST_SENTINEL", "kept")
    monkeypatch.setattr(common.subprocess, "run", run_git)

    assert common._git_lines(tmp_path, ["status"]) == []
    assert "git_index_file" not in captured_env
    assert "Git_Dir" not in captured_env
    assert captured_env["PORTABILITY_TEST_SENTINEL"] == "kept"
