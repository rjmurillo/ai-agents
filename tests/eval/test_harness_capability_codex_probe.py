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
import subprocess
from datetime import date
from pathlib import Path

from tests.eval._harness_capability_test_support import capability, cli


class _MultiHarnessRunner:
    """Dispatch fake `--version` output keyed by the invoked executable."""

    def __init__(
        self,
        *,
        versions: dict[str, str] | None = None,
        fail: frozenset[str] = frozenset(),
        stdout: str = "",
    ) -> None:
        self.versions = versions or {}
        self.fail = fail
        self.stdout = stdout
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
            return subprocess.CompletedProcess(args, 0, self.stdout, "")
        return subprocess.CompletedProcess(args, 0, self.versions.get(executable, ""), "")


def _which_only(*names: str):
    allowed = set(names)
    return lambda name: f"/bin/{name}" if name in allowed else None


def _write_model_probe(path: Path) -> None:
    path.write_text(
        '{"probes":[{"harness":"copilot","capability":"model_override",'
        '"parent_value":"gpt-5.6-sol","child_value":"claude-opus-5",'
        '"cwd":"nested","argv":["copilot","--prompt","probe"],'
        '"request_flag":"--model"}]}',
        encoding="utf-8",
    )


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


def test_behavioral_probe_updates_copilot_record(tmp_path: Path, monkeypatch) -> None:
    output = tmp_path / "report.json"
    plan = tmp_path / "probes.json"
    _write_model_probe(plan)
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
    report = json.loads(output.read_text(encoding="utf-8"))
    copilot = next(row for row in report["harnesses"] if row["harness"] == "copilot")
    assert copilot["capabilities"]["model_override"]["status"] == "VERIFIED"
    assert copilot["capabilities"]["model_override"]["probe_command"] == (
        "custom-copilot --prompt probe --model claude-opus-5"
    )
    assert copilot["capabilities"]["model_override"]["date"] == date.today().isoformat()
    assert copilot["supported_models"] == ["claude-opus-5"]
    assert copilot["probe_command"] == "custom-copilot --prompt probe --model claude-opus-5"
    assert copilot["date"] == date.today().isoformat()
    expected_call = [
        "custom-copilot",
        "--prompt",
        "probe",
        "--model",
        "claude-opus-5",
    ]
    assert expected_call in runner.calls
    behavioral_index = runner.calls.index(expected_call)
    behavioral_kwargs = runner.kwargs[behavioral_index]
    workspace = (output.parent / "behavioral-probes" / "copilot").resolve()
    assert behavioral_kwargs["cwd"] == workspace / "nested"
    assert (workspace / "nested").is_dir()
    behavioral_env = behavioral_kwargs["env"]
    assert isinstance(behavioral_env, dict)
    assert Path(str(behavioral_env["COPILOT_HOME"])) == (
        workspace / ".parity-profile" / "copilot"
    )


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


def test_cli_missing_codex_binary_verifies_no_capability_silently(
    tmp_path: Path, monkeypatch
) -> None:
    output = tmp_path / "report.json"
    monkeypatch.setattr(cli.shutil, "which", _which_only("copilot"))
    runner = _MultiHarnessRunner(versions={"copilot": "copilot 9.9.9"})

    cli.main(["--output", str(output)], runner=runner)

    report = json.loads(output.read_text(encoding="utf-8"))
    codex_capabilities = next(row for row in report["harnesses"] if row["harness"] == "codex")[
        "capabilities"
    ]
    # A missing version probe must never be read as license to mark a
    # behavioral capability VERIFIED by default (no silent pass).
    for key in capability.CAPABILITY_KEYS:
        assert codex_capabilities[key]["status"] == "UNVERIFIED", key
