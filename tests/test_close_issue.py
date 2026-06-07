"""Tests for close_issue.py skill script (issue #2380)."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.github_core.api import RepoInfo

# ---------------------------------------------------------------------------
# Import the script via importlib (not a package)
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1]
    / ".claude" / "skills" / "github" / "scripts" / "issue"
)


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("close_issue")
main = _mod.main
build_parser = _mod.build_parser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


def _state_open():
    return _completed(stdout=json.dumps({"state": "OPEN"}), rc=0)


def _state_closed():
    return _completed(stdout=json.dumps({"state": "CLOSED"}), rc=0)


def _comments(*bodies: str):
    return _completed(stdout=json.dumps({"comments": [{"body": b} for b in bodies]}), rc=0)


def _paginated_comments(*pages: list[str]):
    return _completed(
        stdout=json.dumps([[{"body": body} for body in page] for page in pages]),
        rc=0,
    )


def _envelope(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


# ---------------------------------------------------------------------------
# build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_issue_required(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args([])

    def test_default_reason_is_completed(self):
        args = build_parser().parse_args(["--issue", "5"])
        assert args.reason == "completed"

    def test_reason_not_planned_accepted(self):
        args = build_parser().parse_args(["--issue", "5", "--reason", "not planned"])
        assert args.reason == "not planned"

    def test_invalid_reason_rejected(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["--issue", "5", "--reason", "wontfix"])

    def test_comment_and_comment_file_mutually_exclusive(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args(
                ["--issue", "5", "--comment", "x", "--comment-file", "f.txt"]
            )


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


class TestMain:
    def test_not_authenticated_exits_4(self):
        with patch(
            "close_issue.assert_gh_authenticated",
            side_effect=SystemExit(4),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--issue", "1"])
            assert exc.value.code == 4

    def test_close_success_no_comment(self, capsys):
        with patch(
            "close_issue.assert_gh_authenticated",
        ), patch(
            "close_issue.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            side_effect=[_state_open(), _completed(stdout="closed", rc=0)],
        ) as mock_run:
            rc = main(["--issue", "50"])
        assert rc == 0

        env = _envelope(capsys)
        assert env["Success"] is True
        assert env["Error"] is None
        assert env["Metadata"]["Script"] == "close_issue.py"
        data = env["Data"]
        assert data["issue"] == 50
        assert data["state"] == "closed"
        assert data["reason"] == "completed"
        assert data["commented"] is False

        # State check and close call ran (no comment POST).
        assert mock_run.call_count == 2
        close_args = mock_run.call_args_list[1].args[0]
        assert close_args[:3] == ["gh", "issue", "close"]
        assert "--reason" in close_args
        assert close_args[close_args.index("--reason") + 1] == "completed"

    def test_close_with_reason_not_planned(self, capsys):
        with patch(
            "close_issue.assert_gh_authenticated",
        ), patch(
            "close_issue.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            side_effect=[_state_open(), _completed(rc=0)],
        ) as mock_run:
            rc = main(["--issue", "7", "--reason", "not planned"])
        assert rc == 0
        data = _envelope(capsys)["Data"]
        assert data["reason"] == "not planned"
        close_args = mock_run.call_args_list[1].args[0]
        assert close_args[close_args.index("--reason") + 1] == "not planned"

    def test_close_with_comment_posts_then_closes(self, capsys):
        with patch(
            "close_issue.assert_gh_authenticated",
        ), patch(
            "close_issue.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            side_effect=[
                _state_open(),
                _completed(stdout="{}", rc=0),
                _completed(stdout="closed", rc=0),
            ],
        ) as mock_run:
            rc = main(["--issue", "9", "--comment", "Fixed in PR #10"])
        assert rc == 0
        data = _envelope(capsys)["Data"]
        assert data["commented"] is True

        # State check, close, then comment. Closing first avoids duplicate
        # comments if the close operation fails and callers retry.
        assert mock_run.call_count == 3
        close_args = mock_run.call_args_list[1].args[0]
        assert close_args[:3] == ["gh", "issue", "close"]
        post_args = mock_run.call_args_list[2].args[0]
        assert post_args[:2] == ["gh", "api"]
        assert "comments" in post_args[2]
        # The comment body is passed as JSON on stdin.
        post_input = mock_run.call_args_list[2].kwargs["input"]
        assert json.loads(post_input)["body"] == "Fixed in PR #10"

    def test_comment_from_file(self, tmp_path, capsys, monkeypatch):
        comment_path = tmp_path / "body.md"
        comment_path.write_text("Closing per triage.", encoding="utf-8")
        monkeypatch.setenv("GITHUB_WORKSPACE", str(tmp_path))
        with patch(
            "close_issue.assert_gh_authenticated",
        ), patch(
            "close_issue.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            side_effect=[
                _state_open(),
                _completed(stdout="{}", rc=0),
                _completed(stdout="closed", rc=0),
            ],
        ) as mock_run:
            rc = main(["--issue", "11", "--comment-file", comment_path.name])
        assert rc == 0
        assert _envelope(capsys)["Data"]["commented"] is True
        post_input = mock_run.call_args_list[2].kwargs["input"]
        assert json.loads(post_input)["body"] == "Closing per triage."

    def test_missing_comment_file_exits_2(self, capsys):
        with patch(
            "close_issue.assert_gh_authenticated",
        ), patch(
            "close_issue.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_state_open(),
        ) as mock_run:
            with pytest.raises(SystemExit) as exc:
                main(["--issue", "12", "--comment-file", "missing.md"])
            assert exc.value.code == 2
        mock_run.assert_not_called()
        env = _envelope(capsys)
        assert env["Success"] is False
        assert env["Error"]["Code"] == 2

    def test_comment_file_path_traversal_exits_2(self, tmp_path, capsys, monkeypatch):
        work = tmp_path / "work"
        work.mkdir()
        outside = tmp_path / "outside.md"
        outside.write_text("secret", encoding="utf-8")
        monkeypatch.setenv("GITHUB_WORKSPACE", str(work))
        with patch(
            "close_issue.assert_gh_authenticated",
        ), patch(
            "close_issue.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_state_open(),
        ) as mock_run:
            with pytest.raises(SystemExit) as exc:
                main(["--issue", "12", "--comment-file", "../outside.md"])
            assert exc.value.code == 2
        mock_run.assert_not_called()
        env = _envelope(capsys)
        assert env["Success"] is False
        assert env["Error"]["Type"] == "InvalidParams"

    def test_comment_base_uses_repo_root_when_workspace_missing(self, tmp_path, monkeypatch):
        nested = tmp_path / "nested"
        nested.mkdir()
        monkeypatch.chdir(nested)
        monkeypatch.delenv("GITHUB_WORKSPACE", raising=False)

        assert _mod._comment_base_dir() == Path(__file__).resolve().parents[1]

    def test_comment_base_falls_back_to_script_parent(self, tmp_path, monkeypatch):
        script_dir = tmp_path / "installed" / "scripts"
        script_dir.mkdir(parents=True)
        nested = tmp_path / "cwd"
        nested.mkdir()
        monkeypatch.chdir(nested)
        monkeypatch.delenv("GITHUB_WORKSPACE", raising=False)
        monkeypatch.setattr(_mod, "__file__", str(script_dir / "close_issue.py"))

        assert _mod._comment_base_dir() == script_dir.resolve()

    def test_comment_base_ignores_unrelated_parent_claude_dir(
        self, tmp_path, monkeypatch
    ):
        parent = tmp_path / "parent"
        script_dir = parent / "installed" / "scripts"
        script_dir.mkdir(parents=True)
        (parent / ".claude").mkdir()
        nested = tmp_path / "cwd"
        nested.mkdir()
        monkeypatch.chdir(nested)
        monkeypatch.delenv("GITHUB_WORKSPACE", raising=False)
        monkeypatch.setattr(_mod, "__file__", str(script_dir / "close_issue.py"))

        assert _mod._comment_base_dir() == script_dir.resolve()

    def test_comment_base_expands_workspace(self, tmp_path, monkeypatch):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        monkeypatch.setenv("GITHUB_WORKSPACE", str(workspace))

        assert _mod._comment_base_dir() == workspace.resolve()

    def test_issue_not_found_exits_2(self, capsys):
        with patch(
            "close_issue.assert_gh_authenticated",
        ), patch(
            "close_issue.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_completed(stderr="Could not resolve to an Issue", rc=1),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--issue", "404"])
            assert exc.value.code == 2
        env = _envelope(capsys)
        assert env["Success"] is False
        assert env["Error"]["Code"] == 2
        assert env["Error"]["Type"] == "NotFound"

    def test_issue_state_auth_failure_exits_4(self, capsys):
        with patch(
            "close_issue.assert_gh_authenticated",
        ), patch(
            "close_issue.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_completed(stderr="not logged in", rc=1),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--issue", "401"])
            assert exc.value.code == 4
        env = _envelope(capsys)
        assert env["Success"] is False
        assert env["Error"]["Code"] == 4
        assert env["Error"]["Type"] == "AuthError"

    def test_issue_state_author_error_is_api_error(self, capsys):
        with patch(
            "close_issue.assert_gh_authenticated",
        ), patch(
            "close_issue.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_completed(stderr="author is invalid", rc=1),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--issue", "401"])
            assert exc.value.code == 3
        env = _envelope(capsys)
        assert env["Success"] is False
        assert env["Error"]["Code"] == 3
        assert env["Error"]["Type"] == "ApiError"

    def test_issue_state_non_dict_json_treated_as_open(self, capsys):
        with patch(
            "close_issue.assert_gh_authenticated",
        ), patch(
            "close_issue.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            side_effect=[
                _completed(stdout="null", rc=0),
                _completed(stdout="closed", rc=0),
            ],
        ) as mock_run:
            rc = main(["--issue", "18"])
        assert rc == 0
        assert mock_run.call_count == 2
        assert _envelope(capsys)["Data"]["action"] == "closed"

    def test_already_closed_with_missing_comment_posts_once(self, capsys):
        with patch(
            "close_issue.assert_gh_authenticated",
        ), patch(
            "close_issue.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            side_effect=[
                _state_closed(),
                _comments(),
                _completed(stdout="{}", rc=0),
            ],
        ) as mock_run:
            rc = main(["--issue", "18", "--comment", "Closing note"])
        assert rc == 0
        assert mock_run.call_count == 3
        post_args = mock_run.call_args_list[2].args[0]
        assert post_args[:2] == ["gh", "api"]
        env = _envelope(capsys)
        assert env["Data"]["action"] == "already_closed"
        assert env["Data"]["commented"] is True
        assert env["Data"]["commentAlreadyPresent"] is False

    def test_already_closed_with_existing_comment_skips_duplicate(self, capsys):
        with patch(
            "close_issue.assert_gh_authenticated",
        ), patch(
            "close_issue.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            side_effect=[
                _state_closed(),
                _comments("Closing note"),
            ],
        ) as mock_run:
            rc = main(["--issue", "18", "--comment", "Closing note"])
        assert rc == 0
        assert mock_run.call_count == 2
        env = _envelope(capsys)
        assert env["Data"]["commented"] is False
        assert env["Data"]["commentAlreadyPresent"] is True

    def test_already_closed_dedup_checks_all_comment_pages(self, capsys):
        with patch(
            "close_issue.assert_gh_authenticated",
        ), patch(
            "close_issue.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            side_effect=[
                _state_closed(),
                _paginated_comments(["older note"], ["Closing note"]),
            ],
        ) as mock_run:
            rc = main(["--issue", "18", "--comment", "Closing note"])
        assert rc == 0
        assert mock_run.call_count == 2
        comment_lookup_args = mock_run.call_args_list[1].args[0]
        assert comment_lookup_args[:2] == ["gh", "api"]
        assert "--paginate" in comment_lookup_args
        assert "--slurp" in comment_lookup_args
        env = _envelope(capsys)
        assert env["Data"]["commented"] is False
        assert env["Data"]["commentAlreadyPresent"] is True

    def test_invalid_utf8_comment_file_exits_2(self, tmp_path, capsys, monkeypatch):
        comment_path = tmp_path / "body.md"
        comment_path.write_bytes(b"\xff\xfe")
        monkeypatch.setenv("GITHUB_WORKSPACE", str(tmp_path))
        with patch(
            "close_issue.assert_gh_authenticated",
        ), patch(
            "close_issue.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_state_open(),
        ) as mock_run:
            with pytest.raises(SystemExit) as exc:
                main(["--issue", "12", "--comment-file", comment_path.name])
            assert exc.value.code == 2
        mock_run.assert_not_called()
        env = _envelope(capsys)
        assert env["Success"] is False
        assert env["Error"]["Code"] == 2
        assert env["Error"]["Type"] == "InvalidParams"

    def test_close_api_failure_exits_3(self, capsys):
        with patch(
            "close_issue.assert_gh_authenticated",
        ), patch(
            "close_issue.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            side_effect=[_state_open(), _completed(stderr="HTTP 404", rc=1)],
        ):
            rc = main(["--issue", "13"])
        assert rc == 3
        env = _envelope(capsys)
        assert env["Success"] is False
        assert env["Error"]["Code"] == 3
        assert env["Error"]["Type"] == "ApiError"

    def test_comment_post_failure_exits_3_after_close(self, capsys):
        """A failed comment POST returns code 3 after a successful close."""
        with patch(
            "close_issue.assert_gh_authenticated",
        ), patch(
            "close_issue.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            side_effect=[
                _state_open(),
                _completed(rc=0),
                _completed(stderr="HTTP 403", rc=1),
            ],
        ) as mock_run:
            with pytest.raises(SystemExit) as exc:
                main(["--issue", "14", "--comment", "note"])
            assert exc.value.code == 3
        # State check, close, and comment POST ran.
        assert mock_run.call_count == 3
        env = _envelope(capsys)
        assert env["Success"] is False
        assert env["Error"]["Code"] == 3

    def test_comment_post_auth_failure_exits_4(self, capsys):
        with patch(
            "close_issue.assert_gh_authenticated",
        ), patch(
            "close_issue.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            side_effect=[
                _state_open(),
                _completed(rc=0),
                _completed(stderr="HTTP 401: requires authentication", rc=1),
            ],
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--issue", "14", "--comment", "note"])
            assert exc.value.code == 4
        env = _envelope(capsys)
        assert env["Success"] is False
        assert env["Error"]["Code"] == 4
        assert env["Error"]["Type"] == "AuthError"

    def test_whitespace_only_comment_is_not_posted(self, capsys):
        with patch(
            "close_issue.assert_gh_authenticated",
        ), patch(
            "close_issue.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            side_effect=[_state_open(), _completed(rc=0)],
        ) as mock_run:
            rc = main(["--issue", "15", "--comment", "   "])
        assert rc == 0
        # No comment POST; only state check and close call.
        assert mock_run.call_count == 2
        assert _envelope(capsys)["Data"]["commented"] is False

    def test_close_auth_failure_returns_4(self, capsys):
        with patch(
            "close_issue.assert_gh_authenticated",
        ), patch(
            "close_issue.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            side_effect=[
                _state_open(),
                _completed(stderr="Bad credentials", rc=1),
            ],
        ):
            rc = main(["--issue", "17"])
        assert rc == 4
        env = _envelope(capsys)
        assert env["Success"] is False
        assert env["Error"]["Code"] == 4
        assert env["Error"]["Type"] == "AuthError"

    def test_already_closed_posts_missing_comment_without_close(self, capsys):
        with patch(
            "close_issue.assert_gh_authenticated",
        ), patch(
            "close_issue.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            side_effect=[
                _state_closed(),
                _comments(),
                _completed(stdout="{}", rc=0),
            ],
        ) as mock_run:
            rc = main(["--issue", "16", "--comment", "retry note"])
        assert rc == 0
        data = _envelope(capsys)["Data"]
        assert data["state"] == "closed"
        assert data["action"] == "already_closed"
        assert data["commented"] is True
        assert data["commentAlreadyPresent"] is False
        assert mock_run.call_count == 3
        assert mock_run.call_args_list[2].args[0][:2] == ["gh", "api"]


# ---------------------------------------------------------------------------
# extract_claims (pure parser; no I/O)
# ---------------------------------------------------------------------------


class TestExtractClaims:
    """The claim parser pulls SHAs and PR numbers out of a comment body."""

    def test_no_claims_returns_empty(self):
        claims = _mod.extract_claims("Closing as completed. No further action needed.")
        assert claims.commits == ()
        assert claims.prs == ()

    def test_resolved_by_commit_short_sha(self):
        claims = _mod.extract_claims("Resolved by commit 61c56cbe (Feb 19, 2026).")
        assert claims.commits == ("61c56cbe",)

    def test_resolved_by_commit_full_sha(self):
        claims = _mod.extract_claims(
            "Resolved by commit deadbeefcafe1234567890abcdef0123456789ab.",
        )
        assert claims.commits == ("deadbeefcafe1234567890abcdef0123456789ab",)

    def test_resolved_by_pr_number(self):
        claims = _mod.extract_claims("Resolved by PR #1024 which standardized outputs.")
        assert claims.prs == (1024,)

    def test_fixed_in_pr_phrasing(self):
        claims = _mod.extract_claims("Fixed in PR #42.")
        assert claims.prs == (42,)

    def test_closed_via_pr_phrasing(self):
        claims = _mod.extract_claims("Auto-closed via Closes #907 on PR #1024.")
        # "Closes #N" trailer text mentions the issue being closed, not a fix
        # source; only PR #1024 is the claimed resolver.
        assert claims.prs == (1024,)

    def test_extracts_multiple_distinct_shas(self):
        claims = _mod.extract_claims(
            "Resolved by commit abc1234 and follow-up commit def5678.",
        )
        assert claims.commits == ("abc1234", "def5678")

    def test_ignores_short_hex_words(self):
        # 6 chars is below the 7-char short-SHA floor; not a claim.
        claims = _mod.extract_claims("Resolved by commit abc123.")
        assert claims.commits == ()

    def test_ignores_decimal_numbers_outside_pr_context(self):
        claims = _mod.extract_claims("Closed because count was 1024 items.")
        assert claims.prs == ()

    def test_dedups_repeated_claims(self):
        claims = _mod.extract_claims(
            "Resolved by commit abc1234. See commit abc1234 for context.",
        )
        assert claims.commits == ("abc1234",)


# ---------------------------------------------------------------------------
# verify_claims (gh / git probes)
# ---------------------------------------------------------------------------


def _commit_found():
    return _completed(stdout='{"sha":"abc1234"}', rc=0)


def _commit_missing():
    return _completed(stderr="Not Found", rc=1)


def _pr_merged():
    return _completed(stdout=json.dumps({"state": "closed", "merged": True}), rc=0)


def _pr_open():
    return _completed(stdout=json.dumps({"state": "open", "merged": False}), rc=0)


def _pr_closed_unmerged():
    return _completed(stdout=json.dumps({"state": "closed", "merged": False}), rc=0)


class TestVerifyClaims:
    """The verifier confirms each claim resolves against GitHub before close."""

    def test_no_claims_returns_clean(self):
        result = _mod.verify_claims(
            _mod.Claims(commits=(), prs=()),
            owner="o",
            repo="r",
        )
        assert result.failures == ()

    def test_resolvable_commit_passes(self):
        with patch("subprocess.run", side_effect=[_commit_found()]) as mock_run:
            result = _mod.verify_claims(
                _mod.Claims(commits=("abc1234",), prs=()),
                owner="o",
                repo="r",
            )
        assert result.failures == ()
        # Probe used gh api repos/o/r/commits/abc1234.
        probe_args = mock_run.call_args_list[0].args[0]
        assert probe_args[:2] == ["gh", "api"]
        assert probe_args[2] == "repos/o/r/commits/abc1234"

    def test_missing_commit_fails(self):
        with patch("subprocess.run", side_effect=[_commit_missing()]):
            result = _mod.verify_claims(
                _mod.Claims(commits=("61c56cbe",), prs=()),
                owner="o",
                repo="r",
            )
        assert len(result.failures) == 1
        assert "61c56cbe" in result.failures[0]
        assert "commit" in result.failures[0].lower()

    def test_merged_pr_passes(self):
        with patch("subprocess.run", side_effect=[_pr_merged()]):
            result = _mod.verify_claims(
                _mod.Claims(commits=(), prs=(1024,)),
                owner="o",
                repo="r",
            )
        assert result.failures == ()

    def test_open_pr_fails(self):
        with patch("subprocess.run", side_effect=[_pr_open()]):
            result = _mod.verify_claims(
                _mod.Claims(commits=(), prs=(1024,)),
                owner="o",
                repo="r",
            )
        assert len(result.failures) == 1
        assert "#1024" in result.failures[0]
        assert "merged" in result.failures[0].lower()

    def test_closed_unmerged_pr_fails(self):
        with patch("subprocess.run", side_effect=[_pr_closed_unmerged()]):
            result = _mod.verify_claims(
                _mod.Claims(commits=(), prs=(1024,)),
                owner="o",
                repo="r",
            )
        assert len(result.failures) == 1

    def test_multiple_failures_collected(self):
        with patch(
            "subprocess.run",
            side_effect=[_commit_missing(), _pr_open()],
        ):
            result = _mod.verify_claims(
                _mod.Claims(commits=("61c56cbe",), prs=(1024,)),
                owner="o",
                repo="r",
            )
        assert len(result.failures) == 2


# ---------------------------------------------------------------------------
# main with --verify-claims gate (integration; the audit failure mode)
# ---------------------------------------------------------------------------


class TestVerifyClaimsGate:
    """When --verify-claims is set, an unverifiable claim aborts the close."""

    def test_verify_claims_off_skips_verification(self, capsys):
        # The opt-out path keeps backward compatibility: a comment that
        # claims a non-existent commit still closes when --verify-claims is
        # absent. This preserves the legacy contract for callers that have
        # not yet adopted the gate.
        with patch(
            "close_issue.assert_gh_authenticated",
        ), patch(
            "close_issue.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            side_effect=[
                _state_open(),
                _completed(rc=0),
                _completed(stdout="{}", rc=0),
            ],
        ) as mock_run:
            rc = main(
                [
                    "--issue",
                    "134",
                    "--comment",
                    "Resolved by commit 61c56cbe (Feb 19, 2026).",
                ],
            )
        assert rc == 0
        # State check + close + comment POST; no verification probes.
        assert mock_run.call_count == 3

    def test_verify_claims_blocks_missing_commit(self, capsys):
        # The exact failure mode from issue #2481 (#134 audit row).
        with patch(
            "close_issue.assert_gh_authenticated",
        ), patch(
            "close_issue.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            side_effect=[_state_open(), _commit_missing()],
        ) as mock_run:
            rc = main(
                [
                    "--issue",
                    "134",
                    "--verify-claims",
                    "--comment",
                    "Resolved by commit 61c56cbe (Feb 19, 2026).",
                ],
            )
        assert rc == 1
        # State check + commit probe; NO close, NO comment POST.
        assert mock_run.call_count == 2
        close_calls = [
            call.args[0]
            for call in mock_run.call_args_list
            if call.args and call.args[0][:3] == ["gh", "issue", "close"]
        ]
        assert close_calls == []

        env = _envelope(capsys)
        assert env["Success"] is False
        assert env["Error"]["Code"] == 1
        assert env["Error"]["Type"] == "VerificationFailed"
        # Failure detail names the unverifiable claim so a human auditor can
        # see exactly which claim broke the gate.
        assert "61c56cbe" in env["Error"]["Message"]

    def test_verify_claims_blocks_unmerged_pr(self, capsys):
        with patch(
            "close_issue.assert_gh_authenticated",
        ), patch(
            "close_issue.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            side_effect=[_state_open(), _pr_open()],
        ) as mock_run:
            rc = main(
                [
                    "--issue",
                    "139",
                    "--verify-claims",
                    "--comment",
                    "Resolved by PR #1024.",
                ],
            )
        assert rc == 1
        # State check + PR probe; no close, no comment POST.
        assert mock_run.call_count == 2
        env = _envelope(capsys)
        assert env["Error"]["Type"] == "VerificationFailed"
        assert "#1024" in env["Error"]["Message"]

    def test_verify_claims_passes_when_commit_and_pr_resolve(self, capsys):
        with patch(
            "close_issue.assert_gh_authenticated",
        ), patch(
            "close_issue.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            side_effect=[
                _state_open(),
                _commit_found(),
                _pr_merged(),
                _completed(rc=0),
                _completed(stdout="{}", rc=0),
            ],
        ) as mock_run:
            rc = main(
                [
                    "--issue",
                    "50",
                    "--verify-claims",
                    "--comment",
                    "Resolved by commit abc1234 (PR #999).",
                ],
            )
        assert rc == 0
        # State + commit probe + PR probe + close + comment POST.
        assert mock_run.call_count == 5
        data = _envelope(capsys)["Data"]
        assert data["state"] == "closed"
        assert data["commented"] is True

    def test_verify_claims_passes_when_comment_has_no_claims(self, capsys):
        # An "I looked and there are none" comment (e.g. #702 row) needs no
        # commit/PR verification; the gate is for cited artifacts only.
        with patch(
            "close_issue.assert_gh_authenticated",
        ), patch(
            "close_issue.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            side_effect=[
                _state_open(),
                _completed(rc=0),
                _completed(stdout="{}", rc=0),
            ],
        ) as mock_run:
            rc = main(
                [
                    "--issue",
                    "702",
                    "--verify-claims",
                    "--comment",
                    "Closing because the cited gap is no longer reproducible.",
                ],
            )
        assert rc == 0
        # No commit/PR probes since the comment cites neither.
        assert mock_run.call_count == 3

    def test_verify_claims_with_no_comment_skips_gate(self, capsys):
        # No comment = no claim to verify. Backwards compatible with bare
        # gh issue close usage; the gate only applies to comment claims.
        with patch(
            "close_issue.assert_gh_authenticated",
        ), patch(
            "close_issue.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            side_effect=[_state_open(), _completed(rc=0)],
        ) as mock_run:
            rc = main(["--issue", "60", "--verify-claims"])
        assert rc == 0
        assert mock_run.call_count == 2
