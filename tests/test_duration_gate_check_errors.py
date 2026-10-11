"""Exit codes of the leg wall time gate CLI on bad input."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.testing.duration_gate_check import main
from tests.duration_test_helpers import write_junit


def test_a_missing_input_exits_three(tmp_path: Path) -> None:
    assert main([str(tmp_path / "absent.xml")]) == 3


def test_an_unparseable_input_exits_three(tmp_path: Path) -> None:
    path = tmp_path / "broken.xml"
    path.write_text("<testsuites>", encoding="utf-8")
    assert main([str(path)]) == 3


def test_a_report_declaring_a_dtd_exits_two(tmp_path: Path) -> None:
    path = tmp_path / "evil.xml"
    path.write_text('<!DOCTYPE x [<!ENTITY a "b">]><testsuites/>', encoding="utf-8")
    assert main([str(path)]) == 2


def test_a_report_with_no_testcases_exits_one(tmp_path: Path) -> None:
    assert main([str(write_junit(tmp_path, "p", {}, 0.0))]) == 1


def test_a_non_positive_limit_is_an_argument_error(tmp_path: Path) -> None:
    report = write_junit(tmp_path, "p", {"tests.test_alpha": [1.0]}, 1.0)
    with pytest.raises(SystemExit) as exc:
        main([str(report), "--leg-limit", "0"])
    assert exc.value.code == 2
