"""Tests for scripts/ci/detect_velocity_opportunities.py."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import scripts.ci.detect_velocity_opportunities as dvo

# ---------------------------------------------------------------------------
# build_accelerator_args
# ---------------------------------------------------------------------------


def test_build_args_minimal():
    env = {"EVENT_NAME": "push"}
    args = dvo.build_accelerator_args(env)
    assert args == [
        "scripts/velocity_accelerator.py",
        "--event",
        "push",
        "--output-format",
        "json",
    ]


def test_build_args_pr_merged():
    env = {
        "EVENT_NAME": "pull_request",
        "EVENT_ACTION": "closed",
        "PR_NUMBER": "42",
        "PR_MERGED": "true",
    }
    args = dvo.build_accelerator_args(env)
    assert "--action" in args and "closed" in args
    assert "--pr-number" in args and "42" in args
    assert "--pr-merged" in args


def test_build_args_pr_not_merged():
    env = {
        "EVENT_NAME": "pull_request",
        "PR_MERGED": "false",
    }
    args = dvo.build_accelerator_args(env)
    assert "--pr-merged" not in args


def test_build_args_issue():
    env = {
        "EVENT_NAME": "issues",
        "EVENT_ACTION": "labeled",
        "ISSUE_NUMBER": "7",
        "ISSUE_TITLE": "A title",
        "ISSUE_BODY": "A body",
    }
    args = dvo.build_accelerator_args(env)
    assert "--issue-number" in args and "7" in args
    assert "--issue-title" in args and "A title" in args
    assert "--issue-body" in args and "A body" in args


def test_build_args_empty_optionals_omitted():
    env = {"EVENT_NAME": "push", "EVENT_ACTION": "", "PR_NUMBER": ""}
    args = dvo.build_accelerator_args(env)
    assert "--action" not in args
    assert "--pr-number" not in args


# ---------------------------------------------------------------------------
# main - config error (GITHUB_OUTPUT not set)
# ---------------------------------------------------------------------------


def test_main_missing_github_output(monkeypatch):
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    assert dvo.main() == dvo.EXIT_CONFIG


# ---------------------------------------------------------------------------
# main - velocity_accelerator exits 2 (config error)
# ---------------------------------------------------------------------------


def test_main_accelerator_config_error(tmp_path, monkeypatch):
    output_file = tmp_path / "output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
    monkeypatch.setenv("EVENT_NAME", "push")
    mock_result = MagicMock(returncode=2, stdout="", stderr="config error")
    with patch("scripts.ci.detect_velocity_opportunities.subprocess.run", return_value=mock_result):
        assert dvo.main() == dvo.EXIT_FAILURE


# ---------------------------------------------------------------------------
# main - success with opportunities
# ---------------------------------------------------------------------------


def test_main_success_with_opportunities(tmp_path, monkeypatch):
    output_file = tmp_path / "output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
    monkeypatch.setenv("EVENT_NAME", "push")
    monkeypatch.setenv("BEFORE_SHA", "abc")
    monkeypatch.setenv("AFTER_SHA", "def")

    opportunities = [{"title": "Opp 1", "priority": "high"}]
    mock_result = MagicMock(returncode=0, stdout=json.dumps(opportunities), stderr="")

    captured_env = {}

    def capture_run(cmd, **kwargs):
        captured_env.update(kwargs.get("env", {}))
        return mock_result

    with patch("scripts.ci.detect_velocity_opportunities.subprocess.run", side_effect=capture_run):
        rc = dvo.main()

    assert rc == dvo.EXIT_SUCCESS
    content = output_file.read_text(encoding="utf-8")
    assert "count=1" in content
    assert "opportunities=" in content
    parsed = json.loads(content.split("opportunities=")[1].splitlines()[0])
    assert parsed == opportunities
    # SHA forwarding
    assert captured_env.get("GITHUB_EVENT_BEFORE") == "abc"
    assert captured_env.get("GITHUB_SHA") == "def"
    # BEFORE_SHA/AFTER_SHA removed from forwarded env
    assert "BEFORE_SHA" not in captured_env
    assert "AFTER_SHA" not in captured_env


# ---------------------------------------------------------------------------
# main - zero opportunities
# ---------------------------------------------------------------------------


def test_main_zero_opportunities(tmp_path, monkeypatch):
    output_file = tmp_path / "output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
    monkeypatch.setenv("EVENT_NAME", "push")
    mock_result = MagicMock(returncode=0, stdout="[]", stderr="")
    with patch("scripts.ci.detect_velocity_opportunities.subprocess.run", return_value=mock_result):
        rc = dvo.main()
    assert rc == dvo.EXIT_SUCCESS
    content = output_file.read_text(encoding="utf-8")
    assert "count=0" in content


# ---------------------------------------------------------------------------
# main - non-JSON output falls back to empty list
# ---------------------------------------------------------------------------


def test_main_non_json_output(tmp_path, monkeypatch):
    output_file = tmp_path / "output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
    monkeypatch.setenv("EVENT_NAME", "push")
    mock_result = MagicMock(returncode=0, stdout="not json at all", stderr="")
    with patch("scripts.ci.detect_velocity_opportunities.subprocess.run", return_value=mock_result):
        rc = dvo.main()
    assert rc == dvo.EXIT_SUCCESS
    assert "count=0" in output_file.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# main - non-list JSON output falls back to empty list
# ---------------------------------------------------------------------------


def test_main_non_list_json(tmp_path, monkeypatch):
    output_file = tmp_path / "output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
    monkeypatch.setenv("EVENT_NAME", "push")
    mock_result = MagicMock(returncode=0, stdout='{"key": "value"}', stderr="")
    with patch("scripts.ci.detect_velocity_opportunities.subprocess.run", return_value=mock_result):
        rc = dvo.main()
    assert rc == dvo.EXIT_SUCCESS
    assert "count=0" in output_file.read_text(encoding="utf-8")
