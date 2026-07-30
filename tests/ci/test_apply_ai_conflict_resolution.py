"""Tests for scripts/ci/apply_ai_conflict_resolution.py."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

import scripts.ci.apply_ai_conflict_resolution as aacr

# ---------------------------------------------------------------------------
# extract_json
# ---------------------------------------------------------------------------


def test_extract_json_no_fence():
    text = '{"resolutions": []}'
    assert aacr.extract_json(text) == text


def test_extract_json_with_fence():
    text = '```json\n{"resolutions": []}\n```'
    assert aacr.extract_json(text) == '{"resolutions": []}'


def test_extract_json_fence_no_lang():
    text = '```\n{"key": "val"}\n```'
    assert aacr.extract_json(text) == '{"key": "val"}'


# ---------------------------------------------------------------------------
# parse_resolutions
# ---------------------------------------------------------------------------


def test_parse_resolutions_valid():
    findings = json.dumps(
        {"resolutions": [{"file": "a.py", "strategy": "theirs", "reasoning": "newer"}]}
    )
    result = aacr.parse_resolutions(findings)
    assert len(result) == 1
    assert result[0]["file"] == "a.py"


def test_parse_resolutions_no_resolutions_key():
    with pytest.raises(ValueError, match="No JSON object"):
        aacr.parse_resolutions('{"other": "data"}')


def test_parse_resolutions_empty_array():
    with pytest.raises(ValueError, match="empty resolutions"):
        aacr.parse_resolutions(json.dumps({"resolutions": []}))


def test_parse_resolutions_with_code_fence():
    inner = json.dumps({"resolutions": [{"file": "b.py", "strategy": "ours", "reasoning": "r"}]})
    findings = f"```json\n{inner}\n```"
    result = aacr.parse_resolutions(findings)
    assert result[0]["file"] == "b.py"


# ---------------------------------------------------------------------------
# apply_resolution - theirs
# ---------------------------------------------------------------------------


def test_apply_resolution_theirs():
    calls = []
    with patch.object(
        aacr,
        "_git",
        lambda args: (calls.append(args), subprocess.CompletedProcess(args, 0, "", ""))[1],
    ):
        aacr.apply_resolution({"file": "f.py", "strategy": "theirs", "reasoning": ""})
    assert ["checkout", "--theirs", "f.py"] in calls
    assert ["add", "f.py"] in calls


def test_apply_resolution_ours():
    calls = []
    with patch.object(
        aacr,
        "_git",
        lambda args: (calls.append(args), subprocess.CompletedProcess(args, 0, "", ""))[1],
    ):
        aacr.apply_resolution({"file": "f.py", "strategy": "ours", "reasoning": ""})
    assert ["checkout", "--ours", "f.py"] in calls


def test_apply_resolution_unknown_strategy():
    with pytest.raises(ValueError, match="Unknown strategy"):
        aacr.apply_resolution({"file": "f.py", "strategy": "unknown", "reasoning": ""})


def test_apply_resolution_combine_no_content():
    with pytest.raises(ValueError, match="combined_content"):
        aacr.apply_resolution({"file": "f.py", "strategy": "combine", "reasoning": ""})


def test_apply_resolution_combine_writes_file(tmp_path):
    filepath = tmp_path / "merged.py"
    fake_git = MagicMock(return_value=subprocess.CompletedProcess([], 0, "", ""))
    with patch.object(aacr, "_git", fake_git):
        with patch("builtins.open", open):
            import os

            orig = os.getcwd()
            os.chdir(tmp_path)
            try:
                aacr.apply_resolution(
                    {
                        "file": "merged.py",
                        "strategy": "combine",
                        "reasoning": "",
                        "combined_content": "merged content",
                    }
                )
            finally:
                os.chdir(orig)
    assert filepath.read_text(encoding="utf-8") == "merged content"


# ---------------------------------------------------------------------------
# main - config error
# ---------------------------------------------------------------------------


def test_main_missing_head_ref(monkeypatch):
    monkeypatch.delenv("HEAD_REF", raising=False)
    monkeypatch.setenv("BASE_REF", "main")
    assert aacr.main() == aacr.EXIT_CONFIG


def test_main_missing_base_ref(monkeypatch):
    monkeypatch.setenv("HEAD_REF", "feat/x")
    monkeypatch.delenv("BASE_REF", raising=False)
    assert aacr.main() == aacr.EXIT_CONFIG


# ---------------------------------------------------------------------------
# main - JSON parse failure
# ---------------------------------------------------------------------------


def test_main_unparseable_findings(monkeypatch):
    monkeypatch.setenv("HEAD_REF", "feat/x")
    monkeypatch.setenv("BASE_REF", "main")
    monkeypatch.setenv("PR_NUMBER", "1")
    monkeypatch.setenv("AI_FINDINGS", "gibberish")
    assert aacr.main() == aacr.EXIT_FAILURE


# ---------------------------------------------------------------------------
# main - apply_resolution ValueError aborts merge
# ---------------------------------------------------------------------------


def test_main_apply_resolution_error_aborts_merge(monkeypatch):
    monkeypatch.setenv("HEAD_REF", "feat/x")
    monkeypatch.setenv("BASE_REF", "main")
    monkeypatch.setenv("PR_NUMBER", "2")
    # Unknown strategy triggers ValueError in apply_resolution.
    findings = json.dumps(
        {"resolutions": [{"file": "f.py", "strategy": "explode", "reasoning": ""}]}
    )
    monkeypatch.setenv("AI_FINDINGS", findings)

    abort_called = []

    def git_side_effect(args):
        if args[:2] == ["merge", "--abort"]:
            abort_called.append(True)
        return subprocess.CompletedProcess(args, 0, "", "")

    with patch.object(aacr, "_git", git_side_effect):
        rc = aacr.main()

    assert rc == aacr.EXIT_FAILURE
    assert abort_called, "merge --abort was not called"


# ---------------------------------------------------------------------------
# main - remaining conflicts abort
# ---------------------------------------------------------------------------


def test_main_remaining_conflicts_abort(monkeypatch):
    monkeypatch.setenv("HEAD_REF", "feat/x")
    monkeypatch.setenv("BASE_REF", "main")
    monkeypatch.setenv("PR_NUMBER", "2")
    findings = json.dumps(
        {"resolutions": [{"file": "f.py", "strategy": "theirs", "reasoning": ""}]}
    )
    monkeypatch.setenv("AI_FINDINGS", findings)

    # diff --name-only --diff-filter=U returns a file name (unresolved conflict)
    def git_side_effect(args):
        if args[:4] == ["diff", "--name-only", "--diff-filter=U"]:
            return subprocess.CompletedProcess(args, 0, "still_conflicted.py\n", "")
        return subprocess.CompletedProcess(args, 0, "", "")

    with patch.object(aacr, "_git", git_side_effect):
        rc = aacr.main()

    assert rc == aacr.EXIT_FAILURE


# ---------------------------------------------------------------------------
# main - success
# ---------------------------------------------------------------------------


def test_main_success(monkeypatch):
    monkeypatch.setenv("HEAD_REF", "feat/x")
    monkeypatch.setenv("BASE_REF", "main")
    monkeypatch.setenv("PR_NUMBER", "3")
    findings = json.dumps(
        {"resolutions": [{"file": "f.py", "strategy": "theirs", "reasoning": ""}]}
    )
    monkeypatch.setenv("AI_FINDINGS", findings)

    clean_git = MagicMock(return_value=subprocess.CompletedProcess([], 0, "", ""))
    push_mock = MagicMock(return_value=subprocess.CompletedProcess([], 0, "", ""))

    with patch.object(aacr, "_git", clean_git):
        with patch("scripts.ci.apply_ai_conflict_resolution.subprocess.run", push_mock):
            rc = aacr.main()

    assert rc == aacr.EXIT_SUCCESS
    # Verify safe_push was called
    push_cmd = push_mock.call_args[0][0]
    assert aacr._SAFE_PUSH in push_cmd
