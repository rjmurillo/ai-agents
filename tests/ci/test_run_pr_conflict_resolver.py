"""Tests for scripts/ci/run_pr_conflict_resolver.py."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import scripts.ci.run_pr_conflict_resolver as rpcr

# ---------------------------------------------------------------------------
# main - config error
# ---------------------------------------------------------------------------


def test_main_missing_github_output(monkeypatch):
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    assert rpcr.main() == rpcr.EXIT_CONFIG


# ---------------------------------------------------------------------------
# main - resolver fatal error (exit > 1)
# ---------------------------------------------------------------------------


def test_main_resolver_fatal_exit(tmp_path, monkeypatch):
    out = tmp_path / "output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setenv("PR_NUMBER", "5")
    monkeypatch.setenv("HEAD_REF", "feat/foo")
    monkeypatch.setenv("BASE_REF", "main")
    monkeypatch.setenv("REPO_OWNER", "owner")
    monkeypatch.setenv("REPO_NAME", "repo")
    mock = MagicMock(returncode=3, stdout="fatal", stderr="")
    with patch("scripts.ci.run_pr_conflict_resolver.subprocess.run", return_value=mock):
        rc = rpcr.main()
    assert rc == rpcr.EXIT_FAILURE


# ---------------------------------------------------------------------------
# main - auto-resolved (success)
# ---------------------------------------------------------------------------


def test_main_auto_resolved(tmp_path, monkeypatch):
    out = tmp_path / "output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setenv("PR_NUMBER", "7")
    monkeypatch.setenv("HEAD_REF", "feat/bar")
    monkeypatch.setenv("BASE_REF", "main")
    monkeypatch.setenv("REPO_OWNER", "owner")
    monkeypatch.setenv("REPO_NAME", "repo")
    result_json = json.dumps({"success": True, "files_resolved": ["a.py", "b.py"]})
    mock = MagicMock(returncode=0, stdout=result_json, stderr="")
    with patch("scripts.ci.run_pr_conflict_resolver.subprocess.run", return_value=mock):
        rc = rpcr.main()
    assert rc == rpcr.EXIT_SUCCESS
    content = out.read_text(encoding="utf-8")
    assert "needs_ai=false" in content


# ---------------------------------------------------------------------------
# main - blocked (needs AI)
# ---------------------------------------------------------------------------


def test_main_needs_ai(tmp_path, monkeypatch):
    out = tmp_path / "output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setenv("PR_NUMBER", "9")
    monkeypatch.setenv("HEAD_REF", "feat/baz")
    monkeypatch.setenv("BASE_REF", "main")
    monkeypatch.setenv("REPO_OWNER", "owner")
    monkeypatch.setenv("REPO_NAME", "repo")
    result_json = json.dumps({"success": False, "files_blocked": ["tricky.py"]})
    mock = MagicMock(returncode=1, stdout=result_json, stderr="")
    with patch("scripts.ci.run_pr_conflict_resolver.subprocess.run", return_value=mock):
        rc = rpcr.main()
    assert rc == rpcr.EXIT_SUCCESS
    content = out.read_text(encoding="utf-8")
    assert "needs_ai=true" in content
    assert "blocked_files=" in content
    assert "tricky.py" in content


# ---------------------------------------------------------------------------
# main - invalid JSON from resolver falls back to empty
# ---------------------------------------------------------------------------


def test_main_invalid_json_from_resolver(tmp_path, monkeypatch):
    out = tmp_path / "output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setenv("PR_NUMBER", "11")
    monkeypatch.setenv("HEAD_REF", "feat/x")
    monkeypatch.setenv("BASE_REF", "main")
    monkeypatch.setenv("REPO_OWNER", "owner")
    monkeypatch.setenv("REPO_NAME", "repo")
    mock = MagicMock(returncode=0, stdout="not json", stderr="")
    with patch("scripts.ci.run_pr_conflict_resolver.subprocess.run", return_value=mock):
        rc = rpcr.main()
    assert rc == rpcr.EXIT_SUCCESS
    content = out.read_text(encoding="utf-8")
    # Empty parsed dict -> success=False path -> needs_ai=true
    assert "needs_ai=true" in content
