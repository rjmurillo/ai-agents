"""The threshold gate reports every failure in one run (issue #7481).

``check_thresholds`` used to return 11 at the first quality below its floor,
so each run named one file and hid the rest. The JSON report held raw scores
only, so a caller could not get the verdict without re-implementing the
threshold rules. These tests drive ``main(argv)`` and read stderr, the JSON
report, and the exit code from the same run.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[3]
    / ".claude"
    / "skills"
    / "code-qualities-assessment"
    / "scripts"
    / "assess.py"
)
_spec = importlib.util.spec_from_file_location("assess_threshold_report", _SCRIPT)
assert _spec is not None and _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
main = _mod.main

_FOCUSED = "def alpha():\n    return 1\n"
# 40 definitions: cohesion scores 1.0 at confidence 0.4, below the default 7.
_SPRAWLING = "".join(f"def f{i}():\n    return {i}\n\n" for i in range(40))
# 15 imports: coupling scores 1.0 at confidence 0.6, below the default 7.
_COUPLED = "".join(f"import mod{i}\n" for i in range(15)) + _FOCUSED


def _write(root: Path, name: str, body: str | bytes) -> Path:
    path = root / name
    if isinstance(body, bytes):
        path.write_bytes(body)
    else:
        path.write_text(body, encoding="utf-8")
    return path


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )


def _commit(repo: Path, name: str, body: str | bytes, message: str) -> None:
    _write(repo, name, body)
    _git(repo, "add", name)
    _git(repo, "commit", "-m", message)


def _init_repo(repo: Path) -> None:
    _git(repo, "init")
    _git(repo, "checkout", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")


def _run(argv: list[str], output: Path) -> tuple[int, dict[str, dict[str, Any]]]:
    rc = main([*argv, "--format", "json", "--output", str(output)])
    report = json.loads(output.read_text(encoding="utf-8"))
    gates = {Path(f["file_path"]).name: f["threshold_gate"] for f in report["files"]}
    return rc, gates


def _floor_config(tmp_path: Path) -> str:
    """The built-in defaults plus a 0.5 confidence floor.

    A config file replaces the defaults rather than merging into them, so it
    must carry the thresholds too.
    """
    config = _mod.load_config(str(tmp_path / "absent.qualityrc.json"))
    return json.dumps({**config, "minConfidence": 0.5})


def _failed_lines(err: str) -> list[str]:
    return [line for line in err.splitlines() if line.startswith("❌")]


def test_two_files_failing_different_qualities_are_both_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(tmp_path, "sprawling.py", _SPRAWLING)
    _write(tmp_path, "coupled.py", _COUPLED)
    monkeypatch.chdir(tmp_path)

    rc, gates = _run(["--target", "."], tmp_path / "out.json")

    assert rc == 11
    failed = _failed_lines(capsys.readouterr().err)
    assert any("sprawling.py: Cohesion 1.0 < 7" in line for line in failed)
    assert any("coupled.py: Coupling 1.0 < 7" in line for line in failed)
    assert len(failed) == 2
    assert gates["sprawling.py"] == {
        "failed": True,
        "unscored_supported_source": False,
        "below_threshold": [
            {
                "quality": "cohesion",
                "score": 1.0,
                "minimum": 7,
                "confidence": 0.4,
                "advisory": False,
            }
        ],
    }
    coupled = gates["coupled.py"]
    assert coupled is not None
    assert coupled["failed"] is True
    assert [m["quality"] for m in coupled["below_threshold"]] == ["coupling"]


def test_every_failing_quality_in_one_file_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    body = "".join(f"import mod{i}\n" for i in range(15)) + _SPRAWLING
    _write(tmp_path, "both.py", body)
    monkeypatch.chdir(tmp_path)

    rc, gates = _run(["--target", "."], tmp_path / "out.json")

    assert rc == 11
    failed = _failed_lines(capsys.readouterr().err)
    assert any("both.py: Cohesion" in line for line in failed)
    assert any("both.py: Coupling" in line for line in failed)
    gate = gates["both.py"]
    assert gate is not None
    qualities = [m["quality"] for m in gate["below_threshold"]]
    assert qualities[:2] == ["cohesion", "coupling"]


def test_passing_file_carries_an_empty_verdict_and_exits_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(tmp_path, "focused.py", _FOCUSED)
    monkeypatch.chdir(tmp_path)

    rc, gates = _run(["--target", "."], tmp_path / "out.json")

    assert rc == 0
    assert _failed_lines(capsys.readouterr().err) == []
    assert gates["focused.py"] == {
        "failed": False,
        "unscored_supported_source": False,
        "below_threshold": [],
    }


def test_advisory_miss_is_listed_but_does_not_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(tmp_path, "sprawling.py", _SPRAWLING)
    _write(tmp_path, ".qualityrc.json", _floor_config(tmp_path))
    monkeypatch.chdir(tmp_path)

    rc, gates = _run(["--target", "sprawling.py"], tmp_path / "out.json")

    assert rc == 0
    err = capsys.readouterr().err
    assert _failed_lines(err) == []
    assert "advisory" in err
    gate = gates["sprawling.py"]
    assert gate is not None
    assert gate["failed"] is False
    assert gate["below_threshold"][0]["quality"] == "cohesion"
    assert gate["below_threshold"][0]["advisory"] is True


def test_advisory_miss_does_not_hide_a_later_hard_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(tmp_path, "sprawling.py", _SPRAWLING)
    _write(tmp_path, "coupled.py", _COUPLED)
    _write(tmp_path, ".qualityrc.json", _floor_config(tmp_path))
    monkeypatch.chdir(tmp_path)

    rc, gates = _run(["--target", "."], tmp_path / "out.json")

    assert rc == 11
    failed = _failed_lines(capsys.readouterr().err)
    assert len(failed) == 1
    assert "coupled.py: Coupling" in failed[0]
    assert gates["sprawling.py"] is not None and gates["sprawling.py"]["failed"] is False
    assert gates["coupled.py"] is not None and gates["coupled.py"]["failed"] is True


def test_regression_mode_reports_every_new_file_and_skips_comparable_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _init_repo(tmp_path)
    _commit(tmp_path, "legacy.py", _SPRAWLING, "base")
    _git(tmp_path, "checkout", "-b", "feature")
    _commit(tmp_path, "legacy.py", "# note\n" + _SPRAWLING, "touch legacy")
    _commit(tmp_path, "sprawling.py", _SPRAWLING, "add sprawling")
    _commit(tmp_path, "coupled.py", _COUPLED, "add coupled")
    monkeypatch.chdir(tmp_path)

    rc, gates = _run(["--target", ".", "--changed-only", "--base", "main"], tmp_path / "out.json")

    assert rc == 11
    failed = _failed_lines(capsys.readouterr().err)
    assert any("sprawling.py: Cohesion" in line for line in failed)
    assert any("coupled.py: Coupling" in line for line in failed)
    assert not any("legacy.py" in line for line in failed)
    # The absolute gate never examined the comparable file, so its verdict is
    # null rather than a pass it did not earn.
    assert gates["legacy.py"] is None
    assert gates["sprawling.py"] is not None and gates["sprawling.py"]["failed"] is True
    assert gates["coupled.py"] is not None and gates["coupled.py"]["failed"] is True


def test_regression_mode_reports_unscored_source_and_a_later_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _init_repo(tmp_path)
    _commit(tmp_path, "seed.py", _FOCUSED, "base")
    _git(tmp_path, "checkout", "-b", "feature")
    # Invalid UTF-8: the scanner cannot decode it, so every quality is unscored.
    _commit(tmp_path, "aaa_unreadable.py", b"\xff\xfe\x00def broken(:\n", "add unreadable")
    _commit(tmp_path, "zzz_coupled.py", _COUPLED, "add coupled")
    monkeypatch.chdir(tmp_path)

    rc, gates = _run(["--target", ".", "--changed-only", "--base", "main"], tmp_path / "out.json")

    assert rc == 11
    failed = _failed_lines(capsys.readouterr().err)
    assert any(
        "aaa_unreadable.py: supported authored source could not be scored" in line
        for line in failed
    )
    assert any("zzz_coupled.py: Coupling" in line for line in failed)
    assert gates["aaa_unreadable.py"] == {
        "failed": True,
        "unscored_supported_source": True,
        "below_threshold": [],
    }
    assert gates["zzz_coupled.py"] is not None and gates["zzz_coupled.py"]["failed"] is True
