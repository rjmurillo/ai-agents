"""Tests for invoke_pr_comment_processing.py consumer script."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Import the consumer script via importlib (not a package)
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / ".github" / "scripts"


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None, f"Could not load spec for {name}"
    assert spec.loader is not None, f"Spec for {name} has no loader"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("invoke_pr_comment_processing")
main = _mod.main
build_parser = _mod.build_parser
parse_findings = _mod.parse_findings
add_comment_reaction = _mod.add_comment_reaction
reply_to_comment = _mod.reply_to_comment
process_comments = _mod.process_comments


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


def _make_findings(comments: list[dict] | None = None) -> str:
    return json.dumps({"comments": comments or []})


# ---------------------------------------------------------------------------
# Tests: parse_findings
# ---------------------------------------------------------------------------


class TestParseFindings:
    def test_valid_json(self):
        result = parse_findings('{"comments": []}')
        assert result == {"comments": []}

    def test_json_in_code_fence(self):
        raw = '```json\n{"comments": []}\n```'
        result = parse_findings(raw)
        assert result == {"comments": []}

    def test_code_fence_without_language(self):
        raw = '```\n{"key": "val"}\n```'
        result = parse_findings(raw)
        assert result == {"key": "val"}

    def test_invalid_json_exits_2(self):
        with pytest.raises(SystemExit) as exc:
            parse_findings("not json at all")
        assert exc.value.code == 2

    def test_empty_string_exits_2(self):
        with pytest.raises(SystemExit) as exc:
            parse_findings("")
        assert exc.value.code == 2


# ---------------------------------------------------------------------------
# Tests: add_comment_reaction
# ---------------------------------------------------------------------------


class TestAddCommentReaction:
    def test_success_on_pr_endpoint(self):
        with patch("subprocess.run", return_value=_completed(rc=0)):
            assert add_comment_reaction("owner", "repo", 42) is True

    def test_fallback_to_issue_endpoint(self):
        call_count = 0

        def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _completed(rc=1, stderr="Not Found")
            return _completed(rc=0)

        with patch("subprocess.run", side_effect=_side_effect):
            assert add_comment_reaction("owner", "repo", 42) is True

    def test_both_fail_returns_false(self):
        with patch("subprocess.run", return_value=_completed(rc=1, stderr="error")):
            assert add_comment_reaction("owner", "repo", 42) is False

    def test_custom_reaction(self):
        with patch("subprocess.run", return_value=_completed(rc=0)) as mock:
            add_comment_reaction("owner", "repo", 42, reaction="+1")
        # First call should have +1 reaction
        call_args = mock.call_args_list[0][0][0]
        assert "content=+1" in call_args


# ---------------------------------------------------------------------------
# Tests: reply_to_comment
# ---------------------------------------------------------------------------


class TestReplyToComment:
    def test_success(self):
        with patch("subprocess.run", return_value=_completed(rc=0)):
            assert reply_to_comment("o", "r", 1, 42, "body") is True

    def test_failure(self):
        with patch("subprocess.run", return_value=_completed(rc=1, stderr="err")):
            assert reply_to_comment("o", "r", 1, 42, "body") is False

    def test_sends_json_via_stdin(self):
        with patch("subprocess.run", return_value=_completed(rc=0)) as mock:
            reply_to_comment("o", "r", 1, 42, "hello")
        assert mock.call_args.kwargs.get("input") == json.dumps({"body": "hello"})


# ---------------------------------------------------------------------------
# Tests: process_comments
# ---------------------------------------------------------------------------


class TestProcessComments:
    def test_empty_comments(self):
        stats = process_comments("o", "r", 1, {"comments": []})
        assert stats == {"acknowledged": 0, "replied": 0, "skipped": 0, "errors": 0}

    def test_stale_comment_skipped(self):
        findings = {"comments": [{"id": 1, "classification": "stale"}]}
        with patch("subprocess.run", return_value=_completed(rc=0)):
            stats = process_comments("o", "r", 1, findings)
        assert stats["skipped"] == 1
        assert stats["acknowledged"] == 1

    def test_wontfix_comment_replied(self):
        findings = {
            "comments": [{
                "id": 1,
                "classification": "wontfix",
                "resolution": "Not needed",
            }]
        }
        with patch("subprocess.run", return_value=_completed(rc=0)):
            stats = process_comments("o", "r", 1, findings)
        assert stats["replied"] == 1
        assert stats["acknowledged"] == 1

    def test_wontfix_without_resolution_skipped(self):
        findings = {
            "comments": [{"id": 1, "classification": "wontfix"}]
        }
        with patch("subprocess.run", return_value=_completed(rc=0)):
            stats = process_comments("o", "r", 1, findings)
        assert stats["skipped"] == 1

    def test_question_comment_skipped(self):
        findings = {
            "comments": [{"id": 1, "classification": "question", "summary": "Why?"}]
        }
        with patch("subprocess.run", return_value=_completed(rc=0)):
            stats = process_comments("o", "r", 1, findings)
        assert stats["skipped"] == 1

    def test_implementation_comment_skipped(self):
        findings = {
            "comments": [{
                "id": 1,
                "classification": "standard",
                "action": "implement",
                "summary": "Add tests",
            }]
        }
        with patch("subprocess.run", return_value=_completed(rc=0)):
            stats = process_comments("o", "r", 1, findings)
        assert stats["skipped"] == 1

    def test_unknown_classification_skipped(self):
        findings = {"comments": [{"id": 1, "classification": "unknown-type"}]}
        with patch("subprocess.run", return_value=_completed(rc=0)):
            stats = process_comments("o", "r", 1, findings)
        assert stats["skipped"] == 1

    def test_missing_id_counted_as_error(self):
        findings = {"comments": [{"classification": "stale"}]}
        stats = process_comments("o", "r", 1, findings)
        assert stats["errors"] == 1

    def test_reaction_failure_counted_as_error(self):
        findings = {"comments": [{"id": 1, "classification": "stale"}]}
        with patch("subprocess.run", return_value=_completed(rc=1, stderr="err")):
            stats = process_comments("o", "r", 1, findings)
        assert stats["errors"] == 1


# ---------------------------------------------------------------------------
# Tests: main
# ---------------------------------------------------------------------------


class TestMain:
    def test_non_pass_verdict_skips_processing(self):
        rc = main([
            "--pr-number", "1",
            "--verdict", "FAIL",
            "--findings-json", "{}",
        ])
        assert rc == 0

    def test_pass_verdict_with_no_comments(self):
        findings = _make_findings([])
        with patch(
            "invoke_pr_comment_processing.resolve_repo_params",
            return_value={"Owner": "o", "Repo": "r"},
        ):
            rc = main([
                "--pr-number", "1",
                "--verdict", "PASS",
                "--findings-json", findings,
            ])
        assert rc == 0

    def test_warn_verdict_processes_comments(self):
        findings = _make_findings([{"id": 1, "classification": "stale"}])
        with patch(
            "invoke_pr_comment_processing.resolve_repo_params",
            return_value={"Owner": "o", "Repo": "r"},
        ), patch("subprocess.run", return_value=_completed(rc=0)):
            rc = main([
                "--pr-number", "1",
                "--verdict", "WARN",
                "--findings-json", findings,
            ])
        assert rc == 0

    def test_errors_return_3(self):
        findings = _make_findings([{"id": 1, "classification": "stale"}])
        with patch(
            "invoke_pr_comment_processing.resolve_repo_params",
            return_value={"Owner": "o", "Repo": "r"},
        ), patch("subprocess.run", return_value=_completed(rc=1, stderr="err")):
            rc = main([
                "--pr-number", "1",
                "--verdict", "PASS",
                "--findings-json", findings,
            ])
        assert rc == 3

    def test_invalid_json_exits_2(self):
        with pytest.raises(SystemExit) as exc:
            main([
                "--pr-number", "1",
                "--verdict", "PASS",
                "--findings-json", "not json",
            ])
        assert exc.value.code == 2

    def test_pr_number_required(self):
        with pytest.raises(SystemExit):
            main(["--verdict", "PASS", "--findings-json", "{}"])

    def test_verdict_required(self):
        with pytest.raises(SystemExit):
            main(["--pr-number", "1", "--findings-json", "{}"])
