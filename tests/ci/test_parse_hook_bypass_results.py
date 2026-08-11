"""Tests for scripts/ci/parse_hook_bypass_results.py.

Covers the audit-hook-bypass workflow's count-extraction contract. The workflow
previously parsed the detector JSON with an inline `python3 -c` heredoc (logic in
YAML, ADR-006 violation, untestable). These tests pin the extracted script: it
reads `bypass_indicators` from the detector's `AuditReport` JSON, writes the
length, and fails loud on malformed input rather than silently reporting 0.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Add scripts/ci to path for import.
_SCRIPTS_CI = Path(__file__).resolve().parent.parent.parent / "scripts" / "ci"
_original_path = sys.path.copy()
try:
    sys.path.insert(0, str(_SCRIPTS_CI))
    from parse_hook_bypass_results import main
finally:
    sys.path[:] = _original_path


def _report(indicator_count: int) -> dict[str, object]:
    """An AuditReport-shaped payload with the requested number of indicators."""
    return {
        "timestamp": "2026-01-01T00:00:00Z",
        "branch": "feature/x",
        "base_ref": "origin/main",
        "total_commits": 3,
        "bypass_indicators": [
            {"commit": f"abc{i}", "reason": "no-verify"} for i in range(indicator_count)
        ],
    }


def test_counts_indicators(tmp_path: Path) -> None:
    src = tmp_path / "audit.json"
    src.write_text(json.dumps(_report(2)), encoding="utf-8")
    out = tmp_path / "count.txt"
    code = main(["--input", str(src), "--count-out", str(out)])
    assert code == 0
    assert out.read_text(encoding="utf-8").strip() == "2"


def test_zero_indicators_is_clean_count(tmp_path: Path) -> None:
    src = tmp_path / "audit.json"
    src.write_text(json.dumps(_report(0)), encoding="utf-8")
    out = tmp_path / "count.txt"
    code = main(["--input", str(src), "--count-out", str(out)])
    assert code == 0
    assert out.read_text(encoding="utf-8").strip() == "0"


def test_missing_input_is_usage_error(tmp_path: Path) -> None:
    out = tmp_path / "count.txt"
    code = main(["--input", str(tmp_path / "nope.json"), "--count-out", str(out)])
    assert code == 2
    assert not out.exists()


def test_malformed_json_fails_loud(tmp_path: Path) -> None:
    src = tmp_path / "audit.json"
    src.write_text("{not json", encoding="utf-8")
    out = tmp_path / "count.txt"
    code = main(["--input", str(src), "--count-out", str(out)])
    assert code == 1
    assert not out.exists()


def test_unreadable_input_is_usage_error(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    src = tmp_path / "audit.json"
    src.write_text(json.dumps(_report(1)), encoding="utf-8")
    out = tmp_path / "count.txt"

    def unreadable(*_args: object, **_kwargs: object) -> str:
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "read_text", unreadable)
    code = main(["--input", str(src), "--count-out", str(out)])

    assert code == 2
    assert not out.exists()
    assert "cannot read input" in capsys.readouterr().err


def test_undecodable_input_is_malformed_error(
    tmp_path: Path, capsys
) -> None:
    src = tmp_path / "audit.json"
    src.write_bytes(b"\xff")
    out = tmp_path / "count.txt"

    code = main(["--input", str(src), "--count-out", str(out)])

    assert code == 1
    assert not out.exists()
    assert "malformed UTF-8" in capsys.readouterr().err


def test_missing_indicators_key_fails_loud(tmp_path: Path) -> None:
    # A payload with no bypass_indicators list must NOT silently report 0; that
    # would mask a schema drift in detect_hook_bypass.py the same way #2808's
    # crash-masking did.
    src = tmp_path / "audit.json"
    src.write_text(json.dumps({"branch": "x"}), encoding="utf-8")
    out = tmp_path / "count.txt"
    code = main(["--input", str(src), "--count-out", str(out)])
    assert code == 1
    assert not out.exists()


def test_top_level_array_fails_loud(tmp_path: Path) -> None:
    src = tmp_path / "audit.json"
    src.write_text(json.dumps([_report(1)]), encoding="utf-8")
    out = tmp_path / "count.txt"
    code = main(["--input", str(src), "--count-out", str(out)])
    assert code == 1
    assert not out.exists()


def test_non_list_indicators_fails_loud(tmp_path: Path) -> None:
    src = tmp_path / "audit.json"
    src.write_text(json.dumps({"bypass_indicators": "abc"}), encoding="utf-8")
    out = tmp_path / "count.txt"
    code = main(["--input", str(src), "--count-out", str(out)])
    assert code == 1
    assert not out.exists()
