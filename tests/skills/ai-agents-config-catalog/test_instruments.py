"""Tests for the ai-agents-config-catalog skill dispatcher instruments.py."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / ".claude/skills/ai-agents-config-catalog/scripts/instruments.py"
spec = importlib.util.spec_from_file_location("instruments", SCRIPT)
instruments = importlib.util.module_from_spec(spec)
spec.loader.exec_module(instruments)


def test_ai_agents_config_catalog_list_all_rows_exist(capsys):
    assert instruments.main(["--repo", str(ROOT), "list"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["skill"] == "ai-agents-config-catalog"
    assert out["missing"] == [] and out["examined"] == len(out["instruments"])
    ids = {r["id"] for r in out["instruments"]}
    assert {"drift-self-check", "hook-counts", "pytest-markers", "retired-flags"} <= ids


def test_list_missing_row_exits_1(monkeypatch, capsys):
    row = {"id": "ghost", "answers": "x", "argv": ["python3", "no/such.py"], "source": "x"}
    monkeypatch.setattr(instruments, "INSTRUMENTS", [row])
    assert instruments.main(["--repo", str(ROOT), "list"]) == 1
    assert json.loads(capsys.readouterr().out)["missing"] == ["ghost"]


def test_run_unknown_id_exits_2():
    assert instruments.main(["--repo", str(ROOT), "run", "nope"]) == 2


def test_run_passes_child_exit_code(monkeypatch):
    argv = ["python3", "-c", "import sys; sys.exit(7)"]
    row = {"id": "seven", "answers": "x", "argv": argv, "source": "x"}
    monkeypatch.setattr(instruments, "INSTRUMENTS", [row])
    assert instruments.main(["--repo", str(ROOT), "run", "seven"]) == 7


def test_run_start_failure_exits_3(monkeypatch):
    row = {"id": "nobin", "answers": "x", "argv": ["definitely-not-a-binary-xyz"], "source": "x"}
    monkeypatch.setattr(instruments, "INSTRUMENTS", [row])
    assert instruments.main(["--repo", str(ROOT), "run", "nobin"]) == 3


def test_help_exits_0():
    assert instruments.main(["--help"]) == 0
