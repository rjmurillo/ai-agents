"""Tests for scripts/ci/parse_memory_validation_results.py.

Covers the counting step extracted from memory-validation.yml. The stale test
must stay identical to the `jq 'select(.valid == false)'` it replaces: only a
boolean `false` counts stale, so a missing or null `valid` stays valid and the
reported numbers do not move across the extraction. The missing-or-empty file
branch is the Issue #2808 path that used to post a green Pass on a crashed run.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SCRIPTS_CI = Path(__file__).resolve().parent.parent.parent / "scripts" / "ci"
_original_path = sys.path.copy()
try:
    sys.path.insert(0, str(_SCRIPTS_CI))
    from parse_memory_validation_results import counts, main
finally:
    sys.path[:] = _original_path


def _outputs(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    return dict(line.split("=", 1) for line in lines)


def _run(tmp_path: Path, payload: object) -> tuple[int, Path]:
    src = tmp_path / "results.json"
    src.write_text(json.dumps(payload), encoding="utf-8")
    out = tmp_path / "out.txt"
    return main(["--input", str(src), "--output", str(out)]), out


def test_counts_all_valid(tmp_path: Path) -> None:
    rc, out = _run(tmp_path, [{"valid": True}, {"valid": True}])
    assert rc == 0
    assert _outputs(out) == {
        "total": "2",
        "valid": "2",
        "stale": "0",
        "has_stale": "false",
    }


def test_counts_stale_entries(tmp_path: Path) -> None:
    rc, out = _run(tmp_path, [{"valid": True}, {"valid": False}, {"valid": False}])
    assert rc == 0
    assert _outputs(out) == {
        "total": "3",
        "valid": "1",
        "stale": "2",
        "has_stale": "true",
    }


def test_empty_array_is_a_clean_pass(tmp_path: Path) -> None:
    rc, out = _run(tmp_path, [])
    assert rc == 0
    assert _outputs(out) == {
        "total": "0",
        "valid": "0",
        "stale": "0",
        "has_stale": "false",
    }


@pytest.mark.parametrize(
    "entry", [{"valid": None}, {}, {"valid": 0}, {"valid": ""}, {"valid": "false"}]
)
def test_only_boolean_false_counts_stale(entry: dict[str, object]) -> None:
    assert counts([entry]) == (1, 1, 0)


def test_non_dict_entries_are_never_stale() -> None:
    assert counts(["x", 3, None]) == (3, 3, 0)


def test_missing_file_is_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = main(
        ["--input", str(tmp_path / "absent.json"), "--output", str(tmp_path / "o.txt")]
    )
    assert rc == 1
    assert "missing or empty" in capsys.readouterr().out


def test_empty_file_is_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    src = tmp_path / "results.json"
    src.write_text("", encoding="utf-8")
    rc = main(["--input", str(src), "--output", str(tmp_path / "o.txt")])
    assert rc == 1
    assert "missing or empty" in capsys.readouterr().out


def test_malformed_json_is_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    src = tmp_path / "results.json"
    src.write_text("{not json", encoding="utf-8")
    rc = main(["--input", str(src), "--output", str(tmp_path / "o.txt")])
    assert rc == 1
    assert "cannot parse" in capsys.readouterr().out


def test_json_object_instead_of_array_is_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc, _ = _run(tmp_path, {"valid": True})
    assert rc == 1
    assert "not a JSON array" in capsys.readouterr().out


def test_falls_back_to_github_output_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = tmp_path / "results.json"
    src.write_text(json.dumps([{"valid": False}]), encoding="utf-8")
    out = tmp_path / "gh_out.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    assert main(["--input", str(src)]) == 0
    assert _outputs(out)["stale"] == "1"


def test_no_destination_is_a_usage_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    assert main(["--input", str(tmp_path / "results.json")]) == 2
    assert "no --output" in capsys.readouterr().err


def test_output_is_appended_not_truncated(tmp_path: Path) -> None:
    src = tmp_path / "results.json"
    src.write_text(json.dumps([]), encoding="utf-8")
    out = tmp_path / "o.txt"
    out.write_text("existing=1\n", encoding="utf-8")
    main(["--input", str(src), "--output", str(out)])
    assert out.read_text(encoding="utf-8").startswith("existing=1\n")
