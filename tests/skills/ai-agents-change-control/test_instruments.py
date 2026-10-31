"""Tests for the ai-agents-change-control instruments.py dispatcher."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / ".claude/skills/ai-agents-change-control/scripts/instruments.py"

spec = importlib.util.spec_from_file_location("instruments", SCRIPT)
assert spec is not None and spec.loader is not None
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def run(*args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True, cwd=cwd
    )


def test_ai_agents_change_control_list_rows_exist():
    r = run("--repo", str(ROOT), "list")
    out = json.loads(r.stdout)
    assert r.returncode == 0
    assert out["missing"] == [] and out["examined"] == len(mod.INSTRUMENTS)
    assert "drift-self-check" in {row["id"] for row in out["instruments"]}


def test_list_missing_row_exits_1(monkeypatch, capsys):
    monkeypatch.setattr(
        mod,
        "INSTRUMENTS",
        [{"id": "gone", "answers": "x", "argv": ["python3", "nope/missing.py"], "source": "s"}],
    )
    assert mod.main(["--repo", ".", "list"]) == 1
    assert json.loads(capsys.readouterr().out)["missing"] == ["gone"]


def test_run_unknown_id_exits_2():
    assert run("--repo", str(ROOT), "run", "no-such-id").returncode == 2


def test_run_passes_child_exit_code(monkeypatch):
    monkeypatch.setattr(
        mod,
        "INSTRUMENTS",
        [
            {
                "id": "seven",
                "answers": "x",
                "argv": ["python3", "-c", "import sys; sys.exit(7)"],
                "source": "s",
            }
        ],
    )
    assert mod.main(["--repo", ".", "run", "seven"]) == 7


def test_run_start_failure_exits_3(monkeypatch):
    monkeypatch.setattr(
        mod,
        "INSTRUMENTS",
        [{"id": "nx", "answers": "x", "argv": ["/no/such/binary"], "source": "s"}],
    )
    assert mod.main(["--repo", ".", "run", "nx"]) == 3
