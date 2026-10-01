"""The promotion exceptions gate fails on an invalid file or a lapsed record.

ADR-113 decision 8, issue #5636. Each failure path is driven through ``main``
and asserted on its exit code, because a gate that prints but exits 0 is the
silent pass this epic exists to remove.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from scripts.validation.check_promotion_exceptions import (
    EXIT_CONFIG,
    EXIT_LOGIC,
    EXIT_OK,
    REASON_INVALID,
    REASON_LAPSED,
    main,
    validate_promotion_exceptions,
)
from scripts.validation.evidence import EvidenceState
from scripts.validation.promotion_exceptions import EXCEPTIONS_RELATIVE_PATH

REPO_ROOT = Path(__file__).resolve().parents[2]
TODAY = date(2026, 10, 1)


def _entry(**overrides: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "validator": "pytest",
        "reason": "tests.failed",
        "scope": "tests/",
        "rationale": "Known flaky test tracked in a ticket.",
        "owner": "rjmurillo",
        "approval": {"pr": 100, "reviewer": "second-owner"},
        "expires": "2026-12-31",
        "remediate_by": "2026-11-30",
    }
    entry.update(overrides)
    return entry


def _write(root: Path, entries: list[dict[str, Any]]) -> None:
    path = root / EXCEPTIONS_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema_version": "1", "entries": entries}), encoding="utf-8")


def _run(root: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    code = main(["--repo-root", str(root), "--today", TODAY.isoformat()])
    return code, capsys.readouterr().out


def test_missing_file_passes_with_zero_examined(tmp_path: Path) -> None:
    outcome = validate_promotion_exceptions(tmp_path, TODAY)
    assert outcome.state is EvidenceState.PASS
    assert outcome.examined == 0


def test_valid_unlapsed_record_passes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write(tmp_path, [_entry()])
    code, out = _run(tmp_path, capsys)
    assert code == EXIT_OK
    assert "examined=1" in out


def test_expired_record_fails_with_exit_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(tmp_path, [_entry(expires="2026-09-30", remediate_by="2026-09-30")])
    code, out = _run(tmp_path, capsys)
    assert code == EXIT_LOGIC
    assert REASON_LAPSED in out
    assert "expired: validator='pytest' reason='tests.failed' scope='tests/'" in out
    assert "expires=2026-09-30" in out


def test_a_lapsed_item_record_is_named_with_its_item(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(tmp_path, [_entry(item="a.py", expires="2026-09-30", remediate_by="2026-09-30")])
    _, out = _run(tmp_path, capsys)
    assert "item='a.py'" in out


def test_overdue_remediation_fails_with_exit_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(tmp_path, [_entry(remediate_by="2026-09-30")])
    code, out = _run(tmp_path, capsys)
    assert code == EXIT_LOGIC
    assert "remediation_overdue" in out


def test_expiry_day_itself_passes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write(tmp_path, [_entry(expires="2026-10-01", remediate_by="2026-10-01")])
    assert _run(tmp_path, capsys)[0] == EXIT_OK


def test_one_lapsed_among_valid_still_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    lapsed = _entry(scope="old/", expires="2026-01-01", remediate_by="2026-01-01")
    _write(tmp_path, [_entry(), lapsed])
    code, out = _run(tmp_path, capsys)
    assert code == EXIT_LOGIC
    assert "findings=1" in out


def test_invalid_file_fails_with_exit_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write(tmp_path, [_entry(owner="")])
    code, out = _run(tmp_path, capsys)
    assert code == EXIT_CONFIG
    assert REASON_INVALID in out


def test_unparseable_file_fails_with_exit_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / EXCEPTIONS_RELATIVE_PATH
    path.parent.mkdir(parents=True)
    path.write_text("{nope", encoding="utf-8")
    assert _run(tmp_path, capsys)[0] == EXIT_CONFIG


def test_default_date_is_today_in_utc(tmp_path: Path) -> None:
    _write(tmp_path, [_entry(expires="2000-01-01", remediate_by="2000-01-01")])
    assert validate_promotion_exceptions(tmp_path).state is EvidenceState.FAIL


def test_main_without_today_uses_the_clock(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--repo-root", str(tmp_path)]) == EXIT_OK
    assert "examined=0" in capsys.readouterr().out


def test_the_shipped_exceptions_file_passes_the_gate() -> None:
    """Rule 13 of ci-scripts.md: the gate passes against the real corpus."""
    assert main(["--repo-root", str(REPO_ROOT)]) == EXIT_OK
