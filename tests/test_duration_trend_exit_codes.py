"""Exit codes of the duration trend CLI on bad input, arguments, and outputs."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.testing.duration_trend import main
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


@pytest.mark.parametrize(("flag", "value"), [("--max-history", "0"), ("--top", "0")])
def test_a_non_positive_count_exits_two(tmp_path: Path, flag: str, value: str) -> None:
    report = write_junit(tmp_path, "p", {"tests.test_alpha": [1.0]}, 1.0)

    assert main([str(report), flag, value]) == 2


def test_a_non_positive_threshold_is_an_argument_error(tmp_path: Path) -> None:
    report = write_junit(tmp_path, "p", {"tests.test_alpha": [1.0]}, 1.0)

    with pytest.raises(SystemExit) as exc:
        main([str(report), "--module-ratio", "0"])
    assert exc.value.code == 2


def test_an_unwritable_summary_exits_three(tmp_path: Path) -> None:
    report = write_junit(tmp_path, "p", {"tests.test_alpha": [1.0]}, 1.0)

    assert main([str(report), "--summary", str(tmp_path / "no" / "dir.md")]) == 3


def test_a_failed_history_write_leaves_no_summary_and_reports_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report = write_junit(tmp_path, "p", {"tests.test_alpha": [1.0]}, 1.0)
    blocker = tmp_path / "file"
    blocker.write_text("", encoding="utf-8")
    summary = tmp_path / "summary.md"

    rc = main([str(report), "--write-history", str(blocker / "history.json"),
               "--summary", str(summary)])

    assert rc == 3
    assert not summary.exists()
    assert "::error title=Test duration report::could not write output" in (
        capsys.readouterr().out)
