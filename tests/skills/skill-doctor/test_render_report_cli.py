"""render_report.py exit codes for unreadable and incomplete reports."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from render_report import main


def _run(path: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    with pytest.raises(SystemExit) as exc:
        main([str(path)])
    return int(exc.value.code or 0), capsys.readouterr().err


def test_missing_report_exits_2_without_a_traceback(tmp_path, capsys):
    code, err = _run(tmp_path / "missing.json", capsys)

    assert code == 2
    assert err.startswith("error: cannot read")
    assert "Traceback" not in err


def test_malformed_json_exits_2_without_a_traceback(tmp_path, capsys):
    path = tmp_path / "report.json"
    path.write_text("{not json", encoding="utf-8")

    code, err = _run(path, capsys)

    assert code == 2
    assert "Traceback" not in err
    assert not (tmp_path / "report.html").exists()


@pytest.mark.parametrize("report", [{}, [], {"scores": {}}, {"scores": {"overall": "high"}}])
def test_report_without_numeric_overall_exits_1(tmp_path, capsys, report):
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report), encoding="utf-8")

    code, err = _run(path, capsys)

    assert code == 1
    assert "needs a numeric scores.overall" in err
    assert not (tmp_path / "report.html").exists()


def test_valid_report_renders_and_names_the_share_button(tmp_path, capsys):
    path = tmp_path / "report.json"
    path.write_text(json.dumps({"scores": {"overall": 0.8}}), encoding="utf-8")

    main([str(path)])

    out = capsys.readouterr().out
    assert (tmp_path / "report.html").is_file()
    assert "Share button" in out


def test_skill_md_names_the_current_share_and_toggle_labels():
    text = (
        Path(__file__).resolve().parents[3] / "src/claude/skills/skill-doctor/SKILL.md"
    ).read_text(encoding="utf-8")

    assert '"Share" button' in text and '"Show more" toggle' in text
    assert "share as png" not in text
