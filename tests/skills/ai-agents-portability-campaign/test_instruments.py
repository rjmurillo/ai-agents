"""Tests for the ai-agents-portability-campaign instruments.py dispatcher."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = (
    ROOT / ".claude" / "skills" / "ai-agents-portability-campaign" / "scripts" / "instruments.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("pc_instruments", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ins = _load()


def test_list_all_rows_exist_at_head(capsys):
    code = ins.main(["--repo", str(ROOT), "list"])
    out = json.loads(capsys.readouterr().out)
    assert code == 0, out["missing"]
    assert out["skill"] == "ai-agents-portability-campaign"
    assert out["examined"] == len(out["instruments"])
    assert "drift-self-check" in {r["id"] for r in out["instruments"]}
    assert "event-map" in {r["id"] for r in out["instruments"]}


def test_list_missing_row_exits_1(monkeypatch, capsys):
    rows = [{"id": "ghost", "answers": "x", "argv": ["python3", "no/such.py"], "source": "s"}]
    monkeypatch.setattr(ins, "INSTRUMENTS", rows)
    assert ins.main(["--repo", str(ROOT), "list"]) == 1
    assert json.loads(capsys.readouterr().out)["missing"] == ["ghost"]


def test_run_unknown_id_exits_2():
    assert ins.main(["--repo", str(ROOT), "run", "nope"]) == 2


def test_run_passes_child_exit_code(monkeypatch):
    rows = [
        {
            "id": "seven",
            "answers": "x",
            "argv": ["python3", "-c", "import sys; sys.exit(7)"],
            "source": "s",
        }
    ]
    monkeypatch.setattr(ins, "INSTRUMENTS", rows)
    assert ins.main(["--repo", str(ROOT), "run", "seven"]) == 7


def test_run_forwards_args_after_double_dash(monkeypatch):
    rows = [
        {
            "id": "echo",
            "answers": "x",
            "argv": ["python3", "-c", "import sys; sys.exit(int(sys.argv[1]))"],
            "source": "s",
        }
    ]
    monkeypatch.setattr(ins, "INSTRUMENTS", rows)
    assert ins.main(["--repo", str(ROOT), "run", "echo", "--", "5"]) == 5


def test_run_unstartable_exits_3(monkeypatch):
    rows = [{"id": "bad", "answers": "x", "argv": ["definitely-not-a-binary-xyz"], "source": "s"}]
    monkeypatch.setattr(ins, "INSTRUMENTS", rows)
    assert ins.main(["--repo", str(ROOT), "run", "bad"]) == 3


def test_bad_repo_exits_2(tmp_path):
    assert ins.main(["--repo", str(tmp_path / "nope"), "list"]) == 2


def test_hook_counts_row_runs(capfd):
    assert ins.main(["--repo", str(ROOT), "run", "hook-counts"]) == 0
    assert '"examined": 3' in capfd.readouterr().out
