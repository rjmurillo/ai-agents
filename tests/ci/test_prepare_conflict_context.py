"""Tests for scripts/ci/prepare_conflict_context.py."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock, patch

import scripts.ci.prepare_conflict_context as pcc

# ---------------------------------------------------------------------------
# build_context
# ---------------------------------------------------------------------------


def test_build_context_empty_files():
    result = pcc.build_context([], "main")
    assert result == ""


def test_build_context_single_file(tmp_path):
    filepath = tmp_path / "conflict.py"
    content = "<<<<<<< HEAD\nours\n=======\ntheirs\n>>>>>>> main\n"
    filepath.write_text(content, encoding="utf-8")

    git_calls = []

    def fake_git(args):
        git_calls.append(args)
        return subprocess.CompletedProcess(args, 0, "abc123 commit\n", "")

    with patch.object(pcc, "_git", fake_git):
        result = pcc.build_context([str(filepath)], "main")

    assert f"### File: {filepath}" in result
    assert "#### Conflict markers:" in result
    assert "<<<<<<< HEAD" in result
    assert "#### Recent commits (PR branch):" in result
    assert "#### Recent commits (base branch):" in result
    assert "abc123 commit" in result


def test_build_context_missing_file():
    with patch.object(pcc, "_git", return_value=subprocess.CompletedProcess([], 0, "", "")):
        result = pcc.build_context(["/nonexistent/file.py"], "main")
    assert "### File: /nonexistent/file.py" in result


def test_build_context_truncates_at_100_lines(tmp_path):
    filepath = tmp_path / "big.py"
    lines = [f"line {i}" for i in range(200)]
    filepath.write_text("\n".join(lines), encoding="utf-8")
    with patch.object(pcc, "_git", return_value=subprocess.CompletedProcess([], 0, "", "")):
        result = pcc.build_context([str(filepath)], "main")
    content_section = result.split("```")[1]
    assert content_section.count("\n") <= 101


# ---------------------------------------------------------------------------
# main - config error
# ---------------------------------------------------------------------------


def test_main_missing_github_output(monkeypatch):
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    assert pcc.main() == pcc.EXIT_CONFIG


# ---------------------------------------------------------------------------
# main - success with files
# ---------------------------------------------------------------------------


def test_main_writes_encoded_context(tmp_path, monkeypatch):
    output_file = tmp_path / "output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
    monkeypatch.setenv("HEAD_REF", "feat/branch")
    monkeypatch.setenv("BASE_REF", "main")
    monkeypatch.setenv("BLOCKED_FILES_JSON", json.dumps(["README.md"]))

    # README.md won't exist, so conflict_lines returns []
    fake_git = MagicMock(return_value=subprocess.CompletedProcess([], 0, "", ""))
    with patch.object(pcc, "_git", fake_git):
        rc = pcc.main()

    assert rc == pcc.EXIT_SUCCESS
    content = output_file.read_text(encoding="utf-8")
    assert "conflict_context=" in content
    # Newlines are percent-encoded
    assert "%0A" in content


def test_main_empty_blocked_files(tmp_path, monkeypatch):
    output_file = tmp_path / "output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
    monkeypatch.setenv("HEAD_REF", "feat/x")
    monkeypatch.setenv("BASE_REF", "main")
    monkeypatch.setenv("BLOCKED_FILES_JSON", "[]")

    fake_git = MagicMock(return_value=subprocess.CompletedProcess([], 0, "", ""))
    with patch.object(pcc, "_git", fake_git):
        rc = pcc.main()

    assert rc == pcc.EXIT_SUCCESS
    content = output_file.read_text(encoding="utf-8")
    assert "conflict_context=" in content


def test_main_invalid_blocked_files_json(tmp_path, monkeypatch):
    output_file = tmp_path / "output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
    monkeypatch.setenv("HEAD_REF", "feat/x")
    monkeypatch.setenv("BASE_REF", "main")
    monkeypatch.setenv("BLOCKED_FILES_JSON", "not-json")

    fake_git = MagicMock(return_value=subprocess.CompletedProcess([], 0, "", ""))
    with patch.object(pcc, "_git", fake_git):
        rc = pcc.main()

    assert rc == pcc.EXIT_SUCCESS


def test_main_percent_encodes_content(tmp_path, monkeypatch):
    output_file = tmp_path / "output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
    monkeypatch.setenv("HEAD_REF", "feat/x")
    monkeypatch.setenv("BASE_REF", "main")

    # Create a file with a % character to verify encoding
    conflict_file = tmp_path / "file.py"
    conflict_file.write_text("100% done\n", encoding="utf-8")
    monkeypatch.setenv("BLOCKED_FILES_JSON", json.dumps([str(conflict_file)]))

    fake_git = MagicMock(return_value=subprocess.CompletedProcess([], 0, "", ""))
    with patch.object(pcc, "_git", fake_git):
        rc = pcc.main()

    assert rc == pcc.EXIT_SUCCESS
    content = output_file.read_text(encoding="utf-8")
    # % in the file content should become %25
    assert "%25" in content
