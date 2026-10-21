# ruff: noqa: F811
"""Harness version gate of scripts/eval/eval_routing_benchmark.py (issue #5426).

A live run reads `<cli> --version` for each planned harness before it spends and
again before every row, and refuses when the installed CLI is not the matrix pin.
Driven through `main(argv)` with a fake probe; `installed_version` and
`require_pinned_versions` are tested against a fake process runner.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from tests.eval._routing_runner_test_support import (
    CODEX_VERSION,
    COPILOT_VERSION,
    backend_mod,
    cli,
    live_mod,
    result_mod,
)
from tests.eval.test_eval_routing_benchmark_cli import (  # noqa: F401
    PINS,
    ScriptedLive,
    _installed_matches_pin,
    _live_args,
    _no_ambient_credentials,
    scripted_live,
    small_config,
    verified,
)

DRIFTED = "codex-cli 0.164.0"
ROWS = 2 * 6 * 2


@pytest.fixture(autouse=True)
def _credentials(monkeypatch: pytest.MonkeyPatch, _no_ambient_credentials: None) -> None:
    monkeypatch.setenv("CODEX_API_KEY", "a")
    monkeypatch.setenv("GH_TOKEN", "b")


class Probe:
    """Records each probed harness and answers from `answer(harness, call_index)`."""

    def __init__(self, answer: Callable[[str, int], str]) -> None:
        self.calls: list[str] = []
        self._answer = answer

    def __call__(self, harness: str) -> str:
        self.calls.append(harness)
        return self._answer(harness, len(self.calls))


def _install(monkeypatch: pytest.MonkeyPatch, answer: Callable[[str, int], str]) -> Probe:
    probe = Probe(answer)
    monkeypatch.setattr(cli, "installed_version", probe)
    return probe


def _codex_drifts_after(calls: int) -> Callable[[str, int], str]:
    def answer(harness: str, index: int) -> str:
        if harness == "codex" and index > calls:
            return DRIFTED
        return PINS[harness]

    return answer


def _probe_fails_after(calls: int) -> Callable[[str, int], str]:
    def answer(harness: str, index: int) -> str:
        if index > calls:
            raise live_mod.VersionProbeError(f"{harness} version probe failed: gone")
        return PINS[harness]

    return answer


def _lines(output: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]


# --- before the run --------------------------------------------------------


def test_drift_before_the_run_exits_2_names_both_versions_and_writes_nothing(
    verified: Path,
    small_config: Path,
    tmp_path: Path,
    scripted_live: type[ScriptedLive],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _install(monkeypatch, _codex_drifts_after(0))
    output = tmp_path / "results.jsonl"

    exit_code = cli.main(_live_args(verified, small_config, output))

    err = capsys.readouterr().err
    assert exit_code == cli.EXIT_CONFIG
    assert DRIFTED in err and CODEX_VERSION in err and "re-pin" in err
    assert scripted_live.created == [] and not output.exists()


def test_one_drifted_harness_in_a_mixed_plan_still_refuses_the_whole_run(
    verified: Path,
    small_config: Path,
    tmp_path: Path,
    scripted_live: type[ScriptedLive],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def copilot_drifts(harness: str, index: int) -> str:
        return "GitHub Copilot CLI 1.0.90." if harness == "copilot" else PINS[harness]

    probe = _install(monkeypatch, copilot_drifts)
    output = tmp_path / "results.jsonl"

    exit_code = cli.main(_live_args(verified, small_config, output))

    err = capsys.readouterr().err
    assert exit_code == cli.EXIT_CONFIG and COPILOT_VERSION in err and "codex" not in err
    assert sorted(probe.calls) == ["codex", "copilot"]
    assert scripted_live.created == [] and not output.exists()


def test_an_unreadable_version_before_the_run_exits_3_and_writes_nothing(
    verified: Path,
    small_config: Path,
    tmp_path: Path,
    scripted_live: type[ScriptedLive],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _install(monkeypatch, _probe_fails_after(0))
    output = tmp_path / "results.jsonl"

    exit_code = cli.main(_live_args(verified, small_config, output))

    assert exit_code == cli.EXIT_HARNESS_FAILURE
    assert "version probe failed" in capsys.readouterr().err
    assert scripted_live.created == [] and not output.exists()


def test_arms_narrow_the_probe_to_the_harnesses_still_planned(
    verified: Path,
    tmp_path: Path,
    scripted_live: type[ScriptedLive],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.eval._routing_runner_test_support import config_dict

    document = config_dict()
    document["harnesses"] = [h for h in document["harnesses"] if h["harness"] == "codex"]
    config = tmp_path / "codex-only.json"
    config.write_text(json.dumps(document), encoding="utf-8")
    probe = _install(monkeypatch, _codex_drifts_after(10_000))
    output = tmp_path / "results.jsonl"
    args = ["--live", "--max-invocations", "1000", "--output", str(output), "--arms", "E"]

    exit_code = cli.main([*args, "--matrix", str(verified), "--config", str(config)])

    assert exit_code == cli.EXIT_OK
    assert set(probe.calls) == {"codex"}
    assert {line["arm"] for line in _lines(output)} == {"E"}


def test_no_probe_runs_when_the_credential_gate_refuses(
    verified: Path,
    small_config: Path,
    tmp_path: Path,
    scripted_live: type[ScriptedLive],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CODEX_API_KEY")
    monkeypatch.delenv("GH_TOKEN")
    probe = _install(monkeypatch, _codex_drifts_after(0))

    exit_code = cli.main(_live_args(verified, small_config, tmp_path / "results.jsonl"))

    assert exit_code == cli.EXIT_AUTH and probe.calls == []


# --- during the run --------------------------------------------------------


def test_matching_versions_probe_once_per_harness_then_once_per_row(
    verified: Path,
    small_config: Path,
    tmp_path: Path,
    scripted_live: type[ScriptedLive],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe = _install(monkeypatch, _codex_drifts_after(10_000))
    output = tmp_path / "results.jsonl"

    exit_code = cli.main(_live_args(verified, small_config, output))

    lines = _lines(output)
    assert exit_code == cli.EXIT_OK and len(lines) == ROWS
    assert len(probe.calls) == 2 + ROWS
    assert probe.calls[2:] == [line["harness"]["name"] for line in lines]


def test_drift_mid_run_writes_that_row_and_every_later_row_not_run_and_exits_2(
    verified: Path,
    small_config: Path,
    tmp_path: Path,
    scripted_live: type[ScriptedLive],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe = _install(monkeypatch, _codex_drifts_after(5))
    output = tmp_path / "results.jsonl"

    exit_code = cli.main(_live_args(verified, small_config, output))

    lines = _lines(output)
    cut = [line for line in lines if line["status"] == "NOT_RUN"]
    ran = [line for line in lines if line["status"] != "NOT_RUN"]
    assert exit_code == cli.EXIT_CONFIG and len(lines) == ROWS
    assert ran and cut and lines.index(cut[0]) == len(ran)
    assert all(DRIFTED in line["reason"] for line in cut)
    assert len(scripted_live.created) == len(ran)
    assert len(probe.calls) == 2 + len(ran) + 1


def test_probe_failure_mid_run_writes_not_run_rows_and_exits_3(
    verified: Path,
    small_config: Path,
    tmp_path: Path,
    scripted_live: type[ScriptedLive],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(monkeypatch, _probe_fails_after(4))
    output = tmp_path / "results.jsonl"

    exit_code = cli.main(_live_args(verified, small_config, output))

    cut = [line for line in _lines(output) if line["status"] == "NOT_RUN"]
    assert exit_code == cli.EXIT_HARNESS_FAILURE
    assert cut and all("version probe failed" in line["reason"] for line in cut)


def test_a_drift_stop_exit_code_wins_over_an_earlier_row_failure(
    verified: Path,
    small_config: Path,
    tmp_path: Path,
    scripted_live: type[ScriptedLive],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    down = {"failure": result_mod.FailureKind.HARNESS, "failure_detail": "exit code 1"}
    scripted_live.script = backend_mod.Script(overrides={"role:orchestrator": down})
    _install(monkeypatch, _codex_drifts_after(5))
    output = tmp_path / "results.jsonl"

    exit_code = cli.main(_live_args(verified, small_config, output))

    statuses = {line["status"] for line in _lines(output)}
    assert statuses == {"HARNESS_FAILED", "NOT_RUN"}
    assert exit_code == cli.EXIT_CONFIG


def test_after_the_budget_is_spent_no_further_probe_runs(
    verified: Path,
    small_config: Path,
    tmp_path: Path,
    scripted_live: type[ScriptedLive],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe = _install(monkeypatch, _codex_drifts_after(10_000))
    output = tmp_path / "results.jsonl"
    args = _live_args(verified, small_config, output)
    args[2] = "5"

    exit_code = cli.main(args)

    lines = _lines(output)
    cut = [line for line in lines if line["status"] == "NOT_RUN"]
    attempted = len(lines) - len(cut) + 1
    assert exit_code == cli.EXIT_OK
    assert len(probe.calls) == 2 + attempted
    assert {line["reason"] for line in cut[1:]} == {"invocation budget spent"}


# --- the probe and the comparison -------------------------------------------


def _completed(stdout: str, returncode: int = 0) -> Callable[..., Any]:
    def runner(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, returncode, stdout=stdout, stderr="")

    return runner


def test_installed_version_reads_the_first_line_of_the_cli_version() -> None:
    runner = _completed(f"{COPILOT_VERSION}\nRun 'copilot update' to check for updates.\n")

    assert live_mod.installed_version("copilot", runner) == COPILOT_VERSION


def test_installed_version_isolates_the_profile_and_passes_copilot_no_auto_update() -> None:
    seen: dict[str, Any] = {}

    def runner(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        seen["argv"], seen["env"] = argv, kwargs["env"]
        return subprocess.CompletedProcess(argv, 0, stdout=COPILOT_VERSION, stderr="")

    live_mod.installed_version("copilot", runner)

    assert seen["argv"] == ["copilot", "--no-auto-update", "--version"]
    assert "routing-version-copilot-" in seen["env"]["HOME"]


@pytest.mark.parametrize(
    "runner",
    [
        _completed("", 0),
        _completed(CODEX_VERSION, 1),
    ],
    ids=["empty-output", "non-zero-exit"],
)
def test_installed_version_raises_probe_error_on_a_bad_answer(runner: Callable[..., Any]) -> None:
    with pytest.raises(live_mod.VersionProbeError, match="codex version probe failed"):
        live_mod.installed_version("codex", runner)


@pytest.mark.parametrize(
    "exc",
    [FileNotFoundError("codex"), subprocess.TimeoutExpired(["codex"], 60.0)],
    ids=["missing-binary", "timeout"],
)
def test_installed_version_raises_probe_error_when_the_cli_cannot_run(exc: Exception) -> None:
    def runner(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise exc

    with pytest.raises(live_mod.VersionProbeError) as caught:
        live_mod.installed_version("codex", runner)
    assert caught.value.__cause__ is exc


def test_require_pinned_versions_passes_when_every_cli_matches() -> None:
    live_mod.require_pinned_versions(PINS, PINS.__getitem__)


def test_require_pinned_versions_compares_exactly_and_names_every_drift() -> None:
    installed = {"codex": CODEX_VERSION + " ", "copilot": "GitHub Copilot CLI 1.0.89-1"}

    with pytest.raises(live_mod.VersionDriftError) as caught:
        live_mod.require_pinned_versions(PINS, installed.__getitem__)

    message = str(caught.value)
    assert "codex installed" in message and "copilot installed" in message
