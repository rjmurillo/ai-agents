"""Tests for scripts/ci/drift_create_alert_issue.py.

Covers:
  - missing template -> error, exit 1
  - gh issue create success -> exit 0
  - gh issue create failure -> propagate exit code
  - template substitution (date, url, repository, run_id, details)
  - drift-details.md missing is handled gracefully
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.ci.drift_create_alert_issue import (
    EXIT_CONFIG,
    EXIT_EXTERNAL,
    EXIT_OK,
    main,
    run,
)


def _make_template(tmp_path: Path) -> Path:
    tmpl = (
        "## Agent Drift Detected\n\n"
        "**Detection Date**: $DETECTION_DATE\n"
        "**Workflow Run**: $SERVER_URL/$REPOSITORY/actions/runs/$RUN_ID\n\n"
        "### Agents with Drift\n\n"
        "$DRIFT_DETAILS\n"
    )
    p = tmp_path / ".github" / "prompts" / "drift-alert-issue.md"
    p.parent.mkdir(parents=True)
    p.write_text(tmpl, encoding="utf-8")
    return p


def _mock_gh(returncode: int) -> MagicMock:
    m = MagicMock()
    m.returncode = returncode
    return m


def test_missing_template_returns_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    rc = run()
    assert rc == EXIT_CONFIG
    assert "template not found" in capsys.readouterr().err


def test_success_calls_gh_issue_create(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    _make_template(tmp_path)
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.setenv("SERVER_URL", "https://github.com")
    monkeypatch.setenv("REPOSITORY", "owner/repo")
    monkeypatch.setenv("RUN_ID", "99")
    (tmp_path / "drift-details.md").write_text("- agent: foo", encoding="utf-8")

    with patch(
        "scripts.ci.drift_create_alert_issue.subprocess.run", return_value=_mock_gh(0)
    ) as mock_sub:
        rc = run()

    assert rc == EXIT_OK
    call_args = mock_sub.call_args[0][0]
    assert "gh" in call_args
    assert "issue" in call_args
    assert "create" in call_args


def test_gh_failure_propagated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    _make_template(tmp_path)
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.setenv("SERVER_URL", "https://github.com")
    monkeypatch.setenv("REPOSITORY", "owner/repo")
    monkeypatch.setenv("RUN_ID", "1")
    (tmp_path / "drift-details.md").write_text("- agent: foo", encoding="utf-8")

    with patch("scripts.ci.drift_create_alert_issue.subprocess.run", return_value=_mock_gh(1)):
        rc = run()

    assert rc == EXIT_EXTERNAL


def test_gh_nonzero_exit_maps_to_exit_err(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Any non-zero returncode from gh must map to EXIT_ERR=1 (ADR-035)."""
    monkeypatch.chdir(tmp_path)
    _make_template(tmp_path)
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.setenv("SERVER_URL", "https://github.com")
    monkeypatch.setenv("REPOSITORY", "owner/repo")
    monkeypatch.setenv("RUN_ID", "1")
    (tmp_path / "drift-details.md").write_text("- agent: foo", encoding="utf-8")

    with patch("scripts.ci.drift_create_alert_issue.subprocess.run", return_value=_mock_gh(2)):
        rc = run()

    assert rc == EXIT_EXTERNAL


def test_template_substitution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    _make_template(tmp_path)
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.setenv("SERVER_URL", "https://example.com")
    monkeypatch.setenv("REPOSITORY", "acme/widgets")
    monkeypatch.setenv("RUN_ID", "42")
    (tmp_path / "drift-details.md").write_text("drift here", encoding="utf-8")

    captured_body: list[str] = []

    def fake_gh(cmd: list[str], **kwargs: object) -> MagicMock:
        # Find --body-file argument
        idx = cmd.index("--body-file")
        body_file = Path(cmd[idx + 1])
        captured_body.append(body_file.read_text(encoding="utf-8"))
        m = MagicMock()
        m.returncode = 0
        return m

    with patch("scripts.ci.drift_create_alert_issue.subprocess.run", side_effect=fake_gh):
        run()

    body = captured_body[0]
    assert "https://example.com" in body
    assert "acme/widgets" in body
    assert "42" in body
    assert "drift here" in body


def test_missing_drift_details_main_returns_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _make_template(tmp_path)
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.setenv("SERVER_URL", "https://github.com")
    monkeypatch.setenv("REPOSITORY", "owner/repo")
    monkeypatch.setenv("RUN_ID", "1")
    # drift-details.md does NOT exist

    with patch("scripts.ci.drift_create_alert_issue.subprocess.run") as mock_run:
        rc = main()

    assert rc == EXIT_CONFIG
    mock_run.assert_not_called()


def test_empty_drift_details_returns_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _make_template(tmp_path)
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    (tmp_path / "drift-details.md").write_text("", encoding="utf-8")

    with patch("scripts.ci.drift_create_alert_issue.subprocess.run") as mock_run:
        rc = main()

    assert rc == EXIT_CONFIG
    mock_run.assert_not_called()


def test_fallback_env_vars_used(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    _make_template(tmp_path)
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.delenv("SERVER_URL", raising=False)
    monkeypatch.setenv("GITHUB_SERVER_URL", "https://github.com")
    monkeypatch.delenv("REPOSITORY", raising=False)
    monkeypatch.setenv("GITHUB_REPOSITORY", "fallback/repo")
    monkeypatch.delenv("RUN_ID", raising=False)
    monkeypatch.setenv("GITHUB_RUN_ID", "7")
    (tmp_path / "drift-details.md").write_text("- agent: foo", encoding="utf-8")

    captured_body: list[str] = []

    def fake_gh(cmd: list[str], **kwargs: object) -> MagicMock:
        idx = cmd.index("--body-file")
        captured_body.append(Path(cmd[idx + 1]).read_text(encoding="utf-8"))
        m = MagicMock()
        m.returncode = 0
        return m

    with patch("scripts.ci.drift_create_alert_issue.subprocess.run", side_effect=fake_gh):
        run()

    body = captured_body[0]
    assert "fallback/repo" in body
    assert "7" in body
