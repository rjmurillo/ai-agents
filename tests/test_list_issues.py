"""Tests for list_issues.py skill script (issue #2110)."""

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


_mod = _import_script("list_issues")
main = _mod.main
build_parser = _mod.build_parser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


def _issue(
    number=1,
    title="Issue",
    state="OPEN",
    labels=None,
    assignees=None,
    author="alice",
):
    return {
        "number": number,
        "title": title,
        "state": state,
        "labels": [{"name": n} for n in (labels or [])],
        "assignees": [{"login": a} for a in (assignees or [])],
        "author": {"login": author},
        "url": f"https://github.com/o/r/issues/{number}",
        "createdAt": "2026-01-01T00:00:00Z",
        "updatedAt": "2026-01-02T00:00:00Z",
    }


# ---------------------------------------------------------------------------
# Tests: build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_defaults(self):
        args = build_parser().parse_args([])
        assert args.state == "open"
        assert args.limit == 30
        assert args.label == ""
        assert args.assignee == ""

    def test_all_filters(self):
        args = build_parser().parse_args([
            "--state", "closed",
            "--label", "bug,P1",
            "--author", "alice",
            "--assignee", "bob",
            "--limit", "100",
        ])
        assert args.state == "closed"
        assert args.label == "bug,P1"
        assert args.author == "alice"
        assert args.assignee == "bob"
        assert args.limit == 100

    def test_invalid_state_rejected(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["--state", "bogus"])


# ---------------------------------------------------------------------------
# Tests: main
# ---------------------------------------------------------------------------


class TestMain:
    def test_not_authenticated_exits_4(self, capsys):
        with patch(
            "list_issues.assert_gh_authenticated",
            side_effect=SystemExit(4),
        ):
            with pytest.raises(SystemExit) as exc:
                main([])
            assert exc.value.code == 4
        payload = json.loads(capsys.readouterr().out)
        assert payload["Success"] is False
        assert payload["Error"]["Code"] == 4
        assert payload["Error"]["Type"] == "AuthError"

    def test_success_open_issues(self, capsys):
        issues = [
            _issue(1, "First", labels=["bug"], assignees=["alice"]),
            _issue(2, "Second"),
        ]
        with patch(
            "list_issues.assert_gh_authenticated",
        ), patch(
            "list_issues.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_completed(stdout=json.dumps(issues), rc=0),
        ):
            rc = main([])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)["Data"]["issues"]
        assert len(output) == 2
        assert output[0]["number"] == 1
        assert output[0]["labels"] == ["bug"]
        assert output[0]["assignees"] == ["alice"]
        assert output[0]["author"] == "alice"

    def test_label_filter_passes_each_label(self):
        with patch(
            "list_issues.assert_gh_authenticated",
        ), patch(
            "list_issues.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_completed(stdout="[]", rc=0),
        ) as mock_run:
            rc = main(["--label", "bug,P1"])
        assert rc == 0
        cmd = mock_run.call_args[0][0]
        # Each label gets its own --label flag.
        assert cmd.count("--label") == 2
        assert "bug" in cmd and "P1" in cmd

    def test_assignee_filter_passed(self):
        with patch(
            "list_issues.assert_gh_authenticated",
        ), patch(
            "list_issues.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_completed(stdout="[]", rc=0),
        ) as mock_run:
            main(["--assignee", "@me"])
        cmd = mock_run.call_args[0][0]
        assert "--assignee" in cmd
        assert "@me" in cmd

    def test_state_all_forwards_state_flag(self):
        # gh issue list defaults to open-only when --state is omitted,
        # so --state all must be forwarded to actually return all states.
        with patch(
            "list_issues.assert_gh_authenticated",
        ), patch(
            "list_issues.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_completed(stdout="[]", rc=0),
        ) as mock_run:
            main(["--state", "all"])
        cmd = mock_run.call_args[0][0]
        assert "--state" in cmd
        assert "all" in cmd

    def test_search_filter_ignores_other_flags(self, capsys):
        issues = [_issue(5, "Fix auth bug")]
        with patch(
            "list_issues.assert_gh_authenticated",
        ), patch(
            "list_issues.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_completed(stdout=json.dumps(issues), rc=0),
        ) as mock_run:
            rc = main(["--search", "fix auth", "--label", "bug", "--state", "open"])
        assert rc == 0
        cmd = mock_run.call_args[0][0]
        assert "--search" in cmd
        assert "fix auth" in cmd
        assert "--label" not in cmd
        assert "--author" not in cmd
        # --state is implicit-default 'open' here but must not be forwarded
        # when --search is set, since gh would ignore it anyway.
        assert "--state" not in cmd
        output = json.loads(capsys.readouterr().out)["Data"]["issues"]
        assert len(output) == 1

    def test_api_error_exits_3(self, capsys):
        with patch(
            "list_issues.assert_gh_authenticated",
        ), patch(
            "list_issues.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_completed(rc=1, stderr="API error"),
        ):
            with pytest.raises(SystemExit) as exc:
                main([])
            assert exc.value.code == 3
        payload = json.loads(capsys.readouterr().out)
        assert payload["Success"] is False
        assert payload["Error"]["Type"] == "ApiError"

    def test_timeout_exits_3(self, capsys):
        with patch(
            "list_issues.assert_gh_authenticated",
        ), patch(
            "list_issues.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="gh", timeout=30),
        ):
            with pytest.raises(SystemExit) as exc:
                main([])
            assert exc.value.code == 3
        payload = json.loads(capsys.readouterr().out)
        assert payload["Success"] is False
        assert payload["Error"]["Type"] == "Timeout"

    def test_gh_missing_exits_3(self, capsys):
        with patch(
            "list_issues.assert_gh_authenticated",
        ), patch(
            "list_issues.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            side_effect=FileNotFoundError("gh"),
        ):
            with pytest.raises(SystemExit) as exc:
                main([])
            assert exc.value.code == 3
        payload = json.loads(capsys.readouterr().out)
        assert payload["Success"] is False
        assert payload["Error"]["Type"] == "ApiError"

    def test_malformed_json_exits_3(self, capsys):
        with patch(
            "list_issues.assert_gh_authenticated",
        ), patch(
            "list_issues.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_completed(stdout="not json", rc=0),
        ):
            with pytest.raises(SystemExit) as exc:
                main([])
            assert exc.value.code == 3
        payload = json.loads(capsys.readouterr().out)
        assert payload["Success"] is False
        assert payload["Error"]["Type"] == "ApiError"

    @pytest.mark.parametrize("payload", ["null", "{}", "42", '"text"'])
    def test_non_list_root_exits_3(self, payload, capsys):
        # gh should always return a JSON array; a non-list root (null,
        # object, scalar) must map to ADR-035 exit code 3, not crash or
        # silently emit an empty list.
        with patch(
            "list_issues.assert_gh_authenticated",
        ), patch(
            "list_issues.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_completed(stdout=payload, rc=0),
        ):
            with pytest.raises(SystemExit) as exc:
                main([])
            assert exc.value.code == 3
        error = json.loads(capsys.readouterr().out)["Error"]
        assert error["Code"] == 3
        assert error["Type"] == "ApiError"

    def test_non_dict_items_skipped(self, capsys):
        # gh should never return scalars, but a malformed response must
        # not crash on attribute access.
        payload = [_issue(1, "Good"), "garbage", None, 42]
        with patch(
            "list_issues.assert_gh_authenticated",
        ), patch(
            "list_issues.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_completed(stdout=json.dumps(payload), rc=0),
        ):
            rc = main([])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)["Data"]["issues"]
        assert len(output) == 1
        assert output[0]["number"] == 1

    def test_null_labels_and_assignees_handled(self, capsys):
        payload = [{
            "number": 7,
            "title": "Null lists",
            "state": "OPEN",
            "labels": None,
            "assignees": None,
            "author": {"login": "alice"},
            "url": "https://github.com/o/r/issues/7",
            "createdAt": None,
            "updatedAt": None,
        }]
        with patch(
            "list_issues.assert_gh_authenticated",
        ), patch(
            "list_issues.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_completed(stdout=json.dumps(payload), rc=0),
        ):
            rc = main([])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)["Data"]["issues"]
        assert output[0]["labels"] == []
        assert output[0]["assignees"] == []

    def test_empty_results(self, capsys):
        with patch(
            "list_issues.assert_gh_authenticated",
        ), patch(
            "list_issues.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_completed(stdout="[]", rc=0),
        ):
            rc = main([])
        assert rc == 0
        assert json.loads(capsys.readouterr().out)["Data"]["issues"] == []

    def test_invalid_limit_exits_2(self, capsys):
        with patch(
            "list_issues.assert_gh_authenticated",
        ), patch(
            "list_issues.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--limit", "0"])
            assert exc.value.code == 2
        payload = json.loads(capsys.readouterr().out)
        assert payload["Success"] is False
        assert payload["Error"]["Type"] == "InvalidParams"

    def test_repo_resolution_error_preserves_specific_message(self, capsys):
        def fail_with_message(*_args, **_kwargs):
            print("Invalid GitHub owner name: bad owner", file=sys.stderr)
            raise SystemExit(2)

        with patch(
            "list_issues.assert_gh_authenticated",
        ), patch(
            "list_issues.resolve_repo_params",
            side_effect=fail_with_message,
        ):
            with pytest.raises(SystemExit) as exc:
                main([])
            assert exc.value.code == 2
        payload = json.loads(capsys.readouterr().out)
        assert payload["Success"] is False
        assert payload["Error"]["Type"] == "InvalidParams"
        assert payload["Error"]["Message"] == "Invalid GitHub owner name: bad owner"

    def test_missing_author_login_handled(self, capsys):
        # Defensive: gh sometimes returns a null author (deleted user).
        issues = [{
            "number": 9,
            "title": "Orphan",
            "state": "OPEN",
            "labels": [],
            "assignees": [],
            "author": None,
            "url": "https://github.com/o/r/issues/9",
            "createdAt": None,
            "updatedAt": None,
        }]
        with patch(
            "list_issues.assert_gh_authenticated",
        ), patch(
            "list_issues.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_completed(stdout=json.dumps(issues), rc=0),
        ):
            rc = main([])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)["Data"]["issues"]
        assert output[0]["author"] is None


# ---------------------------------------------------------------------------
# Regression: invoke_skill_first_guard 'issue.list' mapping (#2110)
# ---------------------------------------------------------------------------


class TestIssueListGuardMapping:
    """Guard's issue.list mapping must point at a list-capable script
    whose example command parses without requiring extra args."""

    def test_mapping_targets_list_issues_script(self):
        guard_path = (
            Path(__file__).resolve().parents[1]
            / ".claude" / "hooks" / "PreToolUse" / "invoke_skill_first_guard.py"
        )
        # Use a unique module name to avoid polluting the canonical
        # 'invoke_skill_first_guard' entry that other test modules import
        # with sys.path manipulation + @patch on the canonical name.
        spec = importlib.util.spec_from_file_location(
            "_isfg_mapping_probe", guard_path,
        )
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        sys.modules["_isfg_mapping_probe"] = mod
        spec.loader.exec_module(mod)

        mapping = mod.SKILL_MAPPINGS["issue"]["list"]
        assert mapping["script"] == "list_issues.py"
        # The mapped script must exist on disk.
        script = _SCRIPTS_DIR / mapping["script"]
        assert script.exists(), f"missing {script}"
        # The example must reference the same script.
        assert mapping["script"] in mapping["example"]

    def test_example_command_parses_without_error(self):
        # Strip the leading 'python3 .claude/...script' prefix and verify
        # the remaining argv is accepted by build_parser without exit.
        guard_path = (
            Path(__file__).resolve().parents[1]
            / ".claude" / "hooks" / "PreToolUse" / "invoke_skill_first_guard.py"
        )
        spec = importlib.util.spec_from_file_location(
            "invoke_skill_first_guard_v2", guard_path,
        )
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        sys.modules["invoke_skill_first_guard_v2"] = mod
        spec.loader.exec_module(mod)

        example = mod.SKILL_MAPPINGS["issue"]["list"]["example"]
        # Drop 'python3 <path>' prefix; keep the rest as argv.
        tokens = example.split()
        # Find script token (ends with .py).
        script_idx = next(
            i for i, t in enumerate(tokens) if t.endswith(".py")
        )
        argv = tokens[script_idx + 1:]
        # Must not raise SystemExit.
        args = build_parser().parse_args(argv)
        assert args.state == "open"
        assert args.label == "bug"
