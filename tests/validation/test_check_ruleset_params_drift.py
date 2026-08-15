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


class TestCheckDrift:
    """Unit tests for the drift comparison logic."""

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


class TestMainOffline:
    """Test the --offline flag."""

    def test_offline_skips(self, capsys):
        rc = mod.main(["--offline"])
        assert rc == 0
        assert "SKIP" in capsys.readouterr().out


class TestMainLive:
    """Integration-style tests with mocked subprocess."""

    def _mock_gh(self, params: dict):
        """Return a mock that simulates gh api returning given params."""
        rules = [{"type": "required_status_checks", "parameters": params}]
        payload = json.dumps({"rules": rules})
        return subprocess.CompletedProcess(
            args=[], returncode=0, stdout=payload, stderr=""
        )

    def test_match_returns_zero(self, capsys):
        live_params = {
            "strict_required_status_checks_policy": False,
            "required_review_thread_resolution": True,
            "required_approving_review_count": 0,
        }
        with patch("subprocess.run", return_value=self._mock_gh(live_params)):
            rc = mod.main([])
        assert rc == 0
        assert "OK" in capsys.readouterr().out

    def test_drift_returns_one(self, capsys):
        live_params = {
            "strict_required_status_checks_policy": True,
            "required_review_thread_resolution": True,
            "required_approving_review_count": 0,
        }
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


class TestEdgeCases:
    """Edge cases: malformed baseline, extra live params."""

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

    def test_extra_live_params_reported_as_drift(self) -> None:
        baseline: dict[str, Any] = {
            "parameters": {"strict_required_status_checks_policy": False}
        }
        live: dict[str, Any] = {
            "strict_required_status_checks_policy": False,
            "require_linear_history": True,
        }
        drifts = mod.check_drift(baseline, live)
        assert any("require_linear_history" in d for d in drifts)
