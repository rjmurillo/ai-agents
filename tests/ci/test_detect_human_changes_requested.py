"""Tests for scripts/ci/detect_human_changes_requested.py."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import scripts.ci.detect_human_changes_requested as dhcr

# ---------------------------------------------------------------------------
# main - config error
# ---------------------------------------------------------------------------


def test_main_missing_github_output(monkeypatch):
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    assert dhcr.main() == dhcr.EXIT_CONFIG


# ---------------------------------------------------------------------------
# main - gh CLI failure (graceful fallback)
# ---------------------------------------------------------------------------


def test_main_gh_failure_writes_false(tmp_path, monkeypatch):
    out = tmp_path / "output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setenv("PR_NUMBER", "5")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    mock = MagicMock(returncode=1, stdout="", stderr="error")
    with patch("scripts.ci.detect_human_changes_requested.subprocess.run", return_value=mock):
        rc = dhcr.main()
    assert rc == dhcr.EXIT_SUCCESS
    assert "human_changes_requested=false" in out.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# main - no human reviews
# ---------------------------------------------------------------------------


def test_main_no_human_changes(tmp_path, monkeypatch):
    out = tmp_path / "output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setenv("PR_NUMBER", "7")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    reviews = [
        {"state": "CHANGES_REQUESTED", "author": {"login": "coderabbitai[bot]"}},
        {"state": "APPROVED", "author": {"login": "human-reviewer"}},
    ]
    mock = MagicMock(returncode=0, stdout=json.dumps({"reviews": reviews}))
    with patch("scripts.ci.detect_human_changes_requested.subprocess.run", return_value=mock):
        rc = dhcr.main()
    assert rc == dhcr.EXIT_SUCCESS
    assert "human_changes_requested=false" in out.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# main - human CHANGES_REQUESTED present
# ---------------------------------------------------------------------------


def test_main_human_changes_present(tmp_path, monkeypatch):
    out = tmp_path / "output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setenv("PR_NUMBER", "9")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    reviews = [
        {"state": "CHANGES_REQUESTED", "author": {"login": "real-human"}},
    ]
    mock = MagicMock(returncode=0, stdout=json.dumps({"reviews": reviews}))
    with patch("scripts.ci.detect_human_changes_requested.subprocess.run", return_value=mock):
        rc = dhcr.main()
    assert rc == dhcr.EXIT_SUCCESS
    assert "human_changes_requested=true" in out.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# main - bot author is not flagged
# ---------------------------------------------------------------------------


def test_main_bot_authors_excluded(tmp_path, monkeypatch):
    out = tmp_path / "output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setenv("PR_NUMBER", "11")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    reviews = [
        {"state": "CHANGES_REQUESTED", "author": {"login": bot}} for bot in dhcr._BOT_AUTHORS
    ]
    mock = MagicMock(returncode=0, stdout=json.dumps({"reviews": reviews}))
    with patch("scripts.ci.detect_human_changes_requested.subprocess.run", return_value=mock):
        rc = dhcr.main()
    assert rc == dhcr.EXIT_SUCCESS
    assert "human_changes_requested=false" in out.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# main - invalid JSON from gh
# ---------------------------------------------------------------------------


def test_main_invalid_json_from_gh(tmp_path, monkeypatch):
    out = tmp_path / "output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setenv("PR_NUMBER", "13")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    mock = MagicMock(returncode=0, stdout="not json")
    with patch("scripts.ci.detect_human_changes_requested.subprocess.run", return_value=mock):
        rc = dhcr.main()
    assert rc == dhcr.EXIT_SUCCESS
    assert "human_changes_requested=false" in out.read_text(encoding="utf-8")
