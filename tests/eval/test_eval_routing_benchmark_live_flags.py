# ruff: noqa: F811
"""Live-run flags of scripts/eval/eval_routing_benchmark.py (issue #5424).

Budget, repetitions, `--arms`, and `--real-home`, driven through `main(argv)` with the
scripted stand-in for the live backend. The fixtures live in the sibling CLI test module.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.eval._routing_runner_test_support import cli, config_dict
from tests.eval.test_eval_routing_benchmark_cli import (  # noqa: F401
    ScriptedLive,
    _live_args,
    _no_ambient_credentials,
    scripted_live,
    small_config,
    verified,
)


def test_live_requires_an_invocation_budget(
    verified: Path,
    small_config: Path,
    tmp_path: Path,
    scripted_live: type[ScriptedLive],
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "results.jsonl"
    args = _live_args(verified, small_config, output)
    without = args[:1] + args[3:]

    assert cli.main(without) == cli.EXIT_CONFIG
    assert "--max-invocations" in capsys.readouterr().err
    assert cli.main([*args[:2], "0", *args[3:]]) == cli.EXIT_CONFIG
    assert scripted_live.created == [] and not output.exists()


@pytest.mark.parametrize(
    "flag", [["--real-home"], ["--max-invocations", "5"], ["--repetitions", "2"]]
)
def test_live_only_flags_are_refused_without_live(flag: list[str], capsys: Any) -> None:
    assert cli.main(flag) == cli.EXIT_CONFIG
    assert "need --live" in capsys.readouterr().err


def test_real_home_opens_the_gate_for_a_codex_only_plan(
    verified: Path,
    tmp_path: Path,
    scripted_live: type[ScriptedLive],
) -> None:
    document = config_dict()
    document["harnesses"] = [h for h in document["harnesses"] if h["harness"] == "codex"]
    document["strategies"] = [s for s in document["strategies"] if s["arm"] == "E"]
    config = tmp_path / "codex-only.json"
    config.write_text(json.dumps(document), encoding="utf-8")
    output = tmp_path / "results.jsonl"
    args = ["--live", "--real-home", "--max-invocations", "100", "--output", str(output)]

    exit_code = cli.main([*args, "--matrix", str(verified), "--config", str(config)])

    lines = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert exit_code == cli.EXIT_OK and lines
    assert all(item["ambient_home"]["codex_home"] == "real" for item in lines)
    assert all(kw.get("real_home") is True for kw in scripted_live.kwargs)


def test_the_budget_cuts_the_run_and_every_later_row_is_not_run(
    verified: Path,
    small_config: Path,
    tmp_path: Path,
    scripted_live: type[ScriptedLive],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODEX_API_KEY", "a")
    monkeypatch.setenv("GH_TOKEN", "b")
    output = tmp_path / "results.jsonl"
    args = _live_args(verified, small_config, output)
    args[2] = "5"

    exit_code = cli.main(args)

    lines = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    ran = [line for line in lines if line["status"] != "NOT_RUN"]
    cut = [line for line in lines if line["status"] == "NOT_RUN"]
    assert exit_code == cli.EXIT_OK and len(lines) == 2 * 6 * 2
    assert ran and cut and lines.index(cut[0]) == len(ran)
    assert "mid-row" in cut[0]["reason"] and {c["reason"] for c in cut[1:]} == {
        "invocation budget spent"
    }
    assert all("repetition" in line for line in lines)


def test_repetitions_run_the_whole_plan_per_pass_with_the_repetition_outermost(
    verified: Path,
    small_config: Path,
    tmp_path: Path,
    scripted_live: type[ScriptedLive],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODEX_API_KEY", "a")
    monkeypatch.setenv("GH_TOKEN", "b")
    output = tmp_path / "results.jsonl"

    exit_code = cli.main([*_live_args(verified, small_config, output), "--repetitions", "2"])

    lines = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    reps = [line["repetition"] for line in lines]
    assert exit_code == cli.EXIT_OK and len(lines) == 2 * 6 * 2 * 2
    assert reps == sorted(reps) and set(reps) == {1, 2}


def test_arms_runs_only_the_named_arms_but_validates_the_whole_config(
    verified: Path,
    small_config: Path,
    tmp_path: Path,
    scripted_live: type[ScriptedLive],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODEX_API_KEY", "a")
    monkeypatch.setenv("GH_TOKEN", "b")
    output = tmp_path / "results.jsonl"

    exit_code = cli.main([*_live_args(verified, small_config, output), "--arms", "e"])

    lines = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert exit_code == cli.EXIT_OK and len(lines) == 2 * 6
    assert {line["arm"] for line in lines} == {"E"}


def test_arms_that_select_nothing_do_not_spend(
    verified: Path,
    small_config: Path,
    tmp_path: Path,
    scripted_live: type[ScriptedLive],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("CODEX_API_KEY", "a")
    monkeypatch.setenv("GH_TOKEN", "b")
    output = tmp_path / "results.jsonl"

    exit_code = cli.main([*_live_args(verified, small_config, output), "--arms", "Z"])

    assert exit_code == cli.EXIT_NOTHING_PLANNED
    assert "selects no planned row" in capsys.readouterr().err
    assert scripted_live.created == [] and not output.exists()
