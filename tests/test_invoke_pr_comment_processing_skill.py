"""Tests for invoke_pr_comment_processing.py skill script."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Import the script via importlib (not a package)
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1]
    / ".claude" / "skills" / "github" / "scripts" / "pr"
)


def _import_script(name: str, *, module_alias: str | None = None):
    alias = module_alias or name
    spec = importlib.util.spec_from_file_location(alias, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)
    return mod


# Use alias to avoid collision with the consumer-script test module of the same name
_MODULE_ALIAS = "invoke_pr_comment_processing_skill"
_mod = _import_script("invoke_pr_comment_processing", module_alias=_MODULE_ALIAS)
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


# ---------------------------------------------------------------------------
# Tests: build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_pr_number_required(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["--verdict", "PASS", "--findings-json", "{}"])

    def test_verdict_required(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["--pr-number", "1", "--findings-json", "{}"])

    def test_valid_args(self):
        args = build_parser().parse_args([
            "--pr-number", "42", "--verdict", "PASS", "--findings-json", '{"comments": []}',
        ])
        assert args.pr_number == 42
        assert args.verdict == "PASS"


# ---------------------------------------------------------------------------
# Tests: parse_findings
# ---------------------------------------------------------------------------


class TestParseFindings:
    def test_plain_json(self):
        result = parse_findings('{"comments": []}')
        assert result == {"comments": []}

    def test_code_fence_json(self):
        result = parse_findings('```json\n{"comments": []}\n```')
        assert result == {"comments": []}

    def test_invalid_json_exits_2(self):
        with pytest.raises(SystemExit) as exc:
            parse_findings("not json at all")
        assert exc.value.code == 2


# ---------------------------------------------------------------------------
# Tests: add_comment_reaction
# ---------------------------------------------------------------------------


class TestAddCommentReaction:
    def test_success_on_first_endpoint(self):
        with patch("subprocess.run", return_value=_completed(rc=0)):
            assert add_comment_reaction("o", "r", 123) is True

    def test_fallback_to_issue_endpoint(self):
        calls = [_completed(rc=1, stderr="not found"), _completed(rc=0)]
        with patch("subprocess.run", side_effect=calls):
            assert add_comment_reaction("o", "r", 123) is True

    def test_both_endpoints_fail(self):
        with patch("subprocess.run", return_value=_completed(rc=1, stderr="fail")):
            assert add_comment_reaction("o", "r", 123) is False


# ---------------------------------------------------------------------------
# Tests: reply_to_comment
# ---------------------------------------------------------------------------


class TestReplyToComment:
    def test_success(self):
        with patch("subprocess.run", return_value=_completed(rc=0)):
            assert reply_to_comment("o", "r", 1, 123, "reply text") is True

    def test_failure(self):
        with patch("subprocess.run", return_value=_completed(rc=1, stderr="error")):
            assert reply_to_comment("o", "r", 1, 123, "reply text") is False


# ---------------------------------------------------------------------------
# Tests: process_comments
# ---------------------------------------------------------------------------


class TestProcessComments:
    def test_empty_comments(self):
        stats = process_comments("o", "r", 1, {"comments": []})
        assert stats["acknowledged"] == 0
        assert stats["errors"] == 0

    def test_stale_comment_acknowledged_and_skipped(self):
        findings = {"comments": [{"id": 1, "classification": "stale"}]}
        with patch("subprocess.run", return_value=_completed(rc=0)):
            stats = process_comments("o", "r", 1, findings)
        assert stats["acknowledged"] == 1
        assert stats["skipped"] == 1

    def test_wontfix_with_resolution(self):
        findings = {"comments": [
            {"id": 1, "classification": "wontfix", "resolution": "Out of scope"},
        ]}
        with patch("subprocess.run", return_value=_completed(rc=0)):
            stats = process_comments("o", "r", 1, findings)
        assert stats["acknowledged"] == 1
        assert stats["replied"] == 1

    def test_comment_missing_id(self):
        findings = {"comments": [{"classification": "stale"}]}
        stats = process_comments("o", "r", 1, findings)
        assert stats["errors"] == 1


# ---------------------------------------------------------------------------
# Tests: main
# ---------------------------------------------------------------------------


class TestMain:
    def test_non_pass_warn_verdict_returns_0(self):
        rc = main(["--pr-number", "1", "--verdict", "FAIL", "--findings-json", "{}"])
        assert rc == 0

    def test_no_comments_returns_0(self):
        with patch(
            "invoke_pr_comment_processing_skill.resolve_repo_params",
            return_value={"Owner": "o", "Repo": "r"},
        ):
            rc = main([
                "--pr-number", "1", "--verdict", "PASS",
                "--findings-json", '{"comments": []}',
            ])
        assert rc == 0

    def test_processing_errors_returns_3(self):
        findings = json.dumps({"comments": [{"id": 1, "classification": "stale"}]})
        with patch(
            "invoke_pr_comment_processing_skill.resolve_repo_params",
            return_value={"Owner": "o", "Repo": "r"},
        ), patch(
            "subprocess.run",
            return_value=_completed(rc=1, stderr="fail"),
        ):
            rc = main([
                "--pr-number", "1", "--verdict", "PASS",
                "--findings-json", findings,
            ])
        assert rc == 3
