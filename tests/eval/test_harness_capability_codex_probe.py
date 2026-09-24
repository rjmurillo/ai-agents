"""Codex wiring coverage for the capability-matrix CLI (issue #5423 reopen).

Before this change `PROBE_HARNESS` had no "codex" key, so `_augment_versions`
never attempted a codex probe at all, regardless of whether the CLI was on
PATH or what `shutil.which` returned. `test_cli_live_probe_fills_codex_version`
and `test_cli_probe_failure_still_attempts_codex` assert on `runner.calls` to
prove a probe was actually attempted; both failed on pre-fix code because that
list never contained a codex call. The other two tests describe required
behavior (never crash, never a silent pass) that already held before this
change by omission, so they pass on both pre-fix and post-fix code; they guard
against a future regression rather than proving this one.
"""

from __future__ import annotations

import json
import shlex
import subprocess
from datetime import date
from pathlib import Path

import pytest

from tests.eval._harness_capability_test_support import UNPROBED_MATRIX, capability, cli


@pytest.fixture(autouse=True)
def _start_from_the_unprobed_matrix(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the CLI default at the pre-probe matrix, not the live-probed one."""
    monkeypatch.setattr(cli, "DEFAULT_MATRIX", UNPROBED_MATRIX)


class _MultiHarnessRunner:
    """Dispatch fake `--version` output keyed by the invoked executable."""

    def __init__(
        self,
        *,
        versions: dict[str, str] | None = None,
        fail: frozenset[str] = frozenset(),
        stdout: str = "",
        stderr: str = "",
    ) -> None:
        self.versions = versions or {}
        self.fail = fail
        self.stdout = stdout
        self.stderr = stderr
        self.calls: list[list[str]] = []
        self.kwargs: list[dict[str, object]] = []

    def __call__(self, argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        args = [str(value) for value in argv]
        self.calls.append(args)
        self.kwargs.append(dict(_kwargs))
        executable = args[0]
        if executable in self.fail:
            return subprocess.CompletedProcess(args, 1, "", "boom")
        if "--version" not in args:
            return subprocess.CompletedProcess(args, 0, self.stdout, self.stderr)
        return subprocess.CompletedProcess(args, 0, self.versions.get(executable, ""), "")


def _which_only(*names: str):
    allowed = set(names)
    return lambda name: f"/bin/{name}" if name in allowed else None


def _write_model_probe(path: Path, *, log_dir: Path | None = None) -> None:
    """Write a copilot `model_override` behavioral-probe plan.

    `log_dir`, when given, adds `--log-level all --log-dir <log_dir>` to the
    probe's argv: copilot's `model_override` now reads its backend evidence
    from that wire log (`_capability_probes._capture_copilot_wire`), not
    `--json` stdout, so a plan that omits it can never reach `VERIFIED`
    regardless of what the fake runner returns.
    """
    argv = ["copilot", "--prompt", "probe"]
    if log_dir is not None:
        argv += ["--log-level", "all", "--log-dir", str(log_dir)]
    payload = {
        "probes": [
            {
                "harness": "copilot",
                "capability": "model_override",
                "parent_value": "gpt-5.6-sol",
                "child_value": "claude-opus-5",
                "cwd": "nested",
                "argv": argv,
                "request_flag": "--model",
            }
        ]
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


# --- Positive: codex is probed and its version filled when on PATH -------------


def test_cli_live_probe_fills_codex_version(tmp_path: Path, monkeypatch) -> None:
    output = tmp_path / "report.json"
    monkeypatch.setattr(cli.shutil, "which", _which_only("codex", "copilot"))
    runner = _MultiHarnessRunner(versions={"codex": "codex-cli 0.34.0", "copilot": "copilot 9.9.9"})

    code = cli.main(["--output", str(output)], runner=runner)

    assert code == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    by_harness = {row["harness"]: row for row in report["harnesses"]}
    assert by_harness["codex"]["version"] == "codex-cli 0.34.0"
    assert by_harness["codex"]["version_evidence"] == "backend"
    assert ["codex", "--version"] in runner.calls


# --- Negative: a probe failure still attempts codex and stays UNVERIFIED -------


def test_cli_probe_failure_still_attempts_codex(tmp_path: Path, monkeypatch) -> None:
    output = tmp_path / "report.json"
    monkeypatch.setattr(cli.shutil, "which", _which_only("codex", "copilot"))
    runner = _MultiHarnessRunner(fail=frozenset({"codex"}), versions={"copilot": "copilot 9.9.9"})

    code = cli.main(["--output", str(output)], runner=runner)

    assert code == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    by_harness = {row["harness"]: row for row in report["harnesses"]}
    assert by_harness["codex"]["version_evidence"] == "none"
    # A probe was actually attempted and failed closed, rather than never
    # being attempted at all.
    assert ["codex", "--version"] in runner.calls


def test_behavioral_probe_waits_for_backend_version(tmp_path: Path, monkeypatch) -> None:
    output = tmp_path / "report.json"
    plan = tmp_path / "probes.json"
    _write_model_probe(plan)
    monkeypatch.setattr(cli.shutil, "which", _which_only())
    runner = _MultiHarnessRunner()

    code = cli.main(
        ["--output", str(output), "--behavioral-probes", str(plan)],
        runner=runner,
    )

    assert code == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    copilot = next(row for row in report["harnesses"] if row["harness"] == "copilot")
    assert copilot["capabilities"]["model_override"]["status"] == "UNVERIFIED"
    assert runner.calls == []


def test_invalid_behavioral_plan_is_rejected_before_live_probes(
    tmp_path: Path, monkeypatch
) -> None:
    output = tmp_path / "report.json"
    plan = tmp_path / "probes.json"
    plan.write_text(
        '{"probes":[{"harness":"copilot","capability":"model_override",'
        '"parent_value":"gpt-5.6-sol","child_value":"gpt-5.6-sol",'
        '"argv":["copilot","--prompt","probe"],"request_flag":"--model"}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(cli.shutil, "which", _which_only("codex", "copilot"))
    runner = _MultiHarnessRunner(versions={"codex": "codex-cli 0.34.0", "copilot": "copilot 9.9.9"})

    code = cli.main(
        ["--output", str(output), "--behavioral-probes", str(plan)],
        runner=runner,
    )

    assert code == cli.EXIT_CONFIG
    assert runner.calls == []
    assert not output.exists()


def test_dry_run_validates_behavioral_plan(tmp_path: Path, monkeypatch) -> None:
    """NEGATIVE CONTROL: dry-run rejects malformed plans before any CLI call."""
    output = tmp_path / "report.json"
    plan = tmp_path / "probes.json"
    plan.write_text(
        '{"probes":[{"harness":"copilot","capability":"model_override",'
        '"parent_value":"gpt-5.6-sol","child_value":"claude-opus-5",'
        '"argv":["copilot","--prompt","probe"],"request_flag":"--model",'
        '"unexpected":true}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(cli.shutil, "which", _which_only("copilot"))
    runner = _MultiHarnessRunner(versions={"copilot": "copilot 9.9.9"})

    code = cli.main(
        ["--dry-run", "--output", str(output), "--behavioral-probes", str(plan)],
        runner=runner,
    )

    assert code == cli.EXIT_CONFIG
    assert runner.calls == []
    assert not output.exists()


def _write_copilot_wire_log(log_dir: Path) -> None:
    """Write a wire log whose one response pairs `req_1` with `resp1`/`claude-opus-5`."""
    log_dir.mkdir(parents=True)
    (log_dir / "process-1.log").write_text(
        "2026-09-24T12:00:00.000Z [DEBUG] [rust:model_wire] "
        "response (Request-ID req_1):\n"
        "2026-09-24T12:00:00.000Z [DEBUG] [rust:model_wire] data:\n"
        '2026-09-24T12:00:00.000Z [DEBUG] [rust:model_wire] {"id": "resp1", '
        '"model": "claude-opus-5", "usage": {}}\n',
        encoding="utf-8",
    )


def _assert_copilot_model_override_updated(
    output: Path,
    expected_call: list[str],
    *,
    log_dir: Path,
    runner: _MultiHarnessRunner,
) -> None:
    report = json.loads(output.read_text(encoding="utf-8"))
    copilot = next(row for row in report["harnesses"] if row["harness"] == "copilot")
    expected_command = shlex.join(expected_call)
    assert copilot["capabilities"]["model_override"]["status"] == "VERIFIED"
    assert copilot["capabilities"]["model_override"]["probe_command"] == expected_command
    assert copilot["capabilities"]["model_override"]["date"] == date.today().isoformat()
    assert copilot["supported_models"] == ["claude-opus-5"]
    assert copilot["probe_command"] == expected_command
    assert copilot["date"] == date.today().isoformat()
    assert expected_call in runner.calls
    behavioral_kwargs = runner.kwargs[runner.calls.index(expected_call)]
    workspace = Path(str(behavioral_kwargs["cwd"])).parent
    assert workspace.parent == (output.parent / "behavioral-probes" / "copilot").resolve()
    assert workspace.name.startswith("probe-0-")
    assert behavioral_kwargs["cwd"] == workspace / "nested"
    behavioral_env = behavioral_kwargs["env"]
    assert isinstance(behavioral_env, dict)
    assert Path(str(behavioral_env["COPILOT_HOME"])) == (workspace / ".parity-profile" / "copilot")
    assert log_dir.is_dir()


def test_behavioral_probe_updates_copilot_record(tmp_path: Path, monkeypatch) -> None:
    """Copilot's `model_override` now reads its `--log-dir` wire log, not

    `--json` stdout (`assistant.message.data.model` is a client label, see
    `_capability_evidence.observe_copilot_model`), so this test pre-creates
    the wire log before the plan runs and points the plan's argv at it. The
    log dir sits outside the per-run workspace, which is deleted afterward.
    """
    output = tmp_path / "report.json"
    plan = tmp_path / "probes.json"
    log_dir = (tmp_path / "copilot-logs").resolve()
    _write_copilot_wire_log(log_dir)
    _write_model_probe(plan, log_dir=log_dir)
    monkeypatch.setattr(cli.shutil, "which", _which_only("custom-copilot"))
    answer = {"content": "ok", "model": "claude-opus-5", "apiCallId": "resp1"}
    runner = _MultiHarnessRunner(
        versions={"custom-copilot": "copilot 9.9.9"},
        stdout=json.dumps({"type": "assistant.message", "data": answer}) + "\n",
    )

    code = cli.main(
        [
            "--output",
            str(output),
            "--copilot-bin",
            "custom-copilot",
            "--behavioral-probes",
            str(plan),
        ],
        runner=runner,
    )

    assert code == 0
    expected_call = [
        "custom-copilot",
        "--prompt",
        "probe",
        "--log-level",
        "all",
        "--log-dir",
        str(log_dir),
        "--model",
        "claude-opus-5",
    ]
    _assert_copilot_model_override_updated(output, expected_call, log_dir=log_dir, runner=runner)


def test_same_harness_behavioral_probes_use_distinct_workspaces(
    tmp_path: Path, monkeypatch
) -> None:
    output = tmp_path / "report.json"
    plan = tmp_path / "probes.json"
    plan.write_text(
        json.dumps(
            {
                "probes": [
                    {
                        "harness": "copilot",
                        "capability": "model_override",
                        "parent_value": "gpt-5.6-sol",
                        "child_value": "claude-opus-5",
                        "argv": ["copilot", "--prompt", "probe"],
                        "request_flag": "--model",
                    },
                    {
                        "harness": "copilot",
                        "capability": "subagent_support",
                        "argv": ["copilot", "--prompt", "probe"],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cli.shutil, "which", _which_only("custom-copilot"))
    runner = _MultiHarnessRunner(
        versions={"custom-copilot": "copilot 9.9.9"},
        stdout=json.dumps(
            {
                "type": "assistant.message",
                "data": {"content": "ok", "model": "claude-opus-5"},
            }
        )
        + "\n",
    )

    code = cli.main(
        [
            "--output",
            str(output),
            "--copilot-bin",
            "custom-copilot",
            "--behavioral-probes",
            str(plan),
        ],
        runner=runner,
    )

    assert code == 0
    behavioral_kwargs = [
        kwargs
        for call, kwargs in zip(runner.calls, runner.kwargs, strict=True)
        if "--version" not in call
    ]
    workspaces = [Path(str(kwargs["cwd"])) for kwargs in behavioral_kwargs]
    assert len(workspaces) == 2
    assert workspaces[0].name.startswith("probe-0-")
    assert workspaces[1].name.startswith("probe-1-")
    assert workspaces[0].parent == workspaces[1].parent
    assert workspaces[0] != workspaces[1]


# --- Edge: missing Codex CLI on PATH stays UNVERIFIED, never a crash -----------


def test_cli_missing_codex_binary_stays_unverified_not_crash(tmp_path: Path, monkeypatch) -> None:
    output = tmp_path / "report.json"
    monkeypatch.setattr(cli.shutil, "which", _which_only("copilot"))
    runner = _MultiHarnessRunner(versions={"copilot": "copilot 9.9.9"})

    code = cli.main(["--output", str(output)], runner=runner)

    assert code == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    by_harness = {row["harness"]: row for row in report["harnesses"]}
    assert by_harness["codex"]["version"] == ""
    assert by_harness["codex"]["version_evidence"] == "none"
    assert not any(call[0] == "codex" for call in runner.calls)


def test_cli_missing_codex_binary_changes_no_codex_capability(tmp_path: Path, monkeypatch) -> None:
    """A missing binary must never be read as license to add or drop a capability claim.

    The checked-in matrix already carries real, independently-verified codex
    capabilities (live probes against codex-cli 0.156.0, 2026-09-24), so
    this run's job is to prove they pass through byte-for-byte unchanged
    when no probe of any kind can run, not to prove they start UNVERIFIED
    (they do not).
    """
    output = tmp_path / "report.json"
    monkeypatch.setattr(cli.shutil, "which", _which_only("copilot"))
    runner = _MultiHarnessRunner(versions={"copilot": "copilot 9.9.9"})
    checked_in_codex = next(
        record for record in capability.load_matrix(cli.DEFAULT_MATRIX) if record.harness == "codex"
    )

    cli.main(["--output", str(output)], runner=runner)

    report = json.loads(output.read_text(encoding="utf-8"))
    codex_capabilities = next(row for row in report["harnesses"] if row["harness"] == "codex")[
        "capabilities"
    ]
    for key in capability.CAPABILITY_KEYS:
        checked_in = checked_in_codex.capabilities[key]
        assert codex_capabilities[key]["status"] == checked_in.status.value, key
        assert codex_capabilities[key]["evidence"] == checked_in.evidence.value, key
