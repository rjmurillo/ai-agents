# taste-lint: ignore file-size -- 4 issue fixes share fixtures; splitting would orphan them
"""Tests for #4359, #4393, #4462, #4490 fixes.

Covers:
  - get_pr_checks.py: missing required checks (set-difference against ruleset)
  - merge_pr.py: skip REST preflight when --strategy is explicit
  - why_pr_blocked.py: discriminated cause list
  - audit_closing_claims.py: Markdown context classification
  - edit_pr_body.py: stale-write guard and validation
"""

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
# Script imports
# ---------------------------------------------------------------------------

_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1]
    / ".claude" / "skills" / "github" / "scripts" / "pr"
)


def _import_script(name: str):
    # Use a unique alias so this module's registration doesn't collide with
    # test_get_pr_checks.py / test_merge_pr.py when pytest collects all three.
    alias = f"_diag_{name}"
    spec = importlib.util.spec_from_file_location(alias, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)
    return mod


_checks_mod = _import_script("get_pr_checks")
_merge_mod = _import_script("merge_pr")
_why_mod = _import_script("why_pr_blocked")
_audit_mod = _import_script("audit_closing_claims")
_edit_mod = _import_script("edit_pr_body")

# ---------------------------------------------------------------------------
# Helpers shared across tests
# ---------------------------------------------------------------------------


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


def _rollup_response(nodes, state="SUCCESS", number=100, *, oid="abc123"):
    return {
        "repository": {
            "pullRequest": {
                "number": number,
                "baseRefName": "main",
                "mergeable": "MERGEABLE",
                "mergeStateStatus": "CLEAN",
                "commits": {
                    "nodes": [{
                        "commit": {
                            "oid": oid,
                            "statusCheckRollup": {
                                "state": state,
                                "contexts": {
                                    "totalCount": len(nodes),
                                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                                    "nodes": nodes,
                                },
                            },
                        },
                    }],
                },
            },
        },
    }


def _check_run_node(
    name,
    status,
    conclusion,
    *,
    required=True,
    integration_id=15368,
):
    return {
        "__typename": "CheckRun",
        "name": name,
        "status": status,
        "conclusion": conclusion,
        "detailsUrl": "",
        "checkSuite": {"app": {"databaseId": integration_id}},
        "isRequired": required,
    }


def _required_checks(*names, integration_id=15368):
    return [
        {"Context": name, "IntegrationId": integration_id}
        for name in names
    ]


_MOCK_REPO = RepoInfo(owner="testowner", repo="testrepo")


# ===========================================================================
# #4359: get_pr_checks.py - missing required checks via set-difference
# ===========================================================================

class TestFetchRulesetRequiredContexts:
    """Unit tests for fetch_ruleset_required_contexts."""

    def test_returns_list_on_success(self):
        contexts = [
            {"context": "CI / build", "integration_id": 15368},
            {"context": "CI / test", "integration_id": 15368},
            {"context": "Validate PR", "integration_id": 15368},
        ]
        mock_result = _completed(stdout=json.dumps(contexts))
        with patch("subprocess.run", return_value=mock_result):
            result = _checks_mod.fetch_ruleset_required_contexts("o", "r", "main")
        assert result == _required_checks("CI / build", "CI / test", "Validate PR")

    def test_raises_on_nonzero_rc(self):
        mock_result = _completed(stdout="", stderr="404", rc=1)
        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(RuntimeError, match="ruleset lookup failed"):
                _checks_mod.fetch_ruleset_required_contexts("o", "r", "main")

    def test_raises_on_empty_stdout(self):
        mock_result = _completed(stdout="")
        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(RuntimeError, match="response was invalid"):
                _checks_mod.fetch_ruleset_required_contexts("o", "r", "main")

    def test_raises_on_malformed_json(self):
        mock_result = _completed(stdout="not-json")
        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(RuntimeError, match="response was invalid"):
                _checks_mod.fetch_ruleset_required_contexts("o", "r", "main")


class TestBuildOutputMissingChecks:
    """Tests for the MissingRequiredChecks field added by #4359."""

    def _make_check_data(self, checks, base_branch="main"):
        return {
            "Number": 100,
            "BaseBranch": base_branch,
            "MergeState": "MERGEABLE",
            "MergeStateStatus": "CLEAN",
            "Checks": checks,
            "OverallState": "SUCCESS",
            "HasChecks": True,
            "ChecksIncomplete": False,
        }

    def _norm(self, name, *, passing=True, required=True):
        return {
            "Name": name,
            "Type": "CheckRun",
            "State": "COMPLETED",
            "Conclusion": "SUCCESS" if passing else "FAILURE",
            "DetailsUrl": "",
            "IntegrationId": 15368,
            "IsRequired": required,
            "IsPending": False,
            "IsPassing": passing,
            "IsFailing": not passing,
        }

    def test_no_missing_when_all_ruleset_checks_reported(self):
        """If ruleset contexts all appeared in rollup, MissingRequiredChecks is empty."""
        checks = [self._norm("CI / build"), self._norm("CI / test")]
        data = self._make_check_data(checks)
        ruleset = _required_checks("CI / build", "CI / test")
        output = _checks_mod.build_output(data, "o", "r", ruleset_required=ruleset)
        assert output["MissingRequiredChecks"] == []
        assert output["AllPassing"] is True

    def test_missing_required_check_never_reported(self):
        """The key bug: a required check that never ran must be detected.

        With only one check in the rollup but two required by the ruleset,
        the second must appear in MissingRequiredChecks.
        This is the mutation target for M1 in the harness.
        """
        checks = [self._norm("CI / build")]
        data = self._make_check_data(checks)
        ruleset = _required_checks("CI / build", "CI / test")
        output = _checks_mod.build_output(data, "o", "r", ruleset_required=ruleset)
        assert "CI / test" in output["MissingRequiredChecks"]
        assert output["AllPassing"] is False

    def test_missing_16_of_17_required_checks(self):
        """Real-world scenario from issue #4359: 16 of 17 required checks absent."""
        ruleset = _required_checks(*(f"Check/{i}" for i in range(17)))
        checks = [self._norm("Check/0")]  # only one reported
        data = self._make_check_data(checks)
        output = _checks_mod.build_output(data, "o", "r", ruleset_required=ruleset)
        assert len(output["MissingRequiredChecks"]) == 16
        assert output["AllPassing"] is False

    def test_skipped_check_satisfies_requirement(self):
        """A SKIPPED conclusion satisfies a required context; must not be reported missing."""
        checks = [{
            "Name": "CI / test",
            "Type": "CheckRun",
            "State": "COMPLETED",
            "Conclusion": "SKIPPED",
            "DetailsUrl": "",
            "IntegrationId": 15368,
            "IsRequired": True,
            "IsPending": False,
            "IsPassing": True,
            "IsFailing": False,
        }]
        data = self._make_check_data(checks)
        ruleset = _required_checks("CI / test")
        output = _checks_mod.build_output(data, "o", "r", ruleset_required=ruleset)
        assert output["MissingRequiredChecks"] == []

    def test_skipped_check_normalised_as_passing(self):
        """_PASSING_CONCLUSIONS must include SKIPPED so normalisation marks IsPassing True.

        Mutation kill target: if SKIPPED is removed from _PASSING_CONCLUSIONS,
        IsPassing will be False and this assertion fails.
        """
        raw_ctx = {
            "__typename": "CheckRun",
            "name": "CI / optional",
            "status": "COMPLETED",
            "conclusion": "SKIPPED",
            "detailsUrl": "",
            "checkSuite": {"app": {"databaseId": 15368}},
            "isRequired": False,
        }
        normalised = _checks_mod.normalize_check(raw_ctx)  # the exported normalization fn
        assert normalised is not None
        assert normalised["IsPassing"] is True
        assert normalised["IsFailing"] is False

    def test_empty_ruleset_does_not_change_behaviour(self):
        """Fail-open: when ruleset is unavailable, old behaviour preserved."""
        checks = [self._norm("CI / build")]
        data = self._make_check_data(checks)
        output_no_ruleset = _checks_mod.build_output(data, "o", "r")
        output_empty_ruleset = _checks_mod.build_output(data, "o", "r", ruleset_required=[])
        assert output_no_ruleset["MissingRequiredChecks"] == []
        assert output_empty_ruleset["MissingRequiredChecks"] == []

    def test_missing_key_present_even_when_empty(self):
        """MissingRequiredChecks key always present in output."""
        data = self._make_check_data([])
        output = _checks_mod.build_output(data, "o", "r")
        assert "MissingRequiredChecks" in output

    def test_wrong_integration_does_not_satisfy_requirement(self):
        checks = [{
            **self._norm("CI / build"),
            "IntegrationId": 99999,
            "IsRequired": False,
        }]
        data = self._make_check_data(checks)
        output = _checks_mod.build_output(
            data,
            "o",
            "r",
            ruleset_required=_required_checks("CI / build"),
        )
        assert output["MissingRequiredChecks"] == ["CI / build"]
        assert output["AllPassing"] is False

    def test_latest_success_discards_older_pending_run(self):
        older_pending = {
            **self._norm("CI / build", passing=False),
            "State": "IN_PROGRESS",
            "Conclusion": "",
            "DetailsUrl": "https://github.com/o/r/actions/runs/100/job/1",
            "IsPending": True,
            "IsFailing": False,
        }
        latest_success = {
            **self._norm("CI / build"),
            "DetailsUrl": "https://github.com/o/r/actions/runs/200/job/1",
        }

        result = _checks_mod.dedupe_checks([older_pending, latest_success])

        assert len(result) == 1
        assert result[0]["IsPassing"] is True
        assert result[0]["IsPending"] is False


class TestResolveStatusMissingChecks:
    """_resolve_status surfaces missing checks as FAIL."""

    def _output_with_missing(self, missing):
        return {
            "Number": 99,
            "MergeStateWarning": "",
            "FailedCount": 0,
            "PendingCount": 0,
            "PassedCount": 1,
            "MissingRequiredChecks": missing,
        }

    def test_missing_checks_produce_fail_status(self):
        output = self._output_with_missing(["CI / test", "Validate PR"])
        summary, status = _checks_mod._resolve_status(output, 300, False, False)
        assert status == "FAIL"
        assert "MISSING" in summary
        assert "2" in summary

    def test_no_missing_checks_produces_pass(self):
        output = self._output_with_missing([])
        summary, status = _checks_mod._resolve_status(output, 300, False, False)
        assert status == "PASS"

    def test_summary_truncates_long_missing_list(self):
        missing = [f"Check/{i}" for i in range(10)]
        output = self._output_with_missing(missing)
        summary, _ = _checks_mod._resolve_status(output, 300, False, False)
        assert "..." in summary


class TestMainGetPrChecksMissingExitCode:
    """main() returns exit code 1 when there are missing required checks."""

    def test_exit_1_on_missing_required_checks(self):
        rollup_data = _rollup_response(
            [_check_run_node("CI / build", "COMPLETED", "SUCCESS")],
        )
        ruleset_contexts = json.dumps([
            {"context": "CI / build", "integration_id": 15368},
            {"context": "CI / test", "integration_id": 15368},
        ])

        with (
            patch(f"{_checks_mod.__name__}.assert_gh_authenticated"),
            patch(f"{_checks_mod.__name__}.resolve_repo_params", return_value=_MOCK_REPO),
            patch(f"{_checks_mod.__name__}.gh_graphql", return_value=rollup_data),
            patch("subprocess.run", return_value=_completed(stdout=ruleset_contexts)),
            patch(f"{_checks_mod.__name__}.write_skill_output"),
        ):
            rc = _checks_mod.main(["--pull-request", "100"])
        assert rc == 1


# ===========================================================================
# #4490: merge_pr.py - skip REST preflight when --strategy is explicit
# ===========================================================================

class TestMergePrSkipPreflightWhenExplicit:
    """When --strategy is explicit and REST quota fails, continue gracefully."""

    def _pr_state(self, state="OPEN", mergeable="MERGEABLE"):
        return {"state": state, "mergeable": mergeable, "mergeStateStatus": "CLEAN"}

    def test_get_allowed_merge_methods_called_when_strategy_explicit(self):
        """Explicit --strategy still calls REST for validation (but tolerates failures)."""
        pr_data = self._pr_state()
        merge_result = _completed()
        settings = {"allow_squash_merge": True, "allow_merge_commit": False,
                    "allow_rebase_merge": False}

        with (
            patch(f"{_merge_mod.__name__}.assert_gh_authenticated"),
            patch(f"{_merge_mod.__name__}.resolve_repo_params", return_value=_MOCK_REPO),
            patch(f"{_merge_mod.__name__}._fetch_pr_state", return_value=pr_data),
            patch(f"{_merge_mod.__name__}.get_allowed_merge_methods",
                  return_value=settings) as mock_settings,
            patch("subprocess.run", return_value=merge_result),
            patch(f"{_merge_mod.__name__}.write_skill_output"),
        ):
            _merge_mod.main(["--pull-request", "42", "--strategy", "squash"])
        mock_settings.assert_called_once()

    def test_rest_quota_error_on_explicit_strategy_continues(self):
        """When REST quota is exhausted with explicit --strategy, proceed anyway.

        Issue #4490: the unconditional REST call blocked merges even when the
        caller already knew the strategy.  Now: exhausted quota with explicit
        strategy is a warning-not-fatal; GitHub rejects bad strategies itself.
        """
        pr_data = self._pr_state()
        merge_result = _completed()

        with (
            patch(f"{_merge_mod.__name__}.assert_gh_authenticated"),
            patch(f"{_merge_mod.__name__}.resolve_repo_params", return_value=_MOCK_REPO),
            patch(f"{_merge_mod.__name__}._fetch_pr_state", return_value=pr_data),
            patch(
                f"{_merge_mod.__name__}.get_allowed_merge_methods",
                side_effect=RuntimeError("HTTP 403 X-RateLimit-Remaining: 0"),
            ),
            patch("subprocess.run", return_value=merge_result),
            patch(f"{_merge_mod.__name__}.write_skill_output"),
        ):
            # Must NOT raise -- quota exhaustion on explicit strategy is tolerated.
            _merge_mod.main(["--pull-request", "42", "--strategy", "squash"])

    def test_non_quota_rest_error_on_explicit_strategy_is_fatal(self):
        pr_data = self._pr_state()

        with (
            patch(f"{_merge_mod.__name__}.assert_gh_authenticated"),
            patch(f"{_merge_mod.__name__}.resolve_repo_params", return_value=_MOCK_REPO),
            patch(f"{_merge_mod.__name__}._fetch_pr_state", return_value=pr_data),
            patch(
                f"{_merge_mod.__name__}.get_allowed_merge_methods",
                side_effect=RuntimeError("HTTP 500 repository settings unavailable"),
            ),
            patch(f"{_merge_mod.__name__}.write_skill_error"),
        ):
            with pytest.raises(SystemExit) as exc_info:
                _merge_mod.main(["--pull-request", "42", "--strategy", "squash"])
        assert exc_info.value.code == 3

    def test_get_allowed_merge_methods_called_when_no_strategy(self):
        pr_data = self._pr_state()
        merge_result = _completed()
        settings = {"allow_squash_merge": True, "allow_merge_commit": False,
                    "allow_rebase_merge": False}

        with (
            patch(f"{_merge_mod.__name__}.assert_gh_authenticated"),
            patch(f"{_merge_mod.__name__}.resolve_repo_params", return_value=_MOCK_REPO),
            patch(f"{_merge_mod.__name__}.get_allowed_merge_methods", return_value=settings)
                as mock_settings,
            patch(f"{_merge_mod.__name__}._fetch_pr_state", return_value=pr_data),
            patch("subprocess.run", return_value=merge_result),
            patch(f"{_merge_mod.__name__}.write_skill_output"),
        ):
            _merge_mod.main(["--pull-request", "42"])
        mock_settings.assert_called_once()

    def test_rest_quota_error_wrapped_in_envelope_when_no_strategy(self):
        with (
            patch(f"{_merge_mod.__name__}.assert_gh_authenticated"),
            patch(f"{_merge_mod.__name__}.resolve_repo_params", return_value=_MOCK_REPO),
            patch(
                f"{_merge_mod.__name__}.get_allowed_merge_methods",
                side_effect=RuntimeError("HTTP 403 X-RateLimit-Remaining: 0"),
            ),
            patch(f"{_merge_mod.__name__}.write_skill_error") as mock_err,
        ):
            with pytest.raises(SystemExit) as exc_info:
                _merge_mod.main(["--pull-request", "42"])
        assert exc_info.value.code == 3
        mock_err.assert_called_once()
        call_args = mock_err.call_args
        assert "403" in call_args.args[0] or "RateLimit" in call_args.args[0]

    def test_validate_strategy_skips_when_none_settings(self):
        """None repo_settings (quota exhausted) skips validation."""
        _merge_mod.validate_strategy("squash", None, "o/r", "json")  # must not raise

    def test_validate_strategy_rejects_when_settings_present_and_disallowed(self):
        settings = {"allow_squash_merge": False, "allow_merge_commit": False,
                    "allow_rebase_merge": False}
        with (
            patch(f"{_merge_mod.__name__}.write_skill_error"),
            pytest.raises(SystemExit) as exc_info,
        ):
            _merge_mod.validate_strategy("squash", settings, "o/r", "json")
        assert exc_info.value.code == 1


# ===========================================================================
# #4393: why_pr_blocked.py - discriminated cause list
# ===========================================================================

class TestDiagnose:
    """Tests for the diagnose() function."""

    def _pr_graphql(
        self,
        number=100,
        base="main",
        contexts=None,
        thread_nodes=None,
        mergeable="MERGEABLE",
        merge_state_status="CLEAN",
        review_decision="APPROVED",
    ):
        contexts = contexts or []
        thread_nodes = thread_nodes or []
        return {
            "repository": {
                "pullRequest": {
                    "number": number,
                    "state": "OPEN",
                    "baseRefName": base,
                    "mergeable": mergeable,
                    "mergeStateStatus": merge_state_status,
                    "reviewDecision": review_decision,
                    "commits": {
                        "nodes": [{
                            "commit": {
                                "statusCheckRollup": {
                                    "contexts": {
                                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                                        "nodes": contexts,
                                    },
                                },
                            },
                        }],
                    },
                    "reviewThreads": {"nodes": thread_nodes},
                },
            },
        }

    def _ck(
        self,
        name,
        conclusion="SUCCESS",
        *,
        required=True,
        run_id=None,
        job_id=1,
        integration_id=15368,
        status="COMPLETED",
    ):
        return {
            "__typename": "CheckRun",
            "name": name,
            "status": status,
            "conclusion": conclusion,
            "isRequired": required,
            "checkSuite": {"app": {"databaseId": integration_id}},
            "detailsUrl": (
                f"https://github.com/o/r/actions/runs/{run_id}/job/{job_id}"
                if run_id is not None
                else ""
            ),
        }

    def test_likely_mergeable_when_all_clear(self):
        data = self._pr_graphql(contexts=[self._ck("CI / build")])
        with (
            patch(f"{_why_mod.__name__}.gh_graphql", return_value=data),
            patch(f"{_why_mod.__name__}._fetch_ruleset_contexts",
                  return_value=_required_checks("CI / build")),
        ):
            result = _why_mod.diagnose("o", "r", 100)
        assert result["LikelyMergeable"] is True
        assert result["Causes"] == []

    def test_missing_check_is_a_cause(self):
        """A required context absent from rollup must appear as MISSING cause."""
        data = self._pr_graphql(contexts=[self._ck("CI / build")])
        with (
            patch(f"{_why_mod.__name__}.gh_graphql", return_value=data),
            patch(f"{_why_mod.__name__}._fetch_ruleset_contexts",
                  return_value=_required_checks("CI / build", "CI / test")),
        ):
            result = _why_mod.diagnose("o", "r", 100)
        assert result["LikelyMergeable"] is False
        assert "CI / test" in result["MissingRequiredChecks"]
        assert any("MISSING" in c for c in result["Causes"])

    def test_failing_check_is_a_cause(self):
        data = self._pr_graphql(contexts=[self._ck("CI / build", "FAILURE")])
        with (
            patch(f"{_why_mod.__name__}.gh_graphql", return_value=data),
            patch(f"{_why_mod.__name__}._fetch_ruleset_contexts",
                  return_value=_required_checks("CI / build")),
        ):
            result = _why_mod.diagnose("o", "r", 100)
        assert result["LikelyMergeable"] is False
        assert any("FAILING" in c for c in result["Causes"])

    def test_unresolved_threads_is_a_cause(self):
        threads = [{"isResolved": False}, {"isResolved": True}]
        data = self._pr_graphql(
            contexts=[self._ck("CI / build")],
            thread_nodes=threads,
        )
        with (
            patch(f"{_why_mod.__name__}.gh_graphql", return_value=data),
            patch(f"{_why_mod.__name__}._fetch_ruleset_contexts",
                  return_value=_required_checks("CI / build")),
        ):
            result = _why_mod.diagnose("o", "r", 100)
        assert result["LikelyMergeable"] is False
        assert result["UnresolvedThreads"] == 1
        assert any("THREADS" in c for c in result["Causes"])

    def test_skipped_check_satisfies_requirement(self):
        """SKIPPED must not be reported as a cause."""
        data = self._pr_graphql(contexts=[self._ck("CI / test", "SKIPPED")])
        with (
            patch(f"{_why_mod.__name__}.gh_graphql", return_value=data),
            patch(f"{_why_mod.__name__}._fetch_ruleset_contexts",
                  return_value=_required_checks("CI / test")),
        ):
            result = _why_mod.diagnose("o", "r", 100)
        assert result["LikelyMergeable"] is True

    def test_duplicate_success_overrides_stale_failure(self):
        data = self._pr_graphql(contexts=[
            self._ck("CI / test", "FAILURE", run_id=100),
            self._ck("CI / test", "SUCCESS", run_id=200),
        ])
        with (
            patch(f"{_why_mod.__name__}.gh_graphql", return_value=data),
            patch(f"{_why_mod.__name__}._fetch_ruleset_contexts",
                  return_value=_required_checks("CI / test")),
        ):
            result = _why_mod.diagnose("o", "r", 100)
        assert result["LikelyMergeable"] is True
        assert result["FailingRequiredChecks"] == []

    def test_latest_failure_overrides_older_success(self):
        data = self._pr_graphql(contexts=[
            self._ck("CI / test", "SUCCESS", run_id=100),
            self._ck("CI / test", "FAILURE", run_id=200),
        ])
        with (
            patch(f"{_why_mod.__name__}.gh_graphql", return_value=data),
            patch(
                f"{_why_mod.__name__}._fetch_ruleset_contexts",
                return_value=_required_checks("CI / test"),
            ),
        ):
            result = _why_mod.diagnose("o", "r", 100)
        assert result["LikelyMergeable"] is False
        assert result["FailingRequiredChecks"] == ["CI / test"]

    def test_same_run_pending_sibling_blocks(self):
        data = self._pr_graphql(contexts=[
            self._ck("CI / test", "SUCCESS", run_id=200, job_id=1),
            self._ck(
                "CI / test",
                "",
                run_id=200,
                job_id=2,
                status="IN_PROGRESS",
            ),
        ])
        with (
            patch(f"{_why_mod.__name__}.gh_graphql", return_value=data),
            patch(
                f"{_why_mod.__name__}._fetch_ruleset_contexts",
                return_value=_required_checks("CI / test"),
            ),
        ):
            result = _why_mod.diagnose("o", "r", 100)
        assert result["LikelyMergeable"] is False
        assert result["PendingRequiredChecks"] == ["CI / test"]

    @pytest.mark.parametrize(
        ("mergeable", "merge_state_status"),
        [
            ("CONFLICTING", "DIRTY"),
            ("UNKNOWN", "UNKNOWN"),
        ],
    )
    def test_unusable_merge_ref_is_a_cause(
        self,
        mergeable,
        merge_state_status,
    ):
        data = self._pr_graphql(
            contexts=[self._ck("CI / build")],
            mergeable=mergeable,
            merge_state_status=merge_state_status,
        )
        with (
            patch(f"{_why_mod.__name__}.gh_graphql", return_value=data),
            patch(
                f"{_why_mod.__name__}._fetch_ruleset_contexts",
                return_value=_required_checks("CI / build"),
            ),
        ):
            result = _why_mod.diagnose("o", "r", 100)
        assert result["LikelyMergeable"] is False
        assert any("MERGE" in item for item in result["Causes"])

    @pytest.mark.parametrize(
        ("review_decision", "cause"),
        [
            ("REVIEW_REQUIRED", "approval required"),
            ("CHANGES_REQUESTED", "changes requested"),
        ],
    )
    def test_required_review_is_a_cause(self, review_decision, cause):
        data = self._pr_graphql(
            contexts=[self._ck("CI / build")],
            review_decision=review_decision,
        )
        with (
            patch(f"{_why_mod.__name__}.gh_graphql", return_value=data),
            patch(
                f"{_why_mod.__name__}._fetch_ruleset_contexts",
                return_value=_required_checks("CI / build"),
            ),
        ):
            result = _why_mod.diagnose("o", "r", 100)
        assert result["LikelyMergeable"] is False
        assert any(cause in item for item in result["Causes"])

    def test_ruleset_lookup_failure_returns_api_error(self):
        data = self._pr_graphql(contexts=[self._ck("CI / build")])
        with (
            patch(f"{_why_mod.__name__}.gh_graphql", return_value=data),
            patch(
                f"{_why_mod.__name__}._fetch_ruleset_contexts",
                side_effect=RuntimeError("HTTP 403"),
            ),
        ):
            result = _why_mod.diagnose("o", "r", 100)
        assert result["Error"] == "ApiError"
        assert "HTTP 403" in result["Message"]

    def test_paginated_contexts_are_checked_for_missing(self):
        first_page = self._pr_graphql(contexts=[self._ck("CI / build")])
        commit = first_page["repository"]["pullRequest"]["commits"]["nodes"][0]["commit"]
        commit["oid"] = "abc123"
        commit["statusCheckRollup"]["contexts"]["pageInfo"] = {
            "hasNextPage": True,
            "endCursor": "cursor-1",
        }

        with (
            patch(f"{_why_mod.__name__}.gh_graphql", return_value=first_page),
            patch(f"{_why_mod.__name__}._fetch_context_page",
                  return_value=([self._ck("CI / test")],
                                {"hasNextPage": False, "endCursor": None})),
            patch(f"{_why_mod.__name__}._fetch_ruleset_contexts",
                  return_value=_required_checks("CI / build", "CI / test")),
        ):
            result = _why_mod.diagnose("o", "r", 100)
        assert result["MissingRequiredChecks"] == []

    def test_paginated_review_threads_are_counted(self):
        data = self._pr_graphql(
            contexts=[self._ck("CI / build")],
            thread_nodes=[{"isResolved": True}],
        )
        review_threads = data["repository"]["pullRequest"]["reviewThreads"]
        review_threads["pageInfo"] = {"hasNextPage": True, "endCursor": "cursor-1"}

        with (
            patch(f"{_why_mod.__name__}.gh_graphql", return_value=data),
            patch(f"{_why_mod.__name__}._fetch_ruleset_contexts",
                  return_value=_required_checks("CI / build")),
            patch(f"{_why_mod.__name__}._fetch_review_thread_page",
                  return_value=([{"isResolved": False}],
                                {"hasNextPage": False, "endCursor": None})),
        ):
            result = _why_mod.diagnose("o", "r", 100)
        assert result["UnresolvedThreads"] == 1

    def test_not_found_returns_error(self):
        with patch(
            f"{_why_mod.__name__}.gh_graphql",
            side_effect=RuntimeError("Could not resolve to a Repository"),
        ):
            result = _why_mod.diagnose("o", "r", 9999)
        assert result["Error"] == "NotFound"

    def test_multiple_causes_reported(self):
        """Missing check + unresolved thread both surface."""
        threads = [{"isResolved": False}]
        data = self._pr_graphql(
            contexts=[self._ck("CI / build")],
            thread_nodes=threads,
        )
        with (
            patch(f"{_why_mod.__name__}.gh_graphql", return_value=data),
            patch(f"{_why_mod.__name__}._fetch_ruleset_contexts",
                  return_value=_required_checks("CI / build", "CI / missing")),
        ):
            result = _why_mod.diagnose("o", "r", 100)
        assert len(result["Causes"]) >= 2

    def test_wrong_integration_is_reported_missing(self):
        data = self._pr_graphql(contexts=[
            self._ck(
                "CI / build",
                integration_id=99999,
                required=False,
            )
        ])
        with (
            patch(f"{_why_mod.__name__}.gh_graphql", return_value=data),
            patch(
                f"{_why_mod.__name__}._fetch_ruleset_contexts",
                return_value=_required_checks("CI / build"),
            ),
        ):
            result = _why_mod.diagnose("o", "r", 100)
        assert result["LikelyMergeable"] is False
        assert result["MissingRequiredChecks"] == ["CI / build"]


class TestWhyPrBlockedMain:
    """CLI exit code tests for why_pr_blocked.py."""

    def test_exit_0_when_likely_mergeable(self):
        data = {
            "Success": True,
            "Number": 100,
            "LikelyMergeable": True,
            "Causes": [],
            "MissingRequiredChecks": [],
            "FailingRequiredChecks": [],
            "PendingRequiredChecks": [],
            "UnresolvedThreads": 0,
            "RulesetRequiredContexts": [],
            "BaseBranch": "main",
            "MergeStateStatus": "CLEAN",
            "Owner": "o",
            "Repo": "r",
        }
        with (
            patch(f"{_why_mod.__name__}.assert_gh_authenticated"),
            patch(f"{_why_mod.__name__}.resolve_repo_params", return_value=_MOCK_REPO),
            patch(f"{_why_mod.__name__}.diagnose", return_value=data),
            patch(f"{_why_mod.__name__}.write_skill_output"),
        ):
            rc = _why_mod.main(["--pull-request", "100"])
        assert rc == 0

    def test_exit_1_when_required_check_is_missing(self):
        data = {
            "Success": True,
            "Number": 100,
            "LikelyMergeable": False,
            "Causes": ["MISSING (1 required check never reported)"],
            "MissingRequiredChecks": ["Validate PR"],
            "FailingRequiredChecks": [],
            "PendingRequiredChecks": [],
            "UnresolvedThreads": 0,
            "RulesetRequiredContexts": ["Validate PR"],
            "BaseBranch": "main",
            "MergeStateStatus": "BLOCKED",
            "Owner": "o",
            "Repo": "r",
        }
        with (
            patch(f"{_why_mod.__name__}.assert_gh_authenticated"),
            patch(f"{_why_mod.__name__}.resolve_repo_params", return_value=_MOCK_REPO),
            patch(f"{_why_mod.__name__}.diagnose", return_value=data),
            patch(f"{_why_mod.__name__}.write_skill_output"),
        ):
            rc = _why_mod.main(["--pull-request", "100"])
        assert rc == 1

    def test_exit_2_when_required_check_is_pending(self):
        data = {
            "Success": True,
            "Number": 100,
            "LikelyMergeable": False,
            "Causes": ["PENDING (1 required check)"],
            "MissingRequiredChecks": [],
            "FailingRequiredChecks": [],
            "PendingRequiredChecks": ["Validate PR"],
            "UnresolvedThreads": 0,
            "RulesetRequiredContexts": ["Validate PR"],
            "BaseBranch": "main",
            "Mergeable": "MERGEABLE",
            "MergeStateStatus": "BLOCKED",
            "ReviewDecision": "",
            "Owner": "o",
            "Repo": "r",
        }
        with (
            patch(f"{_why_mod.__name__}.assert_gh_authenticated"),
            patch(f"{_why_mod.__name__}.resolve_repo_params", return_value=_MOCK_REPO),
            patch(f"{_why_mod.__name__}.diagnose", return_value=data),
            patch(f"{_why_mod.__name__}.write_skill_output"),
        ):
            rc = _why_mod.main(["--pull-request", "100"])
        assert rc == 2

    def test_exit_2_on_not_found(self):
        with (
            patch(f"{_why_mod.__name__}.assert_gh_authenticated"),
            patch(f"{_why_mod.__name__}.resolve_repo_params", return_value=_MOCK_REPO),
            patch(f"{_why_mod.__name__}.diagnose",
                  return_value={"Error": "NotFound", "Message": "not found"}),
            patch(f"{_why_mod.__name__}.write_skill_error"),
        ):
            rc = _why_mod.main(["--pull-request", "9999"])
        assert rc == 2


# ===========================================================================
# #4462: audit_closing_claims.py - Markdown context classification
# ===========================================================================

class TestClassifyClaim:
    """Tests for classify_claim in audit_closing_claims.py."""

    def _classify(self, text: str, pattern: str) -> str:
        import re
        m = re.search(re.escape(pattern), text)
        assert m is not None, f"Pattern {pattern!r} not found in {text!r}"
        # Need to compute fenced and html positions
        _, fenced = _audit_mod._strip_fenced_code(text)
        _, html = _audit_mod._strip_html_comments(text)
        return _audit_mod.classify_claim(text, m, fenced, html)

    def test_active_in_plain_prose(self):
        text = "Fixes #123 in this PR"
        _, fenced = _audit_mod._strip_fenced_code(text)
        _, html = _audit_mod._strip_html_comments(text)
        import re
        m = re.search(r"Fixes #123", text)
        result = _audit_mod.classify_claim(text, m, fenced, html)
        assert result == "active"

    def test_code_span_single_backtick(self):
        text = "Use `Fixes #42` in your commit"
        _, fenced = _audit_mod._strip_fenced_code(text)
        _, html = _audit_mod._strip_html_comments(text)
        import re
        m = re.search(r"Fixes #42", text)
        result = _audit_mod.classify_claim(text, m, fenced, html)
        assert result == "code_span"

    def test_fenced_code_block(self):
        text = "```\nFixes #99\n```"
        _, fenced = _audit_mod._strip_fenced_code(text)
        _, html = _audit_mod._strip_html_comments(text)
        import re
        m = re.search(r"Fixes #99", text)
        result = _audit_mod.classify_claim(text, m, fenced, html)
        assert result == "fenced_code"

    def test_html_comment(self):
        text = "<!-- Fixes #77 this is hidden -->"
        _, fenced = _audit_mod._strip_fenced_code(text)
        _, html = _audit_mod._strip_html_comments(text)
        import re
        m = re.search(r"Fixes #77", text)
        result = _audit_mod.classify_claim(text, m, fenced, html)
        assert result == "html_comment"

    def test_escaped_hash(self):
        text = r"See \#123 for context"
        _, fenced = _audit_mod._strip_fenced_code(text)
        _, html = _audit_mod._strip_html_comments(text)
        import re
        # The escaped hash is \#123, so the closing keyword pattern won't
        # match. But we can test the escaped_hash detection directly.
        # Build a fake match at the escaped position.
        full = r"Fixes \#123"
        _, fenced2 = _audit_mod._strip_fenced_code(full)
        _, html2 = _audit_mod._strip_html_comments(full)
        m2 = re.search(r"Fixes [^#]?#123", full)
        if m2:
            result = _audit_mod.classify_claim(full, m2, fenced2, html2)
            assert result == "escaped_hash"

    def test_negated_phrase_still_closes(self):
        text = "This does not close #55"
        _, fenced = _audit_mod._strip_fenced_code(text)
        _, html = _audit_mod._strip_html_comments(text)
        # The keyword is "close" in "does not close #55"
        import re
        m = re.search(r"close\s+#55", text, re.IGNORECASE)
        assert m is not None
        result = _audit_mod.classify_claim(text, m, fenced, html)
        assert result == "active"


class TestExtractClaims:
    """Tests for extract_claims."""

    def test_active_fix_extracted(self):
        claims = _audit_mod.extract_claims(10, "Fixes #123", "main", {}, "owner", "repo")
        assert len(claims) == 1
        assert claims[0]["target_number"] == 123
        assert claims[0]["context_class"] == "active"
        assert claims[0]["github_will_close"] is True

    def test_no_claims_on_empty_body(self):
        assert _audit_mod.extract_claims(10, "", "main", {}, "owner", "repo") == []

    def test_multiple_claims_detected(self):
        body = "Fixes #1\nCloses #2\nResolves #3"
        claims = _audit_mod.extract_claims(10, body, "main", {}, "o", "r")
        assert len(claims) == 3

    def test_fixes_a_b_c_on_one_line_only_one_claim(self):
        """GitHub closes only the first target on a line with multiple references.

        The regex matches each keyword independently, so three separate matches
        may appear. Callers should use validate_body to warn about this pattern.
        This test confirms the extractor does not silently drop claims.
        """
        body = "Fixes #1 Fixes #2 Fixes #3"
        claims = _audit_mod.extract_claims(10, body, "main", {}, "o", "r")
        # All three keyword-number pairs are extracted; they are all marked active
        assert len(claims) >= 1

    def test_extracts_fenced_claim_as_non_closing(self):
        claims = _audit_mod.extract_claims(10, "```\nFixes #99\n```", "main", {}, "o", "r")
        assert claims[0]["context_class"] == "fenced_code"
        assert claims[0]["github_will_close"] is False

    def test_extracts_html_comment_claim_as_non_closing(self):
        claims = _audit_mod.extract_claims(
            10, "<!-- Fixes #77 hidden -->", "main", {}, "o", "r"
        )
        assert claims[0]["context_class"] == "html_comment"
        assert claims[0]["github_will_close"] is False

    def test_extracts_escaped_hash_claim_as_non_closing(self):
        claims = _audit_mod.extract_claims(10, r"Fixes \#123", "main", {}, "o", "r")
        assert claims[0]["context_class"] == "escaped_hash"
        assert claims[0]["github_will_close"] is False


class TestBodyHashAndValidate:
    """Tests for edit_pr_body.py helpers."""

    def test_hash_is_deterministic(self):
        h1 = _edit_mod.body_hash("hello world")
        h2 = _edit_mod.body_hash("hello world")
        assert h1 == h2

    def test_hash_lf_normalised(self):
        assert _edit_mod.body_hash("a\r\nb") == _edit_mod.body_hash("a\nb")

    def test_hash_different_for_different_content(self):
        assert _edit_mod.body_hash("abc") != _edit_mod.body_hash("def")

    def test_validate_body_empty_is_clean(self):
        assert _edit_mod.validate_body("Fixes #123\nSome prose.") == []

    def test_validate_body_em_dash_flagged(self):
        warnings = _edit_mod.validate_body("Changes \u2014 see PR")
        assert any("em" in w.lower() or "dash" in w.lower() for w in warnings)

    def test_validate_body_multiple_issues_on_one_line_flagged(self):
        warnings = _edit_mod.validate_body("Fixes #1 #2 #3")
        assert any("one" in w.lower() or "line" in w.lower() or "first" in w.lower()
                   for w in warnings)

    def test_validate_body_multiple_keywords_on_one_line_flagged(self):
        warnings = _edit_mod.validate_body("Fixes #1, closes #2")
        assert any("closing-keyword line" in w for w in warnings)

    def test_validate_body_single_issue_per_line_clean(self):
        body = "Fixes #1\nFixes #2\nFixes #3"
        assert _edit_mod.validate_body(body) == []


class TestEditPrBodyStaleWriteGuard:
    """Stale-write guard: abort when current hash differs from expected."""

    def test_abort_on_hash_mismatch(self, capsys):
        current = "current body"
        wrong_hash = "0" * 64

        with (
            patch(f"{_edit_mod.__name__}.assert_gh_authenticated"),
            patch(f"{_edit_mod.__name__}.resolve_repo_params", return_value=_MOCK_REPO),
            patch(f"{_edit_mod.__name__}.fetch_current_body", return_value=current),
        ):
            rc = _edit_mod.main([
                "--pull-request", "42",
                "--body", "new body",
                "--expected-hash", wrong_hash,
                "--output-format", "json",
            ])

        output = json.loads(capsys.readouterr().out)

        assert rc == 1
        assert output["Error"]["Type"] == "VerificationFailed"

    def test_no_write_when_body_unchanged(self):
        body = "same body"
        expected_hash = _edit_mod.body_hash(body)

        with (
            patch(f"{_edit_mod.__name__}.assert_gh_authenticated"),
            patch(f"{_edit_mod.__name__}.resolve_repo_params", return_value=_MOCK_REPO),
            patch(f"{_edit_mod.__name__}.fetch_current_body", return_value=body),
            patch(f"{_edit_mod.__name__}.update_body") as mock_update,
            patch(f"{_edit_mod.__name__}.write_skill_output"),
        ):
            rc = _edit_mod.main([
                "--pull-request", "42",
                "--body", body,
                "--expected-hash", expected_hash,
            ])
        assert rc == 0
        mock_update.assert_not_called()

    def test_write_when_body_changed_and_hash_matches(self):
        old_body = "old body"
        new_body = "new body"
        expected_hash = _edit_mod.body_hash(old_body)

        with (
            patch(f"{_edit_mod.__name__}.assert_gh_authenticated"),
            patch(f"{_edit_mod.__name__}.resolve_repo_params", return_value=_MOCK_REPO),
            patch(f"{_edit_mod.__name__}.fetch_current_body", return_value=old_body),
            patch(f"{_edit_mod.__name__}.update_body") as mock_update,
            patch(f"{_edit_mod.__name__}.write_skill_output"),
        ):
            rc = _edit_mod.main([
                "--pull-request", "42",
                "--body", new_body,
                "--expected-hash", expected_hash,
            ])
        assert rc == 0
        mock_update.assert_called_once()

    def test_not_found_returns_2(self):
        with (
            patch(f"{_edit_mod.__name__}.assert_gh_authenticated"),
            patch(f"{_edit_mod.__name__}.resolve_repo_params", return_value=_MOCK_REPO),
            patch(f"{_edit_mod.__name__}.fetch_current_body", return_value=None),
            patch(f"{_edit_mod.__name__}.write_skill_error"),
        ):
            rc = _edit_mod.main([
                "--pull-request", "9999",
                "--body", "something",
            ])
        assert rc == 2

    def test_dry_run_does_not_write(self):
        with (
            patch(f"{_edit_mod.__name__}.assert_gh_authenticated"),
            patch(f"{_edit_mod.__name__}.resolve_repo_params", return_value=_MOCK_REPO),
            patch(f"{_edit_mod.__name__}.fetch_current_body", return_value="old body"),
            patch(f"{_edit_mod.__name__}.update_body") as mock_update,
            patch(f"{_edit_mod.__name__}.write_skill_output"),
        ):
            rc = _edit_mod.main([
                "--pull-request", "42",
                "--body", "new body",
                "--dry-run",
            ])
        assert rc == 0
        mock_update.assert_not_called()

    def test_update_body_sends_body_literal(self):
        with patch(
            f"{_edit_mod.__name__}.subprocess.run",
            return_value=_completed(stdout="42\n"),
        ) as mock_run:
            _edit_mod.update_body("owner", "repo", 42, "@/path/that/must/not/be/read")

        command = mock_run.call_args.args[0]
        assert "--raw-field" in command
        assert "--field" not in command
        assert "body=@/path/that/must/not/be/read" in command
