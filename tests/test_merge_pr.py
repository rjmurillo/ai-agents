"""Tests for merge_pr.py skill script."""

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

    def test_strategy_default(self):
        args = build_parser().parse_args(["--pull-request", "50"])
        assert args.strategy == "merge"

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
            return_value={"Owner": "o", "Repo": "r"},
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
            return_value={"Owner": "o", "Repo": "r"},
        ), patch(
            "merge_pr.get_allowed_merge_methods", return_value=_ALL_METHODS_ALLOWED,
        ), patch(
            "subprocess.run",
            return_value=_completed(stdout=state_json, rc=0),
        ):
            rc = main(["--pull-request", "50"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["action"] == "none"

    def test_closed_pr_exits_6(self):
        state_json = json.dumps({
            "state": "CLOSED", "mergeable": "", "mergeStateStatus": "", "headRefName": "f",
        })
        with patch(
            "merge_pr.assert_gh_authenticated",
        ), patch(
            "merge_pr.resolve_repo_params",
            return_value={"Owner": "o", "Repo": "r"},
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
            return_value={"Owner": "o", "Repo": "r"},
        ), patch(
            "merge_pr.get_allowed_merge_methods", return_value=_ALL_METHODS_ALLOWED,
        ), patch(
            "subprocess.run",
            side_effect=_side_effect,
        ):
            rc = main(["--pull-request", "50"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["action"] == "merged"
        assert output["strategy"] == "merge"

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
            return_value={"Owner": "o", "Repo": "r"},
        ), patch(
            "merge_pr.get_allowed_merge_methods", return_value=_ALL_METHODS_ALLOWED,
        ), patch(
            "subprocess.run",
            side_effect=_side_effect,
        ):
            rc = main(["--pull-request", "50", "--auto"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["action"] == "auto-merge-enabled"
        assert output["state"] == "PENDING"

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
            return_value={"Owner": "o", "Repo": "r"},
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
            return_value={"Owner": "o", "Repo": "r"},
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
            return_value={"Owner": "o", "Repo": "r"},
        ), patch(
            "merge_pr.get_allowed_merge_methods", return_value=_ALL_METHODS_ALLOWED,
        ), patch(
            "subprocess.run",
            side_effect=_side_effect,
        ):
            rc = main(["--pull-request", "50", "--auto"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["action"] == "auto-merge-enabled"


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
            validate_strategy("merge", {}, "o/r")
        assert exc.value.code == 1

    def test_allowed_strategy_passes(self):
        settings = {
            "allow_merge_commit": True,
            "allow_squash_merge": True,
            "allow_rebase_merge": False,
        }
        validate_strategy("squash", settings, "o/r")

    def test_disallowed_strategy_exits_1(self):
        settings = {
            "allow_merge_commit": False,
            "allow_squash_merge": True,
            "allow_rebase_merge": False,
        }
        with pytest.raises(SystemExit) as exc:
            validate_strategy("merge", settings, "o/r")
        assert exc.value.code == 1

    def test_disallowed_strategy_lists_allowed(self, capsys):
        settings = {
            "allow_merge_commit": False,
            "allow_squash_merge": True,
            "allow_rebase_merge": False,
        }
        with pytest.raises(SystemExit):
            validate_strategy("merge", settings, "o/r")

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
            return_value={"Owner": "o", "Repo": "r"},
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
            validate_strategy("rebase", settings, "o/r")
        assert exc.value.code == 1

    def test_rebase_strategy_allowed(self):
        settings = {
            "allow_merge_commit": False,
            "allow_squash_merge": False,
            "allow_rebase_merge": True,
        }
        validate_strategy("rebase", settings, "o/r")


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
            return_value={"Owner": "o", "Repo": "r"},
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
            return_value={"Owner": "o", "Repo": "r"},
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
            return_value={"Owner": "o", "Repo": "r"},
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
        assert output["branch_deleted"] is True

    def test_pr_view_non_not_found_error_exits_3(self):
        with patch(
            "merge_pr.assert_gh_authenticated",
        ), patch(
            "merge_pr.resolve_repo_params",
            return_value={"Owner": "o", "Repo": "r"},
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
            return_value={"Owner": "o", "Repo": "r"},
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
