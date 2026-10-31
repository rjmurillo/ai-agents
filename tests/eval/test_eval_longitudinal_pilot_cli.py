"""Ceiling and CLI tests for the longitudinal pilot (issue #6993). No model is spawned."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

import pytest

EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

import _longitudinal_pilot as lp  # noqa: E402
import eval_longitudinal_pilot as cli  # noqa: E402

from tests.eval._longitudinal_test_support import (  # noqa: E402
    PILOT_PATH,
    fake_checkout,
    report_of,
    runs,
)


@pytest.fixture
def pilot() -> dict[str, Any]:
    return lp.load_pilot(PILOT_PATH)


# ---- ceiling ----


@pytest.mark.parametrize("value", [None, 0, -1, math.nan, math.inf, True, "5"])
def test_ledger_refuses_missing_or_bad_ceiling(value: Any) -> None:
    with pytest.raises(lp.PilotError):
        lp.Ledger(value, 0.25)


def test_ledger_refuses_reserve_above_ceiling_and_bad_max_calls() -> None:
    with pytest.raises(lp.PilotError):
        lp.Ledger(0.1, 0.25)
    with pytest.raises(lp.PilotError):
        lp.Ledger(1.0, 0.25, max_calls=0)


def test_execution_stops_at_ceiling_and_skips_the_rest(
    pilot: dict[str, Any], tmp_path: Path
) -> None:
    calls: list[str] = []

    def runner(
        condition: str, task: dict[str, Any], prompt: str, root: Path, model: str
    ) -> dict[str, Any]:
        calls.append(task["id"])
        return {**cli.scripted_runner(pilot)(condition, task, prompt, root, model), "cost_usd": 0.4}

    ledger = lp.Ledger(1.0, 0.3)
    records, _ = runs(pilot, tmp_path, runner, ledger)
    assert len(calls) == 2  # 0.4 + 0.4 = 0.8; 0.8 + 0.3 > 1.0
    assert sum(1 for r in records if r.get("skipped") == "ceiling") == 8
    assert ledger.spent_usd <= 1.0 and "crossed" in (ledger.stopped_reason or "")
    report = report_of(pilot, records, ledger)
    assert report["complete"] is False and report["verdict"] == "inconclusive_incomplete"
    assert report["ceiling"]["calls"] == 2


def test_unreported_cost_is_booked_at_the_reserve(pilot: dict[str, Any], tmp_path: Path) -> None:
    ledger = lp.Ledger(0.5, 0.25)
    runs(pilot, tmp_path, cli.scripted_runner(pilot), ledger)
    assert ledger.calls == 2 and ledger.spent_usd == 0.5


def test_max_calls_stops_independent_of_dollars(pilot: dict[str, Any], tmp_path: Path) -> None:
    ledger = lp.Ledger(100.0, 0.25, max_calls=3)
    records, _ = runs(pilot, tmp_path, cli.scripted_runner(pilot), ledger)
    assert ledger.calls == 3 and "max_calls" in (ledger.stopped_reason or "")
    assert sum(1 for r in records if r.get("skipped")) == 7


# ---- CLI ----


def test_live_refuses_without_ceiling(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["live", "--checkout-pre", "a", "--checkout-post", "b", "--out-dir", "o"])
    assert exc.value.code == 2
    assert "--ceiling-usd" in capsys.readouterr().err


@pytest.mark.parametrize("ceiling", ["0", "-3", "nan", "inf"])
def test_live_refuses_bad_ceiling_before_any_spawn(
    ceiling: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def boom(*a: Any, **k: Any) -> Any:
        raise AssertionError("a model call was attempted")

    monkeypatch.setattr(cli, "live_runner", boom)
    monkeypatch.setattr(cli.cap, "run_one", boom)
    rc = cli.main(
        [
            "live",
            "--checkout-pre",
            str(tmp_path),
            "--checkout-post",
            str(tmp_path),
            "--ceiling-usd",
            ceiling,
            "--out-dir",
            str(tmp_path / "o"),
        ]
    )
    assert rc == 2


def test_live_refuses_when_gold_does_not_match_checkout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/usr/bin/claude")
    monkeypatch.setattr(
        cli.cap, "run_one", lambda *a, **k: (_ for _ in ()).throw(AssertionError("spawned"))
    )
    (tmp_path / "scripts" / "eval").mkdir(parents=True)
    rc = cli.main(
        [
            "live",
            "--checkout-pre",
            str(tmp_path),
            "--checkout-post",
            str(tmp_path),
            "--ceiling-usd",
            "1",
            "--out-dir",
            str(tmp_path / "o"),
        ]
    )
    assert rc == 2 and "no spend started" in capsys.readouterr().err


def test_live_missing_claude_cli_is_external(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)
    rc = cli.main(
        [
            "live",
            "--checkout-pre",
            str(tmp_path),
            "--checkout-post",
            str(tmp_path),
            "--ceiling-usd",
            "1",
            "--out-dir",
            str(tmp_path / "o"),
        ]
    )
    assert rc == 3


def test_live_end_to_end_with_stubbed_runner_stops_at_ceiling(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pilot = lp.load_pilot(PILOT_PATH)
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/usr/bin/claude")
    monkeypatch.setattr(cli, "_verify_gold", lambda *a, **k: [])
    monkeypatch.setattr(
        cli.subprocess, "run", lambda *a, **k: type("P", (), {"stdout": "9.9.9", "returncode": 0})()
    )
    scripted = cli.scripted_runner(pilot)
    monkeypatch.setattr(
        cli,
        "live_runner",
        lambda c, t, p, r, m: {**scripted(c, t, p, r, m), "cost_usd": 0.5, "wall_s": 1.0},
    )
    root = fake_checkout(tmp_path / "repo", pilot)
    rc = cli.main(
        [
            "live",
            "--checkout-pre",
            str(root),
            "--checkout-post",
            str(root),
            "--ceiling-usd",
            "1.2",
            "--reserve-usd",
            "0.3",
            "--out-dir",
            str(tmp_path / "out"),
        ]
    )
    report = json.loads((tmp_path / "out" / "report.json").read_text())
    assert rc == 0 and report["mode"] == "live" and report["complete"] is False
    assert (
        report["ceiling"]["spent_usd"] <= 1.2 and report["config"]["harness"] == "claude-cli 9.9.9"
    )
    capsys.readouterr()


def test_dry_run_cli_writes_report_with_config(tmp_path: Path) -> None:
    rc = cli.main(["dry-run", "--out-dir", str(tmp_path), "--reps", "2"])
    report = json.loads((tmp_path / "report.json").read_text())
    assert rc == 0 and report["mode"] == "dry_run" and report["config"]["reps"] == 2
    for key in ("model", "harness", "template_revision", "local_context_revision"):
        assert report["config"][key]
    assert (tmp_path / "records.jsonl").read_text().count("\n") == 20


def test_minutes_file_rows_must_match_a_planned_cell(tmp_path: Path) -> None:
    path = tmp_path / "m.json"
    path.write_text(
        json.dumps([{"control": "local_context", "task_id": "T9", "repeat": 0, "minutes": 1}])
    )
    assert cli.main(["dry-run", "--out-dir", str(tmp_path / "o"), "--minutes", str(path)]) == 2
    path.write_text(
        json.dumps([{"control": "local_context", "task_id": "T1-seed", "repeat": 0, "minutes": 0}])
    )
    assert cli.main(["dry-run", "--out-dir", str(tmp_path / "o"), "--minutes", str(path)]) == 0
    report = json.loads((tmp_path / "o" / "report.json").read_text())
    assert report["conditions"]["local_context"]["human_active_correction_minutes"]["total"] == 0.0


def test_estimate_prints_range_and_basis(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["estimate", "--reps", "3"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert (
        out["calls"] == 30
        and out["total_usd"]["low"] <= out["total_usd"]["mid"] <= out["total_usd"]["high"]
    )
    assert "SKILL-AUTHORING" in out["pricing_basis"]


def test_verify_gold_cli_exit_codes(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    (tmp_path / "scripts" / "eval").mkdir(parents=True)
    assert cli.main(["verify-gold", "--checkout", str(tmp_path), "--phase", "pre"]) == 1
    capsys.readouterr()


def test_prepare_post_renames_in_a_git_checkout(pilot: dict[str, Any], tmp_path: Path) -> None:
    import subprocess

    old, new = pilot["repo_change"]["rename"]
    (tmp_path / old).parent.mkdir(parents=True)
    (tmp_path / old).write_text("x", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    assert cli.main(["prepare-post", "--checkout", str(tmp_path)]) == 0
    assert (tmp_path / new).is_file() and not (tmp_path / old).exists()
    assert cli.main(["prepare-post", "--checkout", str(tmp_path)]) == 2
