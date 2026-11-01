"""Tests for the `bypass_actors` not-observable state in check_ruleset_params_drift.py.

The Actions GITHUB_TOKEN cannot read `bypass_actors`: the API omits the key.
That is a distinct state from "present and matching" and from "present and
drifted". These tests pin all three, plus the empty-list and null edge cases.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "validation"))
import check_ruleset_params_drift as mod

_BASELINE_ACTORS = [{"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"}]
_EXTRA_ACTOR = {"actor_id": 99, "actor_type": "Team", "bypass_mode": "always"}
_NOT_OBSERVABLE = "NOT OBSERVABLE: bypass_actors"


def _baseline(enforcement: str = "active") -> dict[str, Any]:
    return {"ruleset": {"enforcement": enforcement, "bypass_actors": list(_BASELINE_ACTORS)}}


def _matching_params() -> dict[str, Any]:
    """Rule parameters matching every non-delegated key in the committed baseline."""
    baseline = mod.load_baseline()
    return {k: v for k, v in baseline["parameters"].items() if k not in mod.DELEGATED_PARAM_KEYS}


def _gh_response(
    params: dict[str, Any],
    *,
    enforcement: str = "active",
    bypass_actors: Any = "omit",
) -> subprocess.CompletedProcess[str]:
    """Simulate `gh api` output; `bypass_actors="omit"` drops the key entirely."""
    body: dict[str, Any] = {
        "rules": [{"type": "required_status_checks", "parameters": params}],
        "enforcement": enforcement,
    }
    if bypass_actors != "omit":
        body["bypass_actors"] = bypass_actors
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=json.dumps(body), stderr="")


class TestCheckRulesetDriftUnobservable:
    """Unit tests for the three bypass_actors states in check_ruleset_drift."""

    def test_present_and_matching_is_not_drift(self) -> None:
        live = {"enforcement": "active", "bypass_actors": list(_BASELINE_ACTORS)}
        assert mod.bypass_actors_observable(live) is True
        assert mod.check_ruleset_drift(_baseline(), live) == []

    def test_present_and_drifted_is_drift(self) -> None:
        live = {"enforcement": "active", "bypass_actors": [*_BASELINE_ACTORS, _EXTRA_ACTOR]}
        drifts = mod.check_ruleset_drift(_baseline(), live)
        assert len(drifts) == 1
        assert "bypass_actors" in drifts[0]

    def test_absent_is_not_drift(self) -> None:
        live = mod.extract_live_ruleset_state({"enforcement": "active", "rules": []})
        assert live["bypass_actors"] is None
        assert mod.bypass_actors_observable(live) is False
        assert mod.check_ruleset_drift(_baseline(), live) == []

    def test_absent_still_compares_enforcement(self) -> None:
        live = mod.extract_live_ruleset_state({"enforcement": "disabled", "rules": []})
        drifts = mod.check_ruleset_drift(_baseline(enforcement="active"), live)
        assert len(drifts) == 1
        assert "enforcement" in drifts[0]

    def test_empty_list_is_observable_and_drifts(self) -> None:
        """An empty list is a real observation, distinct from an absent key."""
        live = mod.extract_live_ruleset_state({"enforcement": "active", "bypass_actors": []})
        assert live["bypass_actors"] == []
        assert mod.bypass_actors_observable(live) is True
        drifts = mod.check_ruleset_drift(_baseline(), live)
        assert len(drifts) == 1
        assert "bypass_actors" in drifts[0]

    def test_null_is_not_observable(self) -> None:
        live = mod.extract_live_ruleset_state({"enforcement": "active", "bypass_actors": None})
        assert mod.bypass_actors_observable(live) is False
        assert mod.check_ruleset_drift(_baseline(), live) == []


class TestMainBypassActorsStates:
    """CLI-level proof: main() exit code and output for each bypass_actors state."""

    def test_present_match_returns_zero_without_not_observable_note(self, capsys) -> None:
        mock = _gh_response(_matching_params(), bypass_actors=list(_BASELINE_ACTORS))
        with patch("subprocess.run", return_value=mock):
            rc = mod.main([])
        out = capsys.readouterr().out
        assert rc == 0
        assert _NOT_OBSERVABLE not in out
        assert "OK: all recorded ruleset parameters match live values." in out

    def test_present_drift_returns_one(self, capsys) -> None:
        mock = _gh_response(_matching_params(), bypass_actors=[*_BASELINE_ACTORS, _EXTRA_ACTOR])
        with patch("subprocess.run", return_value=mock):
            rc = mod.main([])
        out = capsys.readouterr().out
        assert rc == 1
        assert "DRIFT DETECTED" in out
        assert "bypass_actors" in out
        assert _NOT_OBSERVABLE not in out

    def test_absent_returns_zero_and_logs_distinct_state(self, capsys) -> None:
        """The CI false positive: the GITHUB_TOKEN response has no bypass_actors key."""
        with patch("subprocess.run", return_value=_gh_response(_matching_params())):
            rc = mod.main([])
        out = capsys.readouterr().out
        assert rc == 0
        assert _NOT_OBSERVABLE in out
        assert "bypass_actors not compared" in out
        assert "DRIFT" not in out

    def test_absent_still_fails_on_parameter_drift(self, capsys) -> None:
        live_params = _matching_params()
        live_params["strict_required_status_checks_policy"] = True
        with patch("subprocess.run", return_value=_gh_response(live_params)):
            rc = mod.main([])
        out = capsys.readouterr().out
        assert rc == 1
        assert "strict_required_status_checks_policy" in out
        assert _NOT_OBSERVABLE in out

    def test_absent_still_fails_on_enforcement_drift(self, capsys) -> None:
        mock = _gh_response(_matching_params(), enforcement="evaluate")
        with patch("subprocess.run", return_value=mock):
            rc = mod.main([])
        out = capsys.readouterr().out
        assert rc == 1
        assert "enforcement" in out
