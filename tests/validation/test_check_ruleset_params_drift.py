"""Tests for check_ruleset_params_drift.py."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

sys.path.insert(
    0, str(Path(__file__).resolve().parents[2] / "scripts" / "validation")
)
import check_ruleset_params_drift as mod

# Matches scripts/validation/ruleset_params_baseline.json's "ruleset" section
# so TestMainLive's default mock stays in sync with the committed baseline.
_DEFAULT_ENFORCEMENT = "active"
_DEFAULT_BYPASS_ACTORS = [
    {"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"}
]


class TestCheckDrift:
    """Unit tests for the parameter drift comparison logic."""

    def test_no_drift(self):
        baseline = {"parameters": {"strict_required_status_checks_policy": False}}
        live = {"strict_required_status_checks_policy": False}
        assert mod.check_drift(baseline, live) == []

    def test_drift_detected(self):
        baseline = {"parameters": {"strict_required_status_checks_policy": False}}
        live = {"strict_required_status_checks_policy": True}
        drifts = mod.check_drift(baseline, live)
        assert len(drifts) == 1
        assert "expected=False" in drifts[0]
        assert "actual=True" in drifts[0]

    def test_missing_key_in_live(self):
        baseline = {"parameters": {"strict_required_status_checks_policy": False}}
        live = {}
        drifts = mod.check_drift(baseline, live)
        assert len(drifts) == 1
        assert "not found" in drifts[0]

    def test_multiple_params(self):
        baseline = {
            "parameters": {
                "strict_required_status_checks_policy": False,
                "required_review_thread_resolution": True,
            }
        }
        live = {
            "strict_required_status_checks_policy": False,
            "required_review_thread_resolution": True,
        }
        assert mod.check_drift(baseline, live) == []

    def test_unknown_live_param_is_drift(self) -> None:
        """A live parameter absent from the baseline is now reported, not ignored.

        This is the core defect fix: check_drift() used to iterate only
        baseline_params.items(), so an added rule or a widened permission
        with no baseline entry was invisible.
        """
        baseline = {"parameters": {"strict_required_status_checks_policy": False}}
        live = {
            "strict_required_status_checks_policy": False,
            "require_linear_history": True,
        }
        drifts = mod.check_drift(baseline, live)
        assert len(drifts) == 1
        assert "require_linear_history" in drifts[0]
        assert "True" in drifts[0]

    def test_delegated_key_excluded_from_unknown_key_detection(self) -> None:
        """required_status_checks is never flagged as an unknown live key.

        Regression pin for the constraint in
        .serena/memories/decision-ruleset-drift-must-not-create-a-second-baseline.md:
        scripts/ci/ruleset_required_contexts.py owns REQUIRED_CONTEXTS and no
        second baseline of the required contexts may exist here.
        """
        baseline = {"parameters": {"strict_required_status_checks_policy": False}}
        live = {
            "strict_required_status_checks_policy": False,
            "required_status_checks": [{"context": "Validate PR"}],
        }
        assert mod.check_drift(baseline, live) == []

    def test_delegated_key_in_baseline_is_not_value_compared(self) -> None:
        """A delegated key placed in the baseline by mistake is not compared.

        Defensive: DELEGATED_PARAM_KEYS is excluded from the baseline-to-live
        value comparison as well as unknown-key detection, so this module
        never becomes a second source of truth for required contexts even if
        someone adds the key to the baseline file.
        """
        baseline = {
            "parameters": {
                "strict_required_status_checks_policy": False,
                "required_status_checks": [{"context": "Old Context"}],
            }
        }
        live = {
            "strict_required_status_checks_policy": False,
            "required_status_checks": [{"context": "New Context"}],
        }
        assert mod.check_drift(baseline, live) == []


class TestBypassActorSortKey:
    """Sort key must not raise on actors with missing or non-int fields."""

    def test_heterogeneous_actors_sort_without_raising(self) -> None:
        baseline: dict[str, Any] = {
            "ruleset": {
                "enforcement": "active",
                "bypass_actors": [
                    {"actor_id": 5, "actor_type": "RepositoryRole",
                     "bypass_mode": "always"},
                    {"actor_type": "DeployKey", "bypass_mode": "always"},
                ],
            }
        }
        live: dict[str, Any] = {
            "enforcement": "active",
            "bypass_actors": [
                {"actor_type": "DeployKey", "bypass_mode": "always"},
                {"actor_id": 5, "actor_type": "RepositoryRole",
                 "bypass_mode": "always"},
            ],
        }
        assert mod.check_ruleset_drift(baseline, live) == []


class TestCheckRulesetDrift:
    """Unit tests for the top-level ruleset state comparison (enforcement,
    bypass_actors), which fetch_live_params() previously never fetched."""

    def _baseline(self, enforcement: str = "active", bypass_actors=None) -> dict:
        if bypass_actors is None:
            bypass_actors = list(_DEFAULT_BYPASS_ACTORS)
        return {"ruleset": {"enforcement": enforcement, "bypass_actors": bypass_actors}}

    def test_no_drift_when_matching(self) -> None:
        baseline = self._baseline()
        live = {
            "enforcement": "active",
            "bypass_actors": list(_DEFAULT_BYPASS_ACTORS),
        }
        assert mod.check_ruleset_drift(baseline, live) == []

    def test_enforcement_change_is_drift(self) -> None:
        baseline = self._baseline(enforcement="active")
        live = {"enforcement": "evaluate", "bypass_actors": list(_DEFAULT_BYPASS_ACTORS)}
        drifts = mod.check_ruleset_drift(baseline, live)
        assert len(drifts) == 1
        assert "enforcement" in drifts[0]
        assert "expected='active'" in drifts[0]
        assert "actual='evaluate'" in drifts[0]

    def test_added_bypass_actor_is_drift(self) -> None:
        """An added bypass actor is the highest-value signal this check exists for."""
        baseline = self._baseline()
        extra_actor = {"actor_id": 99, "actor_type": "Team", "bypass_mode": "always"}
        live = {
            "enforcement": "active",
            "bypass_actors": [*_DEFAULT_BYPASS_ACTORS, extra_actor],
        }
        drifts = mod.check_ruleset_drift(baseline, live)
        assert len(drifts) == 1
        assert "bypass_actors" in drifts[0]

    def test_removed_bypass_actor_is_drift(self) -> None:
        baseline = self._baseline()
        live = {"enforcement": "active", "bypass_actors": []}
        drifts = mod.check_ruleset_drift(baseline, live)
        assert len(drifts) == 1
        assert "bypass_actors" in drifts[0]

    def test_modified_bypass_actor_is_drift(self) -> None:
        """Same actor_id, different bypass_mode: a modification, not a reorder."""
        baseline = self._baseline()
        modified_actor = {
            "actor_id": 5,
            "actor_type": "RepositoryRole",
            "bypass_mode": "pull_request",
        }
        live = {"enforcement": "active", "bypass_actors": [modified_actor]}
        drifts = mod.check_ruleset_drift(baseline, live)
        assert len(drifts) == 1
        assert "bypass_actors" in drifts[0]

    def test_reordered_bypass_actors_not_drift(self) -> None:
        """Same actors in a different order is not drift; GitHub reorders freely."""
        actor_a = {"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"}
        actor_b = {"actor_id": 99, "actor_type": "Team", "bypass_mode": "always"}
        baseline = self._baseline(bypass_actors=[actor_a, actor_b])
        live = {"enforcement": "active", "bypass_actors": [actor_b, actor_a]}
        assert mod.check_ruleset_drift(baseline, live) == []


class TestMainOffline:
    """Test the --offline flag."""

    def test_offline_skips(self, capsys):
        rc = mod.main(["--offline"])
        assert rc == 0
        assert "SKIP" in capsys.readouterr().out


class TestMainLive:
    """Integration-style tests with mocked subprocess.

    The mock defaults to the exact "ruleset" section of the committed
    baseline (scripts/validation/ruleset_params_baseline.json) so a test that
    only wants to vary rule-level parameters does not also trip top-level
    ruleset drift.
    """

    def _mock_gh(
        self,
        params: dict,
        enforcement: str = _DEFAULT_ENFORCEMENT,
        bypass_actors: list | None = None,
    ):
        """Return a mock that simulates gh api returning given ruleset state."""
        if bypass_actors is None:
            bypass_actors = list(_DEFAULT_BYPASS_ACTORS)
        rules = [{"type": "required_status_checks", "parameters": params}]
        payload = json.dumps(
            {
                "rules": rules,
                "enforcement": enforcement,
                "bypass_actors": bypass_actors,
            }
        )
        return subprocess.CompletedProcess(
            args=[], returncode=0, stdout=payload, stderr=""
        )

    def _matching_params(self) -> dict:
        """Rule parameters matching every non-delegated key in the baseline."""
        return {
            "allowed_merge_methods": ["squash"],
            "dismiss_stale_reviews_on_push": True,
            "do_not_enforce_on_create": False,
            "require_code_owner_review": False,
            "require_extra_approval_for_unattributed_changes": True,
            "require_last_push_approval": False,
            "required_approving_review_count": 0,
            "required_review_thread_resolution": True,
            "required_reviewers": [],
            "review_draft_pull_requests": False,
            "review_on_push": True,
            "strict_required_status_checks_policy": False,
        }

    def test_match_returns_zero(self, capsys):
        with patch("subprocess.run", return_value=self._mock_gh(self._matching_params())):
            rc = mod.main([])
        assert rc == 0
        assert "OK" in capsys.readouterr().out

    def test_drift_returns_one(self, capsys):
        live_params = self._matching_params()
        live_params["strict_required_status_checks_policy"] = True
        with patch("subprocess.run", return_value=self._mock_gh(live_params)):
            rc = mod.main([])
        assert rc == 1
        assert "DRIFT" in capsys.readouterr().out

    def test_api_failure_exits_auth(self):
        fail = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="auth failed"
        )
        with patch("subprocess.run", return_value=fail):
            with pytest.raises(SystemExit) as exc_info:
                mod.main([])
            assert exc_info.value.code == 4

    def test_api_failure_exits_external(self):
        fail = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="network timeout"
        )
        with patch("subprocess.run", return_value=fail):
            with pytest.raises(SystemExit) as exc_info:
                mod.main([])
            assert exc_info.value.code == 3

    def test_gh_not_found_exits_external(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(SystemExit) as exc_info:
                mod.main([])
            assert exc_info.value.code == 3

    def test_added_bypass_actor_returns_one(self, capsys) -> None:
        """CLI-level proof that an added bypass actor fails the check.

        main([]) returning 1 is the assertion, not check_ruleset_drift()'s
        return value alone (testing.md MUST-8).
        """
        extra_actor = {"actor_id": 99, "actor_type": "Team", "bypass_mode": "always"}
        mock = self._mock_gh(
            self._matching_params(),
            bypass_actors=[*_DEFAULT_BYPASS_ACTORS, extra_actor],
        )
        with patch("subprocess.run", return_value=mock):
            rc = mod.main([])
        assert rc == 1
        assert "bypass_actors" in capsys.readouterr().out

    def test_removed_bypass_actor_returns_one(self, capsys) -> None:
        mock = self._mock_gh(self._matching_params(), bypass_actors=[])
        with patch("subprocess.run", return_value=mock):
            rc = mod.main([])
        assert rc == 1
        assert "bypass_actors" in capsys.readouterr().out

    def test_enforcement_change_returns_one(self, capsys) -> None:
        mock = self._mock_gh(self._matching_params(), enforcement="evaluate")
        with patch("subprocess.run", return_value=mock):
            rc = mod.main([])
        assert rc == 1
        assert "enforcement" in capsys.readouterr().out

    def test_unknown_live_param_returns_one(self, capsys) -> None:
        live_params = self._matching_params()
        live_params["require_linear_history"] = True
        with patch("subprocess.run", return_value=self._mock_gh(live_params)):
            rc = mod.main([])
        assert rc == 1
        assert "require_linear_history" in capsys.readouterr().out

    def test_required_status_checks_delegated_not_reported(self, capsys) -> None:
        """Edge case, regression pin: the delegated key never causes drift here.

        Even though required_status_checks is not in the baseline and its
        live value is a 9-entry context list, main() must exit 0. Ownership
        lives at scripts/ci/ruleset_required_contexts.py per the
        must-not-create-a-second-baseline decision.
        """
        live_params = self._matching_params()
        live_params["required_status_checks"] = [
            {"context": f"Check {i}"} for i in range(9)
        ]
        with patch("subprocess.run", return_value=self._mock_gh(live_params)):
            rc = mod.main([])
        assert rc == 0
        assert "OK" in capsys.readouterr().out

    def test_bypass_actors_reordered_returns_zero(self, capsys) -> None:
        reordered = list(reversed(_DEFAULT_BYPASS_ACTORS))
        mock = self._mock_gh(self._matching_params(), bypass_actors=reordered)
        with patch("subprocess.run", return_value=mock):
            rc = mod.main([])
        assert rc == 0
        assert "OK" in capsys.readouterr().out


class TestEdgeCases:
    """Edge cases: malformed baseline, unknown live params, delegated keys."""

    def test_malformed_baseline_exits_config(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("not json{{{", encoding="utf-8")
        with patch.object(mod, "BASELINE_PATH", bad):
            with pytest.raises(SystemExit) as exc_info:
                mod.main([])
            assert exc_info.value.code == mod.EXIT_CONFIG

    def test_missing_parameters_key_exits_config(self, tmp_path: Path) -> None:
        no_params = tmp_path / "no_params.json"
        no_params.write_text('{"ruleset_id": 1}', encoding="utf-8")
        with patch.object(mod, "BASELINE_PATH", no_params):
            with pytest.raises(SystemExit) as exc_info:
                mod.main([])
            assert exc_info.value.code == mod.EXIT_CONFIG

    def test_missing_ruleset_section_exits_config(self, tmp_path: Path) -> None:
        """A baseline with 'parameters' but no 'ruleset' section is config error.

        Same treatment as today's missing-'parameters' handling: the new
        top-level state section is mandatory, not optional.
        """
        no_ruleset = tmp_path / "no_ruleset.json"
        no_ruleset.write_text(
            json.dumps({"ruleset_id": 1, "parameters": {}}), encoding="utf-8"
        )
        with patch.object(mod, "BASELINE_PATH", no_ruleset):
            with pytest.raises(SystemExit) as exc_info:
                mod.main([])
            assert exc_info.value.code == mod.EXIT_CONFIG

    def test_ruleset_section_missing_bypass_actors_exits_config(
        self, tmp_path: Path
    ) -> None:
        """A malformed 'ruleset' section (missing a required subkey) is config error."""
        malformed = tmp_path / "malformed_ruleset.json"
        malformed.write_text(
            json.dumps(
                {
                    "ruleset_id": 1,
                    "parameters": {},
                    "ruleset": {"enforcement": "active"},
                }
            ),
            encoding="utf-8",
        )
        with patch.object(mod, "BASELINE_PATH", malformed):
            with pytest.raises(SystemExit) as exc_info:
                mod.main([])
            assert exc_info.value.code == mod.EXIT_CONFIG

    def test_unknown_live_params_are_reported_as_drift(self) -> None:
        """Live params not in the baseline are now drift, not ignored.

        Was test_extra_live_params_ignored, asserting drifts == [] under the
        old one-directional contract. check_drift() now also iterates
        live.items(), so an added rule or a widened permission is caught.
        """
        baseline: dict[str, Any] = {
            "parameters": {"strict_required_status_checks_policy": False}
        }
        live: dict[str, Any] = {
            "strict_required_status_checks_policy": False,
            "require_linear_history": True,
            "do_not_enforce_on_create": False,
        }
        drifts = mod.check_drift(baseline, live)
        assert len(drifts) == 2
        joined = "\n".join(drifts)
        assert "require_linear_history" in joined
        assert "do_not_enforce_on_create" in joined

    def test_realistic_multi_rule_payload(self) -> None:
        """Full baseline matches the full multi-rule live payload (real API shape).

        Was test_realistic_multi_rule_payload, previously asserting
        drifts == [] with 5 baseline-absent live params ignored. Under the
        bidirectional contract the baseline now carries every non-delegated
        key, and required_status_checks (delegated) is still excluded from
        comparison even though it is present in live and absent from
        baseline.
        """
        baseline: dict[str, Any] = {
            "parameters": {
                "strict_required_status_checks_policy": False,
                "required_review_thread_resolution": True,
                "required_approving_review_count": 0,
                "do_not_enforce_on_create": False,
                "dismiss_stale_reviews_on_push": True,
                "require_code_owner_review": False,
                "allowed_merge_methods": ["squash"],
            }
        }
        live: dict[str, Any] = {
            "strict_required_status_checks_policy": False,
            "required_review_thread_resolution": True,
            "required_approving_review_count": 0,
            "do_not_enforce_on_create": False,
            "required_status_checks": [{"context": "Validate PR"}],
            "dismiss_stale_reviews_on_push": True,
            "require_code_owner_review": False,
            "allowed_merge_methods": ["squash"],
        }
        drifts = mod.check_drift(baseline, live)
        assert drifts == []
