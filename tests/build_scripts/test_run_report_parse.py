"""Tests for guard-maturity run_report._parse_subprocess_json.

Cover the contract-violation boundary the guard-maturity report relies on
when it shells out to aggregate_guard_intercepts.py and
classify_guard_maturity.py: a returncode-0 child whose stdout is not a JSON
object is a broken contract, not a value to propagate. Pin all three shapes:

- positive: a JSON object parses and returns as a dict.
- negative: non-JSON stdout raises SystemExit(3) (external error, ADR-035).
- edge: valid JSON that is not an object (list, string, null) also raises
  SystemExit(3) instead of leaking an AttributeError downstream.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_RUN_REPORT = (
    _REPO_ROOT / ".claude" / "skills" / "guard-maturity" / "scripts" / "run_report.py"
)


def _load_run_report():
    spec = importlib.util.spec_from_file_location("_gm_run_report_undertest", _RUN_REPORT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


run_report = _load_run_report()


def test_parses_json_object_to_dict():
    result = run_report._parse_subprocess_json('{"guard": "x", "intercepts": 3}', "child")
    assert result == {"guard": "x", "intercepts": 3}


def test_non_json_stdout_exits_3():
    with pytest.raises(SystemExit) as excinfo:
        run_report._parse_subprocess_json("not json at all", "child")
    assert excinfo.value.code == 3


def test_empty_stdout_exits_3():
    with pytest.raises(SystemExit) as excinfo:
        run_report._parse_subprocess_json("", "child")
    assert excinfo.value.code == 3


@pytest.mark.parametrize("payload", ["[1, 2, 3]", '"a string"', "null", "42"])
def test_non_object_json_exits_3(payload: str):
    with pytest.raises(SystemExit) as excinfo:
        run_report._parse_subprocess_json(payload, "child")
    assert excinfo.value.code == 3
