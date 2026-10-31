"""Tests for the ai-agents-empirical-probe-toolkit instruments.py dispatcher."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location(
    "instruments",
    ROOT / ".claude/skills/ai-agents-empirical-probe-toolkit/scripts/instruments.py",
)
assert SPEC is not None and SPEC.loader is not None
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def test_list_all_rows_exist(capsys):
    assert mod.main(["--repo", str(ROOT), "list"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["missing"] == [] and out["examined"] == len(mod.INSTRUMENTS)
    assert "drift-self-check" in {r["id"] for r in out["instruments"]}


def _row(rid, argv):
    return [{"id": rid, "answers": "?", "argv": argv, "source": "t"}]


def test_missing_instrument_exits_one(monkeypatch, capsys):
    monkeypatch.setattr(mod, "INSTRUMENTS", _row("x", ["python3", "nope/missing.py"]))
    assert mod.main(["--repo", str(ROOT), "list"]) == 1
    assert json.loads(capsys.readouterr().out)["missing"] == ["x"]


def test_unknown_id_exits_two():
    assert mod.main(["--repo", str(ROOT), "run", "no-such-id"]) == 2


def test_run_passes_child_exit_code(monkeypatch):
    monkeypatch.setattr(
        mod,
        "INSTRUMENTS",
        _row("seven", ["python3", "-c", "import sys; sys.exit(7)"]),
    )
    monkeypatch.setattr(mod, "_target", lambda argv: None)
    assert mod.main(["--repo", str(ROOT), "run", "seven"]) == 7


def test_unstartable_target_exits_three(monkeypatch):
    monkeypatch.setattr(mod, "INSTRUMENTS", _row("ghost", ["no-such-binary-xyz"]))
    monkeypatch.setattr(mod, "_target", lambda argv: None)
    assert mod.main(["--repo", str(ROOT), "run", "ghost"]) == 3
