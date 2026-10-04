"""Tests for scripts/eval/eval_routing_benchmark.py (issue #5424).

Drives `main(argv)` and the process boundary, asserting on exit codes, the
printed JSON, and what the live gate let through, per testing.md MUST-8.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.eval._routing_runner_test_support import (
    CORPUS,
    EVAL_DIR,
    REAL_MATRIX,
    backend_mod,
    cap,
    cli,
    config_dict,
    make_record,
    matched_records,
    result_mod,
    write_matrix,
)

CREDENTIALS = (
    "CODEX_API_KEY",
    "CODEX_ACCESS_TOKEN",
    "COPILOT_GITHUB_TOKEN",
    "GH_TOKEN",
    "GITHUB_TOKEN",
)
SCRIPT = EVAL_DIR / "eval_routing_benchmark.py"


@pytest.fixture(autouse=True)
def _no_ambient_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in CREDENTIALS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def verified(tmp_path: Path) -> Path:
    return write_matrix(tmp_path / "matrix.json", matched_records())


@pytest.fixture
def small_config(tmp_path: Path) -> Path:
    """Arms E and F only, so a scripted live run stays fast."""
    document = config_dict()
    document["strategies"] = [s for s in document["strategies"] if s["arm"] in {"E", "F"}]
    path = tmp_path / "config.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


class ScriptedLive:
    """Stands in for `LiveBackend`: a context manager over the scripted fake."""

    created: list[str] = []
    script = backend_mod.Script()

    kwargs: list[dict[str, Any]] = []

    def __init__(self, harness: str, **kwargs: Any) -> None:
        type(self).created.append(harness)
        type(self).kwargs.append(kwargs)
        self._budget = kwargs.get("budget")
        self._inner = backend_mod.ScriptedBackend(default=type(self).script)

    def __enter__(self) -> ScriptedLive:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def invoke(self, request: Any, scenario: Any) -> Any:
        if self._budget is not None:
            self._budget.take()
        return self._inner.invoke(request, scenario)

    def grade(self, scenario: Any, round_index: int) -> Any:
        return self._inner.grade(scenario, round_index)


@pytest.fixture
def scripted_live(monkeypatch: pytest.MonkeyPatch) -> type[ScriptedLive]:
    ScriptedLive.created = []
    ScriptedLive.kwargs = []
    ScriptedLive.script = backend_mod.Script()
    monkeypatch.setattr(cli, "LiveBackend", ScriptedLive)
    return ScriptedLive


def _forbid_processes(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("a process was started")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)


def test_dry_run_expands_the_matrix_with_zero_model_calls(
    verified: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _forbid_processes(monkeypatch)

    exit_code = cli.main(["--matrix", str(verified)])

    report = json.loads(capsys.readouterr().out)
    assert exit_code == cli.EXIT_OK
    assert report["mode"] == "dry-run" and report["model_calls"] == 0
    assert report["examined"] == report["planned"] == 6 * 6 * 2 and report["rejected"] == 0
    assert report["by_eligibility"] == {"ELIGIBLE_MATCHED": 72}
    assert len(report["matched_pairs"]) == 36 and report["problems"] == []
    row = report["rows"][0]
    assert {"scenario_id", "arm", "harness", "harness_version", "eligibility", "status"} <= set(row)
    assert row["harness_comparison"] == "matched" and row["pair_id"]


def test_dry_run_lists_unmatched_and_rejected_combinations_before_spend(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    records = [make_record("codex", concurrency=3), make_record("copilot", concurrency=2)]
    records[1] = make_record(
        "copilot", concurrency=2, statuses={"reviewer_isolation": cap.CapabilityStatus.UNSUPPORTED}
    )

    exit_code = cli.main(["--matrix", str(write_matrix(tmp_path / "m.json", records))])

    report = json.loads(capsys.readouterr().out)
    by_arm: dict[str, set[str]] = {}
    for row in report["rows"]:
        by_arm.setdefault(row["arm"], set()).add(f"{row['status']}/{row['harness_comparison']}")
    assert exit_code == cli.EXIT_OK
    assert by_arm["A"] == {"PLANNED/unmatched"}
    assert by_arm["B"] == {"REJECTED/none"}
    assert report["by_eligibility"]["UNSUPPORTED"] > 0
    assert report["by_eligibility"]["ELIGIBLE_UNMATCHED"] > 0


def test_checked_in_matrix_plans_only_what_it_classifies_eligible(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = cli.main([])

    report = json.loads(capsys.readouterr().out)
    eligible = {"ELIGIBLE_MATCHED", "ELIGIBLE_UNMATCHED"}
    assert report["examined"] == 72 and report["model_calls"] == 0
    assert report["planned"] == sum(1 for r in report["rows"] if r["eligibility"] in eligible)
    assert exit_code == (cli.EXIT_OK if report["planned"] else cli.EXIT_NOTHING_PLANNED)


def test_exit_1_when_nothing_is_plannable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    unverified = {
        "model_override": cap.CapabilityStatus.UNVERIFIED,
        "subagent_support": cap.CapabilityStatus.UNVERIFIED,
    }
    records = [
        make_record("codex", statuses=unverified),
        make_record("copilot", statuses=unverified),
    ]

    exit_code = cli.main(["--matrix", str(write_matrix(tmp_path / "m.json", records))])

    report = json.loads(capsys.readouterr().out)
    assert exit_code == cli.EXIT_NOTHING_PLANNED
    assert report["planned"] == 0 and report["by_eligibility"] == {"UNVERIFIED": 72}


def test_exit_1_when_the_config_names_a_harness_the_matrix_does_not_classify(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    matrix = write_matrix(tmp_path / "m.json", [make_record("codex")])

    exit_code = cli.main(["--matrix", str(matrix)])

    report = json.loads(capsys.readouterr().out)
    assert exit_code == cli.EXIT_NOTHING_PLANNED
    assert report["problems"] == ["harness 'copilot' is not classified by the capability matrix"]


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["--config", "{tmp}/absent.json"], "cannot read"),
        (["--matrix", "{tmp}/absent.json"], "could not read matrix"),
        (["--corpus", "{tmp}/absent"], "not a directory"),
        (["--live"], "--live requires --output"),
        (["--output", "{tmp}/out.jsonl"], "only valid with --live"),
    ],
)
def test_exit_2_on_invalid_inputs_or_arguments(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], argv: list[str], message: str
) -> None:
    exit_code = cli.main([part.replace("{tmp}", str(tmp_path)) for part in argv])

    captured = capsys.readouterr()
    assert exit_code == cli.EXIT_CONFIG
    assert message in captured.err and captured.out == ""


def test_exit_2_on_a_config_that_breaks_an_arm_invariant(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    document = config_dict()
    next(s for s in document["strategies"] if s["arm"] == "B").pop("reviewer")
    path = tmp_path / "config.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    exit_code = cli.main(["--config", str(path)])

    assert exit_code == cli.EXIT_CONFIG
    assert "isolated reviewer" in capsys.readouterr().err


def test_exit_2_on_a_corpus_missing_a_category(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    corpus = tmp_path / "corpus"
    shutil.copytree(CORPUS, corpus)
    shutil.rmtree(corpus / "RB-04-scope-expansion")

    exit_code = cli.main(["--corpus", str(corpus)])

    assert exit_code == cli.EXIT_CONFIG
    assert "scope_expansion" in capsys.readouterr().err


def test_live_without_credentials_fails_closed_before_anything_starts(
    verified: Path,
    small_config: Path,
    tmp_path: Path,
    scripted_live: type[ScriptedLive],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _forbid_processes(monkeypatch)
    output = tmp_path / "results.jsonl"

    exit_code = cli.main(
        [
            "--live",
            "--max-invocations",
            "1000",
            "--output",
            str(output),
            "--matrix",
            str(verified),
            "--config",
            str(small_config),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == cli.EXIT_AUTH
    assert "no credential for" in captured.err and captured.out == ""
    assert scripted_live.created == [] and not output.exists()


def test_live_with_a_credential_for_only_one_harness_still_refuses(
    verified: Path,
    small_config: Path,
    tmp_path: Path,
    scripted_live: type[ScriptedLive],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODEX_API_KEY", "credential")
    output = tmp_path / "results.jsonl"

    exit_code = cli.main(
        [
            "--live",
            "--max-invocations",
            "1000",
            "--output",
            str(output),
            "--matrix",
            str(verified),
            "--config",
            str(small_config),
        ]
    )

    assert exit_code == cli.EXIT_AUTH
    assert scripted_live.created == [] and not output.exists()


def test_live_with_credentials_but_nothing_plannable_does_not_spend(
    tmp_path: Path, scripted_live: type[ScriptedLive], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CODEX_API_KEY", "a")
    monkeypatch.setenv("GH_TOKEN", "b")
    output = tmp_path / "results.jsonl"
    unverified = {
        "model_override": cap.CapabilityStatus.UNVERIFIED,
        "subagent_support": cap.CapabilityStatus.UNVERIFIED,
    }
    records = [
        make_record("codex", statuses=unverified),
        make_record("copilot", statuses=unverified),
    ]
    matrix = write_matrix(tmp_path / "m.json", records)

    exit_code = cli.main(
        ["--live", "--max-invocations", "10", "--output", str(output), "--matrix", str(matrix)]
    )

    assert exit_code == cli.EXIT_NOTHING_PLANNED
    assert scripted_live.created == [] and not output.exists()


def _live_args(verified: Path, small_config: Path, output: Path) -> list[str]:
    return [
        "--live",
        "--max-invocations",
        "1000",
        "--output",
        str(output),
        "--matrix",
        str(verified),
        "--config",
        str(small_config),
    ]


def test_authorized_live_run_writes_one_result_per_planned_row(
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

    exit_code = cli.main(_live_args(verified, small_config, output))

    lines = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert exit_code == cli.EXIT_OK and capsys.readouterr().out == ""
    assert len(lines) == 2 * 6 * 2
    assert len(scripted_live.created) == len(lines)
    assert sorted(set(scripted_live.created)) == ["codex", "copilot"]
    assert {line["harness"]["name"] for line in lines} == {"codex", "copilot"}
    assert all(line["status"] == "ACCEPTED" and line["harness"]["version"] for line in lines)


def test_a_harness_failure_in_a_live_run_exits_3_and_still_persists_results(
    verified: Path,
    small_config: Path,
    tmp_path: Path,
    scripted_live: type[ScriptedLive],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODEX_API_KEY", "a")
    monkeypatch.setenv("GH_TOKEN", "b")
    down = {"failure": result_mod.FailureKind.HARNESS, "failure_detail": "exit code 1"}
    scripted_live.script = backend_mod.Script(overrides={"role:orchestrator": down})
    output = tmp_path / "results.jsonl"

    exit_code = cli.main(_live_args(verified, small_config, output))

    lines = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert exit_code == cli.EXIT_HARNESS_FAILURE
    assert {line["status"] for line in lines} == {"HARNESS_FAILED"}
    assert all(line["validation"] is None for line in lines)


def test_script_runs_as_a_process_and_prints_the_dry_run_report() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--matrix", str(REAL_MATRIX)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=120,
    )

    report = json.loads(completed.stdout)
    assert completed.returncode in {cli.EXIT_OK, cli.EXIT_NOTHING_PLANNED}
    assert report["mode"] == "dry-run" and report["model_calls"] == 0


def test_plan_report_omits_model_calls_outside_dry_run() -> None:
    from tests.eval._routing_runner_test_support import plan_mod

    empty = plan_mod.Plan((), ())

    assert "model_calls" not in cli.plan_report(empty, "live")
    assert cli.plan_report(empty, "dry-run")["model_calls"] == 0


# --- Budget, repetitions, and real home (issue #5424 live) ------------------------


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
