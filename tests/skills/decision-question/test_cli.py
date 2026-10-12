"""CLI and entry-point tests for the decision-question engine."""

from __future__ import annotations

import json
import runpy
import subprocess
import sys
from pathlib import Path
from typing import Any

import decision_question as dq
import pytest
from decision_briefs import make_brief, raw_decision

SCRIPT = Path(dq.__file__)


# --- CLI --------------------------------------------------------------------


def _run(tmp_path: Path, payload: Any, *args: str) -> subprocess.CompletedProcess[str]:
    brief = tmp_path / "brief.json"
    brief.write_text(payload if isinstance(payload, str) else json.dumps(payload), encoding="utf-8")
    return subprocess.run(
        [sys.executable, "-I", str(SCRIPT), "--brief", str(brief), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_ask_exits_zero(tmp_path: Path) -> None:
    done = _run(tmp_path, make_brief(raw_decision("D1")))
    assert done.returncode == 0
    assert json.loads(done.stdout)["status"] == "ask"


def test_cli_single_decision_form(tmp_path: Path) -> None:
    done = _run(tmp_path, {**raw_decision("D1"), "context": {"material_decision": True}})
    assert done.returncode == 0
    assert json.loads(done.stdout)["decision_id"] == "D1"


def test_cli_incomplete_exits_two(tmp_path: Path) -> None:
    done = _run(tmp_path, make_brief(raw_decision("D1", why_now="")))
    assert done.returncode == 2
    assert "why_now" in json.loads(done.stdout)["missing"]


def test_cli_skip_exits_zero(tmp_path: Path) -> None:
    done = _run(tmp_path, make_brief(raw_decision("D1"), delegated=True))
    assert done.returncode == 0
    assert json.loads(done.stdout)["status"] == "skip"


def test_cli_max_options_override(tmp_path: Path) -> None:
    done = _run(tmp_path, make_brief(raw_decision("D1", option_count=6)), "--max-options", "6")
    assert json.loads(done.stdout)["split"] is False


@pytest.mark.parametrize(
    "payload", ["{not json", "[1, 2]", json.dumps({"decisions": [{"statement": "x"}]})]
)
def test_cli_malformed_brief_exits_one(tmp_path: Path, payload: str) -> None:
    done = _run(tmp_path, payload)
    assert done.returncode == 1
    assert done.stderr.startswith("error:")


def test_cli_missing_file_exits_one(tmp_path: Path) -> None:
    done = subprocess.run(
        [sys.executable, "-I", str(SCRIPT), "--brief", str(tmp_path / "absent.json")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 1


def test_cli_cap_below_three_exits_one(tmp_path: Path) -> None:
    done = _run(tmp_path, make_brief(raw_decision("D1", option_count=3)), "--max-options", "2")
    assert done.returncode == 1
    assert "at least 3" in done.stderr


def test_main_returns_codes_in_process(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    brief = tmp_path / "b.json"
    brief.write_text(json.dumps(make_brief(raw_decision("D1"))), encoding="utf-8")
    assert dq.main(["--brief", str(brief)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ask"


def test_main_reports_malformed_brief_in_process(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    brief = tmp_path / "b.json"
    brief.write_text("[1]", encoding="utf-8")
    assert dq.main(["--brief", str(brief)]) == 1
    assert "must be an object" in capsys.readouterr().err


def test_main_incomplete_returns_two_in_process(tmp_path: Path) -> None:
    brief = tmp_path / "b.json"
    brief.write_text(json.dumps(make_brief(raw_decision("D1", statement=""))), encoding="utf-8")
    assert dq.main(["--brief", str(brief)]) == 2


def test_single_decision_form_in_process() -> None:
    single = {**raw_decision("D1"), "context": {"material_decision": True}}
    assert dq.evaluate(single)["decision_id"] == "D1"


def test_module_entry_point_exits_with_main_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    brief = tmp_path / "b.json"
    brief.write_text(json.dumps(make_brief(raw_decision("D1"), delegated=True)), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--brief", str(brief)])
    with pytest.raises(SystemExit) as raised:
        runpy.run_path(str(SCRIPT), run_name="__main__")
    assert raised.value.code == 0
