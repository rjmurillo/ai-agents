"""Tests for merge_pr.py skill script."""

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


_mod = _import_script("merge_pr")
main = _mod.main
build_parser = _mod.build_parser
get_allowed_merge_methods = _mod.get_allowed_merge_methods
validate_strategy = _mod.validate_strategy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


# Default settings allowing all merge methods
_ALL_METHODS_ALLOWED = {
    "allow_merge_commit": True,
    "allow_squash_merge": True,
    "allow_rebase_merge": True,
}


# ---------------------------------------------------------------------------
# Tests: build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_pull_request_required(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args([])

    def test_strategy_default_is_none(self):
        """Default strategy is now None — main() resolves it against repo policy.

        Regression: #2449 — hard-coded default of 'merge' violated repo
        policies that only allow squash.
        """
        args = build_parser().parse_args(["--pull-request", "50"])
        assert args.strategy is None

    def test_strategy_squash(self):
        args = build_parser().parse_args([
            "--pull-request", "50", "--strategy", "squash",
        ])
        assert args.strategy == "squash"

    def test_invalid_strategy(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args([
                "--pull-request", "50", "--strategy", "invalid",
            ])


# ---------------------------------------------------------------------------
# Tests: main
# ---------------------------------------------------------------------------


class TestMain:
    def test_not_authenticated_exits_4(self):
        with patch(
            "merge_pr.assert_gh_authenticated",
            side_effect=SystemExit(4),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "1"])
            assert exc.value.code == 4

    def test_pr_not_found_exits_2(self):
        with patch(
            "merge_pr.assert_gh_authenticated",
        ), patch(
            "merge_pr.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "merge_pr.get_allowed_merge_methods", return_value=_ALL_METHODS_ALLOWED,
        ), patch(
            "subprocess.run",
            return_value=_completed(rc=1, stderr="not found"),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "999"])
            assert exc.value.code == 2

    def test_already_merged_returns_0(self, capsys):
        state_json = json.dumps({
            "state": "MERGED", "mergeable": "", "mergeStateStatus": "", "headRefName": "f",
        })
        with patch(
            "merge_pr.assert_gh_authenticated",
        ), patch(
            "merge_pr.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "merge_pr.get_allowed_merge_methods", return_value=_ALL_METHODS_ALLOWED,
        ), patch(
            "subprocess.run",
            return_value=_completed(stdout=state_json, rc=0),
        ):
            rc = main(["--pull-request", "50"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["Data"]["action"] == "none"

    def test_closed_pr_exits_6(self):
        state_json = json.dumps({
            "state": "CLOSED", "mergeable": "", "mergeStateStatus": "", "headRefName": "f",
        })
        with patch(
            "merge_pr.assert_gh_authenticated",
        ), patch(
            "merge_pr.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "merge_pr.get_allowed_merge_methods", return_value=_ALL_METHODS_ALLOWED,
        ), patch(
            "subprocess.run",
            return_value=_completed(stdout=state_json, rc=0),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "50"])
            assert exc.value.code == 6

    def test_merge_success(self, capsys):
        state_json = json.dumps({
            "state": "OPEN", "mergeable": "MERGEABLE",
            "mergeStateStatus": "CLEAN", "headRefName": "feature",
        })
        call_count = 0

        def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _completed(stdout=state_json, rc=0)
            return _completed(rc=0)

        with patch(
            "merge_pr.assert_gh_authenticated",
        ), patch(
            "merge_pr.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "merge_pr.get_allowed_merge_methods", return_value=_ALL_METHODS_ALLOWED,
        ), patch(
            "subprocess.run",
            side_effect=_side_effect,
        ):
            # Explicit --strategy merge — default would resolve to squash now.
            rc = main(["--pull-request", "50", "--strategy", "merge"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["Data"]["action"] == "merged"
        assert output["Data"]["strategy"] == "merge"

    def test_auto_merge(self, capsys):
        state_json = json.dumps({
            "state": "OPEN", "mergeable": "MERGEABLE",
            "mergeStateStatus": "BLOCKED", "headRefName": "feature",
        })
        call_count = 0

        def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _completed(stdout=state_json, rc=0)
            return _completed(rc=0)

        with patch(
            "merge_pr.assert_gh_authenticated",
        ), patch(
            "merge_pr.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "merge_pr.get_allowed_merge_methods", return_value=_ALL_METHODS_ALLOWED,
        ), patch(
            "subprocess.run",
            side_effect=_side_effect,
        ):
            rc = main(["--pull-request", "50", "--auto"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["Data"]["action"] == "auto-merge-enabled"
        assert output["Data"]["state"] == "PENDING"

    def test_not_mergeable_exits_6(self):
        state_json = json.dumps({
            "state": "OPEN", "mergeable": "CONFLICTING",
            "mergeStateStatus": "DIRTY", "headRefName": "feature",
        })
        call_count = 0

        def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _completed(stdout=state_json, rc=0)
            return _completed(rc=1, stderr="not mergeable")

        with patch(
            "merge_pr.assert_gh_authenticated",
        ), patch(
            "merge_pr.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "merge_pr.get_allowed_merge_methods", return_value=_ALL_METHODS_ALLOWED,
        ), patch(
            "subprocess.run",
            side_effect=_side_effect,
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "50"])
            assert exc.value.code == 6

    def test_blocked_policy_without_auto_exits_6(self):
        state_json = json.dumps({
            "state": "OPEN", "mergeable": "MERGEABLE",
            "mergeStateStatus": "BLOCKED", "headRefName": "feature",
        })
        call_count = 0

        def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _completed(stdout=state_json, rc=0)
            return _completed(rc=1, stderr="BLOCKED by branch protection")

        with patch(
            "merge_pr.assert_gh_authenticated",
        ), patch(
            "merge_pr.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "merge_pr.get_allowed_merge_methods", return_value=_ALL_METHODS_ALLOWED,
        ), patch(
            "subprocess.run",
            side_effect=_side_effect,
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "50"])
            assert exc.value.code == 6

    def test_blocked_policy_with_auto_succeeds(self, capsys):
        state_json = json.dumps({
            "state": "OPEN", "mergeable": "MERGEABLE",
            "mergeStateStatus": "BLOCKED", "headRefName": "feature",
        })
        call_count = 0

        def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _completed(stdout=state_json, rc=0)
            return _completed(rc=0)

        with patch(
            "merge_pr.assert_gh_authenticated",
        ), patch(
            "merge_pr.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "merge_pr.get_allowed_merge_methods", return_value=_ALL_METHODS_ALLOWED,
        ), patch(
            "subprocess.run",
            side_effect=_side_effect,
        ):
            rc = main(["--pull-request", "50", "--auto"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["Data"]["action"] == "auto-merge-enabled"


# ---------------------------------------------------------------------------
# Tests: get_allowed_merge_methods
# ---------------------------------------------------------------------------


class TestGetAllowedMergeMethods:
    def test_returns_settings_on_success(self):
        settings = json.dumps({
            "allow_merge_commit": True,
            "allow_squash_merge": True,
            "allow_rebase_merge": False,
        })
        with patch(
            "subprocess.run",
            return_value=_completed(stdout=settings, rc=0),
        ):
            result = get_allowed_merge_methods("o/r")
        assert result["allow_rebase_merge"] is False

    def test_raises_on_api_failure(self):
        with patch(
            "subprocess.run",
            return_value=_completed(rc=1, stderr="error"),
        ):
            with pytest.raises(RuntimeError) as exc:
                get_allowed_merge_methods("o/r")
            assert "Failed to query repository settings" in str(exc.value)

    def test_raises_on_invalid_json(self):
        with patch(
            "subprocess.run",
            return_value=_completed(stdout="not-json", rc=0),
        ):
            with pytest.raises(ValueError) as exc:
                get_allowed_merge_methods("o/r")
            assert "Failed to decode JSON" in str(exc.value)


# ---------------------------------------------------------------------------
# Tests: validate_strategy
# ---------------------------------------------------------------------------


class TestValidateStrategy:
    def test_empty_settings_rejects_strategy(self):
        """Empty settings should reject strategies by defaulting to False."""
        with pytest.raises(SystemExit) as exc:
            validate_strategy("merge", {}, "o/r", "auto")
        assert exc.value.code == 1

    def test_allowed_strategy_passes(self):
        settings = {
            "allow_merge_commit": True,
            "allow_squash_merge": True,
            "allow_rebase_merge": False,
        }
        validate_strategy("squash", settings, "o/r", "auto")

    def test_disallowed_strategy_exits_1(self):
        settings = {
            "allow_merge_commit": False,
            "allow_squash_merge": True,
            "allow_rebase_merge": False,
        }
        with pytest.raises(SystemExit) as exc:
            validate_strategy("merge", settings, "o/r", "auto")
        assert exc.value.code == 1

    def test_disallowed_strategy_emits_json_envelope(self, capsys):
        """Regression: #2449 — must emit JSON envelope on stdout, not plain text on stderr.

        Before the fix, validate_strategy called error_and_exit which
        printed to stderr and produced no JSON on stdout, breaking
        consumers that pipe to json.loads.
        """
        settings = {
            "allow_merge_commit": False,
            "allow_squash_merge": True,
            "allow_rebase_merge": False,
        }
        with pytest.raises(SystemExit) as exc:
            validate_strategy("merge", settings, "o/r", "json")
        assert exc.value.code == 1
        captured = capsys.readouterr()
        envelope = json.loads(captured.out)
        assert envelope["Success"] is False
        assert envelope["Error"]["Code"] == 1
        assert envelope["Error"]["Type"] == "InvalidParams"
        assert "merge" in envelope["Error"]["Message"]
        assert "squash" in envelope["Error"]["Message"]
        assert "Metadata" in envelope
        assert envelope["Metadata"]["Script"] == "merge_pr.py"

    def test_strategy_rejected_in_main(self):
        settings = {
            "allow_merge_commit": False,
            "allow_squash_merge": True,
            "allow_rebase_merge": False,
        }
        with patch(
            "merge_pr.assert_gh_authenticated",
        ), patch(
            "merge_pr.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "merge_pr.get_allowed_merge_methods", return_value=settings,
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "50", "--strategy", "merge"])
            assert exc.value.code == 1

    def test_rebase_strategy_rejected(self):
        settings = {
            "allow_merge_commit": True,
            "allow_squash_merge": True,
            "allow_rebase_merge": False,
        }
        with pytest.raises(SystemExit) as exc:
            validate_strategy("rebase", settings, "o/r", "auto")
        assert exc.value.code == 1

    def test_rebase_strategy_allowed(self):
        settings = {
            "allow_merge_commit": False,
            "allow_squash_merge": False,
            "allow_rebase_merge": True,
        }
        validate_strategy("rebase", settings, "o/r", "auto")


# ---------------------------------------------------------------------------
# Tests: resolve_default_strategy (issue #2449)
# ---------------------------------------------------------------------------


resolve_default_strategy = _mod.resolve_default_strategy


class TestResolveDefaultStrategy:
    """Auto-pick a strategy when --strategy is omitted (issue #2449).

    The previous behavior hard-coded 'merge' as the default, which fails
    on repos that disallow merge commits. The new behavior consults the
    repo's allowed merge methods and picks the single allowed strategy
    when there is one obvious choice, or falls back to 'squash' when
    multiple are allowed (squash is the safest, most-portable default).
    """

    def test_single_allowed_method_squash(self):
        """Repo allows only squash → resolve to squash."""
        settings = {
            "allow_merge_commit": False,
            "allow_squash_merge": True,
            "allow_rebase_merge": False,
        }
        assert resolve_default_strategy(settings) == "squash"

    def test_single_allowed_method_rebase(self):
        settings = {
            "allow_merge_commit": False,
            "allow_squash_merge": False,
            "allow_rebase_merge": True,
        }
        assert resolve_default_strategy(settings) == "rebase"

    def test_single_allowed_method_merge(self):
        settings = {
            "allow_merge_commit": True,
            "allow_squash_merge": False,
            "allow_rebase_merge": False,
        }
        assert resolve_default_strategy(settings) == "merge"

    def test_multiple_allowed_prefers_squash(self):
        """When repo allows multiple, prefer squash (cleanest history)."""
        settings = {
            "allow_merge_commit": True,
            "allow_squash_merge": True,
            "allow_rebase_merge": True,
        }
        assert resolve_default_strategy(settings) == "squash"

    def test_merge_and_rebase_allowed_prefers_merge(self):
        """If squash is disallowed but merge is allowed, prefer merge."""
        settings = {
            "allow_merge_commit": True,
            "allow_squash_merge": False,
            "allow_rebase_merge": True,
        }
        assert resolve_default_strategy(settings) == "merge"

    def test_none_allowed_returns_none(self):
        """If no methods are allowed, return None (caller errors)."""
        settings = {
            "allow_merge_commit": False,
            "allow_squash_merge": False,
            "allow_rebase_merge": False,
        }
        assert resolve_default_strategy(settings) is None


# ---------------------------------------------------------------------------
# Tests: default-strategy integration (issue #2449)
# ---------------------------------------------------------------------------


class TestDefaultStrategyIntegration:
    """End-to-end: omitting --strategy on rjmurillo/ai-agents picks squash."""

    def test_omitted_strategy_picks_squash_on_squash_only_repo(self, capsys):
        """Reproduces rjmurillo/ai-agents (squash-only) scenario."""
        squash_only = {
            "allow_merge_commit": False,
            "allow_squash_merge": True,
            "allow_rebase_merge": False,
        }
        state_json = json.dumps({
            "state": "OPEN", "mergeable": "MERGEABLE",
            "mergeStateStatus": "CLEAN", "headRefName": "feature",
        })
        merge_calls = []

        def _side_effect(*args, **kwargs):
            merge_calls.append(args[0] if args else kwargs.get("args", []))
            if len(merge_calls) == 1:
                return _completed(stdout=state_json, rc=0)
            return _completed(rc=0)

        with patch(
            "merge_pr.assert_gh_authenticated",
        ), patch(
            "merge_pr.resolve_repo_params",
            return_value=RepoInfo(owner="rjmurillo", repo="ai-agents"),
        ), patch(
            "merge_pr.get_allowed_merge_methods", return_value=squash_only,
        ), patch(
            "subprocess.run", side_effect=_side_effect,
        ):
            rc = main(["--pull-request", "2444"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["Success"] is True
        assert output["Data"]["strategy"] == "squash"
        merge_cmd = merge_calls[-1]
        assert "--squash" in merge_cmd

    def test_explicit_disallowed_strategy_emits_envelope(self, capsys):
        """Explicit --strategy merge on squash-only repo → JSON envelope."""
        squash_only = {
            "allow_merge_commit": False,
            "allow_squash_merge": True,
            "allow_rebase_merge": False,
        }
        with patch(
            "merge_pr.assert_gh_authenticated",
        ), patch(
            "merge_pr.resolve_repo_params",
            return_value=RepoInfo(owner="rjmurillo", repo="ai-agents"),
        ), patch(
            "merge_pr.get_allowed_merge_methods", return_value=squash_only,
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "2444", "--strategy", "merge",
                      "--output-format", "json"])
            assert exc.value.code == 1
        envelope = json.loads(capsys.readouterr().out)
        assert envelope["Success"] is False
        assert envelope["Error"]["Code"] == 1
        assert envelope["Error"]["Type"] == "InvalidParams"


# ---------------------------------------------------------------------------
# Tests: success envelope wrapping (issue #2449)
# ---------------------------------------------------------------------------


class TestSuccessEnvelope:
    """All success paths emit the standard JSON envelope per ADR-056."""

    def test_already_merged_uses_envelope(self, capsys):
        state_json = json.dumps({
            "state": "MERGED", "mergeable": "", "mergeStateStatus": "", "headRefName": "f",
        })
        with patch(
            "merge_pr.assert_gh_authenticated",
        ), patch(
            "merge_pr.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "merge_pr.get_allowed_merge_methods", return_value=_ALL_METHODS_ALLOWED,
        ), patch(
            "subprocess.run",
            return_value=_completed(stdout=state_json, rc=0),
        ):
            rc = main(["--pull-request", "50", "--output-format", "json"])
        assert rc == 0
        envelope = json.loads(capsys.readouterr().out)
        assert envelope["Success"] is True
        assert envelope["Data"]["action"] == "none"
        assert envelope["Error"] is None

    def test_merge_success_uses_envelope(self, capsys):
        state_json = json.dumps({
            "state": "OPEN", "mergeable": "MERGEABLE",
            "mergeStateStatus": "CLEAN", "headRefName": "feature",
        })
        call_count = 0

        def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _completed(stdout=state_json, rc=0)
            return _completed(rc=0)

        with patch(
            "merge_pr.assert_gh_authenticated",
        ), patch(
            "merge_pr.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "merge_pr.get_allowed_merge_methods", return_value=_ALL_METHODS_ALLOWED,
        ), patch(
            "subprocess.run", side_effect=_side_effect,
        ):
            rc = main(["--pull-request", "50", "--output-format", "json"])
        assert rc == 0
        envelope = json.loads(capsys.readouterr().out)
        assert envelope["Success"] is True
        assert envelope["Data"]["action"] == "merged"


# ---------------------------------------------------------------------------
# Tests: error envelope wrapping (issue #2449)
# ---------------------------------------------------------------------------


class TestErrorEnvelope:
    """All error paths emit the standard JSON envelope per ADR-056."""

    def test_pr_not_found_uses_envelope(self, capsys):
        with patch(
            "merge_pr.assert_gh_authenticated",
        ), patch(
            "merge_pr.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "merge_pr.get_allowed_merge_methods", return_value=_ALL_METHODS_ALLOWED,
        ), patch(
            "subprocess.run",
            return_value=_completed(rc=1, stderr="not found"),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "999", "--output-format", "json"])
            assert exc.value.code == 2
        envelope = json.loads(capsys.readouterr().out)
        assert envelope["Success"] is False
        assert envelope["Error"]["Code"] == 2
        assert envelope["Error"]["Type"] == "NotFound"

    def test_closed_pr_uses_envelope(self, capsys):
        state_json = json.dumps({
            "state": "CLOSED", "mergeable": "", "mergeStateStatus": "", "headRefName": "f",
        })
        with patch(
            "merge_pr.assert_gh_authenticated",
        ), patch(
            "merge_pr.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "merge_pr.get_allowed_merge_methods", return_value=_ALL_METHODS_ALLOWED,
        ), patch(
            "subprocess.run",
            return_value=_completed(stdout=state_json, rc=0),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "50", "--output-format", "json"])
            assert exc.value.code == 6
        envelope = json.loads(capsys.readouterr().out)
        assert envelope["Success"] is False
        assert envelope["Error"]["Code"] == 6
        assert envelope["Error"]["Type"] == "General"

    def test_not_mergeable_uses_envelope(self, capsys):
        state_json = json.dumps({
            "state": "OPEN", "mergeable": "CONFLICTING",
            "mergeStateStatus": "DIRTY", "headRefName": "feature",
        })
        call_count = 0

        def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _completed(stdout=state_json, rc=0)
            return _completed(rc=1, stderr="not mergeable")

        with patch(
            "merge_pr.assert_gh_authenticated",
        ), patch(
            "merge_pr.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "merge_pr.get_allowed_merge_methods", return_value=_ALL_METHODS_ALLOWED,
        ), patch(
            "subprocess.run", side_effect=_side_effect,
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "50", "--output-format", "json"])
            assert exc.value.code == 6
        envelope = json.loads(capsys.readouterr().out)
        assert envelope["Success"] is False
        assert envelope["Error"]["Code"] == 6


# ---------------------------------------------------------------------------
# Tests: additional main scenarios
# ---------------------------------------------------------------------------


class TestMainAdditional:
    def test_merge_generic_failure_exits_3(self):
        state_json = json.dumps({
            "state": "OPEN", "mergeable": "MERGEABLE",
            "mergeStateStatus": "CLEAN", "headRefName": "feature",
        })
        call_count = 0

        def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _completed(stdout=state_json, rc=0)
            return _completed(rc=1, stderr="unknown error")

        with patch(
            "merge_pr.assert_gh_authenticated",
        ), patch(
            "merge_pr.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "merge_pr.get_allowed_merge_methods", return_value=_ALL_METHODS_ALLOWED,
        ), patch(
            "subprocess.run",
            side_effect=_side_effect,
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "50"])
            assert exc.value.code == 3

    def test_conflicts_keyword_exits_6(self):
        state_json = json.dumps({
            "state": "OPEN", "mergeable": "CONFLICTING",
            "mergeStateStatus": "DIRTY", "headRefName": "feature",
        })
        call_count = 0

        def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _completed(stdout=state_json, rc=0)
            return _completed(rc=1, stderr="conflicts must be resolved")

        with patch(
            "merge_pr.assert_gh_authenticated",
        ), patch(
            "merge_pr.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "merge_pr.get_allowed_merge_methods", return_value=_ALL_METHODS_ALLOWED,
        ), patch(
            "subprocess.run",
            side_effect=_side_effect,
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "50"])
            assert exc.value.code == 6

    def test_delete_branch_flag(self, capsys):
        state_json = json.dumps({
            "state": "OPEN", "mergeable": "MERGEABLE",
            "mergeStateStatus": "CLEAN", "headRefName": "feature",
        })
        calls = []

        def _side_effect(*args, **kwargs):
            calls.append(args[0] if args else kwargs.get("args", []))
            if len(calls) == 1:
                return _completed(stdout=state_json, rc=0)
            return _completed(rc=0)

        with patch(
            "merge_pr.assert_gh_authenticated",
        ), patch(
            "merge_pr.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "merge_pr.get_allowed_merge_methods", return_value=_ALL_METHODS_ALLOWED,
        ), patch(
            "subprocess.run",
            side_effect=_side_effect,
        ):
            rc = main(["--pull-request", "50", "--delete-branch"])
        assert rc == 0
        merge_cmd = calls[-1]
        assert "--delete-branch" in merge_cmd
        output = json.loads(capsys.readouterr().out)
        assert output["Data"]["branch_deleted"] is True

    def test_pr_view_non_not_found_error_exits_3(self):
        with patch(
            "merge_pr.assert_gh_authenticated",
        ), patch(
            "merge_pr.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "merge_pr.get_allowed_merge_methods", return_value=_ALL_METHODS_ALLOWED,
        ), patch(
            "subprocess.run",
            return_value=_completed(rc=1, stderr="internal server error"),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "50"])
            assert exc.value.code == 3

    def test_subject_and_body_passed(self, capsys):
        state_json = json.dumps({
            "state": "OPEN", "mergeable": "MERGEABLE",
            "mergeStateStatus": "CLEAN", "headRefName": "feature",
        })
        calls = []

        def _side_effect(*args, **kwargs):
            calls.append(args[0] if args else kwargs.get("args", []))
            if len(calls) == 1:
                return _completed(stdout=state_json, rc=0)
            return _completed(rc=0)

        with patch(
            "merge_pr.assert_gh_authenticated",
        ), patch(
            "merge_pr.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "merge_pr.get_allowed_merge_methods", return_value=_ALL_METHODS_ALLOWED,
        ), patch(
            "subprocess.run",
            side_effect=_side_effect,
        ):
            rc = main([
                "--pull-request", "50",
                "--subject", "Custom subject",
                "--body", "Custom body",
            ])
        assert rc == 0
        merge_cmd = calls[-1]
        assert "--subject" in merge_cmd
        assert "Custom subject" in merge_cmd
        assert "--body" in merge_cmd
        assert "Custom body" in merge_cmd
