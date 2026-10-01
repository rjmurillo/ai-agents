"""Tests for scripts/eval/eval_durable_live.py (issue #5768). No real claude is started."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.eval._durable_live_test_support import CORPUS, EVAL_DIR, cli, fake_runner, live_mod, load

SCRIPT = EVAL_DIR / "eval_durable_live.py"


def _out(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    return json.loads(capsys.readouterr().out)


def test_dry_run_exits_0_prints_plan_and_launches_nothing(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("dry run must not launch a process")

    monkeypatch.setattr(cli, "run_experiment", forbidden)
    assert cli.main([]) == cli.EXIT_OK
    plan = _out(capsys)
    assert plan["model_calls"] == 0 and plan["mode"] == "dry-run"
    assert plan["max_invocations"] == 24 and plan["within_cap"] is True
    assert plan["controls"]["current"]["bytes"] > plan["controls"]["reduced"]["bytes"]


def test_dry_run_reports_when_the_bound_exceeds_the_cap(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["--max-invocations", "10"]) == cli.EXIT_OK
    assert _out(capsys)["within_cap"] is False


@pytest.mark.parametrize(
    "argv",
    [
        ["--live"],
        ["--output-dir", "x"],
        ["--max-turns", "0"],
        ["--repeats", "0"],
        ["--max-invocations", "0"],
        ["--retry-budget", "-1"],
    ],
)
def test_invalid_arguments_exit_2(argv: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(argv) == cli.EXIT_CONFIG
    assert capsys.readouterr().err.startswith("error:")


def test_missing_corpus_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["--corpus", str(tmp_path / "absent")]) == cli.EXIT_CONFIG
    assert "error:" in capsys.readouterr().err


def test_missing_control_file_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["--repo-root", str(tmp_path)]) == cli.EXIT_CONFIG
    assert "not found" in capsys.readouterr().err


def test_live_without_stored_login_exits_4_before_any_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "run_experiment", lambda *a, **k: pytest.fail("launched"))
    assert cli.main(["--live", "--output-dir", str(tmp_path)]) == cli.EXIT_AUTH


def test_live_without_claude_on_path_exits_4(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli.shutil, "which", lambda _name: None)
    argv = ["--live", "--use-stored-login", "--output-dir", str(tmp_path)]
    assert cli.main(argv) == cli.EXIT_AUTH


def _fake_live(monkeypatch: pytest.MonkeyPatch, tasks: list[str], **runner_kwargs: Any) -> Any:
    scenarios = [load(t) for t in tasks]
    runner = fake_runner(scenarios[0], ["known_good"], **runner_kwargs)
    real = cli.run_experiment
    monkeypatch.setattr(cli.shutil, "which", lambda _name: "/fake/claude")
    monkeypatch.setattr(cli, "load_corpus", lambda _root: scenarios)
    monkeypatch.setattr(cli, "run_experiment", lambda *a, **k: real(*a, runner=runner, **k))
    return runner


def test_live_run_writes_records_reports_comparison_and_labels_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = _fake_live(monkeypatch, ["RB-01-bounded-implementation"])
    argv = ["--live", "--use-stored-login", "--output-dir", str(tmp_path)]
    code = cli.main(argv)
    summary = _out(capsys)
    assert code in (cli.EXIT_OK, cli.EXIT_UNVERIFIED_OR_WORSE)
    assert summary["harness_scope"] == "claude only, not cross-harness"
    assert summary["effort_verified"] is False
    assert summary["launches"] == len(runner.calls) == 2
    for name in ("current.jsonl", "reduced.jsonl", "invocations.jsonl", "comparison.json"):
        assert (tmp_path / name).is_file(), name
    row = json.loads((tmp_path / "current.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert row["config"]["control"] == "current" and row["config"]["harness"] == "claude"
    assert json.loads((tmp_path / "run-summary.json").read_text(encoding="utf-8"))["launches"] == 2


def test_harness_failure_exits_3_and_comparison_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _fake_live(monkeypatch, ["RB-01-bounded-implementation"], returncodes=[1])
    argv = ["--live", "--use-stored-login", "--output-dir", str(tmp_path)]
    assert cli.main(argv) == cli.EXIT_HARNESS_FAILURE
    summary = _out(capsys)
    assert summary["comparison"].startswith("refused:")
    assert len(summary["harness_failures"]) == 2
    assert not (tmp_path / "comparison.json").exists()


def test_invocation_cap_stops_the_run_with_exit_3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = _fake_live(monkeypatch, ["RB-01-bounded-implementation"], returncodes=[0])
    argv = ["--live", "--use-stored-login", "--output-dir", str(tmp_path), "--max-invocations", "1"]
    assert cli.main(argv) == cli.EXIT_HARNESS_FAILURE
    assert "cap 1" in capsys.readouterr().err
    assert len(runner.calls) == 1


def test_script_dry_run_as_a_real_process() -> None:
    done = subprocess.run(
        [sys.executable, str(SCRIPT), "--corpus", str(CORPUS)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert done.returncode == 0
    assert json.loads(done.stdout)["model_calls"] == 0


def test_control_names_match_the_module() -> None:
    assert cli.BASELINE_CONTROL in live_mod.CONTROLS and cli.CANDIDATE_CONTROL in live_mod.CONTROLS


def test_tasks_and_controls_filters_narrow_the_dry_run(
    capsys: pytest.CaptureFixture[str],
) -> None:
    argv = [
        "--tasks",
        "RB-01-bounded-implementation, RB-04-scope-expansion",
        "--controls",
        "reduced",
    ]
    assert cli.main(argv) == cli.EXIT_OK
    plan = _out(capsys)
    assert plan["tasks"] == ["RB-01-bounded-implementation", "RB-04-scope-expansion"]
    assert list(plan["controls"]) == ["reduced"] and plan["max_invocations"] == 4


@pytest.mark.parametrize(
    "argv",
    [["--tasks", "RB-99"], ["--tasks", " , "], ["--controls", "none"], ["--controls", ","]],
)
def test_unknown_or_empty_filters_exit_2(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(argv) == cli.EXIT_CONFIG
    assert "names no known" in capsys.readouterr().err


def test_single_control_live_run_skips_the_comparison(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _fake_live(monkeypatch, ["RB-01-bounded-implementation"])
    argv = ["--live", "--use-stored-login", "--output-dir", str(tmp_path), "--controls", "reduced"]
    assert cli.main(argv) == cli.EXIT_OK
    assert _out(capsys)["comparison"].startswith("not run")
    assert (tmp_path / "reduced.jsonl").is_file() and not (tmp_path / "comparison.json").exists()
