"""Tests for audit_closing_claims.py and edit_pr_body.py (issue #4462)."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from scripts.github_core.api import RepoInfo

# ---------------------------------------------------------------------------
# Import the scripts via importlib (not a package)
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1]
    / ".claude" / "skills" / "github" / "scripts" / "pr"
)


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_audit_mod = _import_script("audit_closing_claims")
_edit_mod = _import_script("edit_pr_body")

_extract_body_claims = _audit_mod._extract_body_claims
_strip_code = _audit_mod._strip_code
audit_main = _audit_mod.main

_body_sha = _edit_mod._body_sha
fetch_current_body = _edit_mod.fetch_current_body
edit_main = _edit_mod.main


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


# ---------------------------------------------------------------------------
# Tests: _strip_code
# ---------------------------------------------------------------------------


class TestStripCode:
    def test_fenced_block_removed(self):
        text = "Before\n```\nFixes #10\n```\nAfter"
        clean = _strip_code(text)
        assert "#10" not in clean
        assert "After" in clean

    def test_inline_code_removed(self):
        text = "See `Fixes #5` for details"
        clean = _strip_code(text)
        assert "#5" not in clean

    def test_escaped_hash_removed(self):
        text = "This is \\#42 but not a real ref"
        clean = _strip_code(text)
        assert "#42" not in clean


# ---------------------------------------------------------------------------
# Tests: _extract_body_claims
# ---------------------------------------------------------------------------


class TestExtractBodyClaims:
    def test_fixes_keyword_registers(self):
        claims = _extract_body_claims("Fixes #42")
        assert len(claims) == 1
        assert claims[0]["number"] == 42
        assert claims[0]["is_closing_keyword"] is True

    def test_refs_keyword_is_not_closing(self):
        """Positive: Refs #N is extracted but marked non-closing."""
        claims = _extract_body_claims("Refs #99")
        assert len(claims) == 1
        assert claims[0]["is_closing_keyword"] is False

    def test_multiple_on_one_line(self):
        """Two separate Fixes lines each register one claim."""
        claims = _extract_body_claims("Fixes #1\nFixes #2\n")
        assert len(claims) == 2

    def test_code_block_skipped(self):
        claims = _extract_body_claims("```\nFixes #10\n```")
        assert len(claims) == 0

    def test_inline_code_skipped(self):
        claims = _extract_body_claims("See `Fixes #5`")
        assert len(claims) == 0

    def test_closes_keyword_registers(self):
        claims = _extract_body_claims("Closes #7")
        assert claims[0]["is_closing_keyword"] is True

    def test_cross_repo_ref_captured(self):
        claims = _extract_body_claims("Fixes other/repo#5")
        assert claims[0]["repo"] == "other/repo"

    def test_empty_body(self):
        assert _extract_body_claims("") == []

    def test_none_body(self):
        assert _extract_body_claims(None) == []


# ---------------------------------------------------------------------------
# Tests: _body_sha
# ---------------------------------------------------------------------------


class TestBodySha:
    def test_sha_is_hex(self):
        sha = _body_sha("hello")
        assert len(sha) == 64
        assert all(c in "0123456789abcdef" for c in sha)

    def test_empty_string(self):
        expected = hashlib.sha256(b"").hexdigest()
        assert _body_sha("") == expected

    def test_different_texts_different_sha(self):
        assert _body_sha("a") != _body_sha("b")


# ---------------------------------------------------------------------------
# Tests: audit_main
# ---------------------------------------------------------------------------


class TestAuditMain:
    def _graphql_response(self, prs: list[dict]) -> str:
        return json.dumps({
            "data": {
                "repository": {
                    "pullRequests": {
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                        "nodes": prs,
                    }
                }
            }
        })

    def test_no_prs_exits_0(self, capsys):
        with patch("audit_closing_claims.assert_gh_authenticated"), \
             patch("audit_closing_claims.resolve_repo_params",
                   return_value=RepoInfo(owner="o", repo="r")), \
             patch("subprocess.run",
                   return_value=_completed(stdout=self._graphql_response([]))):
            rc = audit_main(["--output-format", "json"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["Success"] is True
        assert out["Data"]["total_prs"] == 0

    def test_pr_with_no_mismatch(self, capsys):
        pr_node = {
            "number": 10,
            "title": "clean PR",
            "baseRefName": "main",
            "body": "Fixes #5\n",
            "closingIssuesReferences": {"nodes": [{"number": 5}]},
        }
        with patch("audit_closing_claims.assert_gh_authenticated"), \
             patch("audit_closing_claims.resolve_repo_params",
                   return_value=RepoInfo(owner="o", repo="r")), \
             patch("subprocess.run",
                   return_value=_completed(stdout=self._graphql_response([pr_node]))):
            rc = audit_main(["--output-format", "json"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        report = out["Data"]["report"]
        assert report[0]["mismatches"] == []

    def test_pr_with_mismatch(self, capsys):
        """Fixes #5 in body but #5 not in closingIssuesReferences."""
        pr_node = {
            "number": 11,
            "title": "broken PR",
            "baseRefName": "main",
            "body": "Fixes #5\n",
            "closingIssuesReferences": {"nodes": []},
        }
        with patch("audit_closing_claims.assert_gh_authenticated"), \
             patch("audit_closing_claims.resolve_repo_params",
                   return_value=RepoInfo(owner="o", repo="r")), \
             patch("subprocess.run",
                   return_value=_completed(stdout=self._graphql_response([pr_node]))):
            rc = audit_main(["--output-format", "json"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        report = out["Data"]["report"]
        assert len(report[0]["mismatches"]) == 1
        assert report[0]["mismatches"][0]["claimed_issue"] == 5

    def test_api_failure_exits_3(self, capsys):
        with patch("audit_closing_claims.assert_gh_authenticated"), \
             patch("audit_closing_claims.resolve_repo_params",
                   return_value=RepoInfo(owner="o", repo="r")), \
             patch("subprocess.run", return_value=_completed(rc=1, stderr="API down")):
            rc = audit_main(["--output-format", "json"])
        assert rc == 3

    def test_refs_keyword_mismatch_reported(self, capsys):
        """Refs #N is captured but marked non-closing."""
        pr_node = {
            "number": 12,
            "title": "refs only",
            "baseRefName": "main",
            "body": "Refs #9\n",
            "closingIssuesReferences": {"nodes": []},
        }
        with patch("audit_closing_claims.assert_gh_authenticated"), \
             patch("audit_closing_claims.resolve_repo_params",
                   return_value=RepoInfo(owner="o", repo="r")), \
             patch("subprocess.run",
                   return_value=_completed(stdout=self._graphql_response([pr_node]))):
            rc = audit_main(["--output-format", "json"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        mismatches = out["Data"]["report"][0]["mismatches"]
        assert len(mismatches) == 1
        assert mismatches[0]["is_closing_keyword"] is False


# ---------------------------------------------------------------------------
# Tests: edit_main
# ---------------------------------------------------------------------------


class TestEditMain:
    _CURRENT_BODY = "old body text"
    _CURRENT_SHA = hashlib.sha256(_CURRENT_BODY.encode()).hexdigest()

    def _body_view_response(self) -> str:
        return json.dumps({"body": self._CURRENT_BODY})

    def test_successful_edit_exits_0(self, capsys):
        with patch("edit_pr_body.assert_gh_authenticated"), \
             patch("edit_pr_body.resolve_repo_params",
                   return_value=RepoInfo(owner="o", repo="r")), \
             patch("subprocess.run", side_effect=lambda cmd, **kw: (
                 _completed(stdout=self._body_view_response())
                 if "view" in cmd else _completed(rc=0)
             )):
            rc = edit_main(
                ["--pull-request", "1", "--body", "new body", "--output-format", "json"]
            )
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["Success"] is True
        assert out["Data"]["pull_request"] == 1

    def test_correct_expected_sha_allows_edit(self, capsys):
        with patch("edit_pr_body.assert_gh_authenticated"), \
             patch("edit_pr_body.resolve_repo_params",
                   return_value=RepoInfo(owner="o", repo="r")), \
             patch("subprocess.run", side_effect=lambda cmd, **kw: (
                 _completed(stdout=self._body_view_response())
                 if "view" in cmd else _completed(rc=0)
             )):
            rc = edit_main(
                ["--pull-request", "1", "--body", "new body",
                 "--expected-sha", self._CURRENT_SHA, "--output-format", "json"]
            )
        assert rc == 0

    def test_stale_expected_sha_exits_1(self, capsys):
        """Negative: expected sha does not match current body."""
        wrong_sha = "a" * 64
        with patch("edit_pr_body.assert_gh_authenticated"), \
             patch("edit_pr_body.resolve_repo_params",
                   return_value=RepoInfo(owner="o", repo="r")), \
             patch("subprocess.run",
                   return_value=_completed(stdout=self._body_view_response())):
            rc = edit_main(
                ["--pull-request", "1", "--body", "new body",
                 "--expected-sha", wrong_sha, "--output-format", "json"]
            )
        assert rc == 1
        out = json.loads(capsys.readouterr().out)
        assert out["Error"]["Type"] == "VerificationFailed"

    def test_missing_body_file_exits_2(self, capsys):
        with patch("edit_pr_body.assert_gh_authenticated"), \
             patch("edit_pr_body.resolve_repo_params",
                   return_value=RepoInfo(owner="o", repo="r")), \
             patch("subprocess.run",
                   return_value=_completed(stdout=self._body_view_response())):
            rc = edit_main(
                ["--pull-request", "1", "--body-file", "/no/such/file.txt",
                 "--output-format", "json"]
            )
        assert rc == 2

    def test_api_fetch_failure_exits_3(self, capsys):
        with patch("edit_pr_body.assert_gh_authenticated"), \
             patch("edit_pr_body.resolve_repo_params",
                   return_value=RepoInfo(owner="o", repo="r")), \
             patch("subprocess.run", return_value=_completed(rc=1, stderr="not found")):
            rc = edit_main(
                ["--pull-request", "1", "--body", "x", "--output-format", "json"]
            )
        assert rc == 3

    def test_api_write_failure_exits_3(self, capsys):
        """Edge: fetch succeeds but write fails."""
        call_count = [0]

        def side(cmd, **kw):
            call_count[0] += 1
            if "view" in cmd:
                return _completed(stdout=self._body_view_response())
            return _completed(rc=1, stderr="write failed")

        with patch("edit_pr_body.assert_gh_authenticated"), \
             patch("edit_pr_body.resolve_repo_params",
                   return_value=RepoInfo(owner="o", repo="r")), \
             patch("subprocess.run", side_effect=side):
            rc = edit_main(
                ["--pull-request", "1", "--body", "new body", "--output-format", "json"]
            )
        assert rc == 3

    def test_body_file_is_read_and_written(self, tmp_path, capsys):
        """Edge: --body-file reads the file and writes it to the PR."""
        body_file = tmp_path / "body.md"
        body_file.write_text("file body content", encoding="utf-8")
        written_bodies = []

        def side(cmd, **kw):
            if "view" in cmd:
                return _completed(stdout=self._body_view_response())
            # gh pr edit --body <text>
            if "--body" in cmd:
                idx = list(cmd).index("--body")
                written_bodies.append(cmd[idx + 1])
            return _completed(rc=0)

        with patch("edit_pr_body.assert_gh_authenticated"), \
             patch("edit_pr_body.resolve_repo_params",
                   return_value=RepoInfo(owner="o", repo="r")), \
             patch("subprocess.run", side_effect=side):
            rc = edit_main(
                ["--pull-request", "1", "--body-file", str(body_file),
                 "--output-format", "json"]
            )
        assert rc == 0
        assert written_bodies == ["file body content"]
