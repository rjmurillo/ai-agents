"""Exercise redaction through the local workflow CLI and stage reports."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts.validation import run_workflow_local_test as workflow

WORKFLOW_PATH = ".github/workflows/redaction.yml"
ENV_NAME = "SYNTHETIC_SETTING"
ENV_MARKER = "fixture-alpha-881"
FILE_NAME = "SYNTHETIC_LOCAL_SETTING"
FILE_MARKER = "fixture-beta-436"
WRAPPER_MARKER = "fixture-gamma-902"

STDOUT = f"stage stdout {ENV_NAME.lower()} {ENV_MARKER}\n"
STDERR = f"stage stderr {FILE_NAME} {FILE_MARKER}\nBearer {WRAPPER_MARKER}\n"


@pytest.fixture
def workflow_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Give the workflow both an environment and a dotenv secret."""
    workflow_path = tmp_path / WORKFLOW_PATH
    workflow_path.parent.mkdir(parents=True)
    workflow_path.write_text(
        f"on: [push]\njobs: {{}}\nenv:\n  FIXTURE: ${{{{ secrets.{ENV_NAME} }}}}\n",
        encoding="utf-8",
    )
    (tmp_path / ".secrets").write_text(f'{FILE_NAME}="{FILE_MARKER}"\n', encoding="utf-8")
    monkeypatch.setenv(ENV_NAME, ENV_MARKER)
    monkeypatch.delenv(workflow._BYPASS_ENV, raising=False)
    monkeypatch.delenv("ACT", raising=False)
    monkeypatch.setattr(workflow, "_have", lambda tool: True)
    monkeypatch.setattr(workflow, "_gh_act_available", lambda: True)
    monkeypatch.setattr(workflow, "_docker_ready", lambda: True)
    return tmp_path


@pytest.mark.parametrize("report_format", ["text", "json"])
@pytest.mark.parametrize("failure", ["act", "actionlint", "timeout"])
def test_cli_redacts_captured_output(
    workflow_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    report_format: str,
    failure: str,
) -> None:
    """Failure and timeout details retain diagnostics in both report formats."""

    def open_process(cmd: list[str], **_kwargs: object) -> Mock:
        process = Mock(returncode=0)
        if cmd[0] == "actionlint" and failure != "actionlint":
            process.communicate.return_value = ("", "")
        elif failure == "timeout":
            process.communicate.side_effect = [
                subprocess.TimeoutExpired(cmd, 1, STDOUT.encode(), STDERR.encode()),
                ("", ""),
            ]
        else:
            process.returncode = 1
            process.communicate.return_value = (STDOUT.rstrip(), STDERR)
        return process

    monkeypatch.setattr(subprocess, "Popen", open_process)
    monkeypatch.setattr(workflow, "_terminate", Mock())
    exit_code = workflow.main(
        [
            "--repo-root",
            str(workflow_repo),
            "--files",
            WORKFLOW_PATH,
            "--format",
            report_format,
            "--no-full",
        ]
    )
    captured = capsys.readouterr()
    if report_format == "json":
        report = json.loads(captured.out)
        assert report["exit_code"] == 1
        assert not report["secret_skipped"]
        detail = report["stages"][-1]["detail"]
    else:
        assert "workflow-local-test: FAIL" in captured.out
        detail = captured.out
    assert exit_code == 1
    assert captured.err == ""
    assert "stage stdout" in detail
    assert "stage stderr" in detail
    for marker in (ENV_NAME, ENV_MARKER, FILE_NAME, FILE_MARKER, WRAPPER_MARKER):
        assert marker.lower() not in detail.lower()
    assert ("TimeoutExpired" in detail) == (failure == "timeout")


def test_stage_detail_redacts_before_truncating(
    workflow_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Truncation cannot remove the start of a value before it is redacted."""
    suffix = " marker\n" + "x" * (workflow._DETAIL_CAP - len(" marker\n") - 8)
    monkeypatch.setattr(workflow, "_run", lambda *args, **kwargs: (1, f"{ENV_MARKER}{suffix}", ""))

    stage = workflow._act_dryrun_stage([WORKFLOW_PATH], workflow_repo)

    assert not stage.ok
    assert "marker" in stage.detail
    assert ENV_MARKER[-8:] not in stage.detail


def test_unclosed_secret_in_stdout_preserves_timeout_diagnostics(
    workflow_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A multiline redaction cannot consume the other stream's diagnostics."""
    monkeypatch.setattr(
        workflow,
        "_run",
        lambda *args, **kwargs: (
            -1,
            "-----BEGIN PRIVATE KEY-----\nfixture-private-183",
            "TimeoutExpired: stage timed out\nordinary stderr",
        ),
    )

    stage = workflow._act_dryrun_stage([WORKFLOW_PATH], workflow_repo)

    assert not stage.ok
    assert "fixture-private-183" not in stage.detail
    assert "TimeoutExpired" in stage.detail
    assert "ordinary stderr" in stage.detail


def test_local_pytest_stage_redacts_short_literal_and_keeps_failure(
    workflow_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The local pytest fallback returns a sanitized failed stage."""
    short_marker = "X82"
    monkeypatch.setenv(ENV_NAME, short_marker)
    monkeypatch.setattr(
        workflow,
        "_local_pytest_commands",
        lambda *_: (
            [(["uv"], {"COVERAGE_FILE": ".coverage.0", "PYTEST_NON_TMP_ROOT": "pytest-0"})],
            "",
        ),
    )
    monkeypatch.setattr(
        workflow, "_run", lambda *args, **kwargs: (1, f"assertion failed: {short_marker}", STDERR)
    )

    stage = workflow._local_pytest_stage([WORKFLOW_PATH], workflow_repo)

    assert not stage.ok
    assert short_marker not in stage.detail
    assert FILE_MARKER not in stage.detail
    assert "assertion failed" in stage.detail
