"""Tests for eval harness provider plumbing, provenance, and API key fixes.

Covers issues:
- #3924: eval entry points must use load_api_key_for_selected_provider
- #3935: rule scenario files for code-quality and pragmatic-programmer exist
- #3956: eval-rule-activation output includes run provenance
- #4002: build_plan does not raise for quota-billed providers
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = REPO_ROOT / "scripts" / "eval"
RULE_SCENARIOS_DIR = REPO_ROOT / "tests" / "evals" / "rule-scenarios"

_path_added = str(EVAL_DIR) not in sys.path
if _path_added:
    sys.path.insert(0, str(EVAL_DIR))
try:
    import _eval_agent_types as types_mod
    import _eval_common as eval_common_mod
    import _plan_runner as plan_mod
finally:
    if _path_added and str(EVAL_DIR) in sys.path:
        sys.path.remove(str(EVAL_DIR))


def _make_fixture() -> types_mod.Fixture:
    return types_mod.Fixture(
        id="F001",
        input="test input",
        provenance="hand-written",
        assertions=[],
    )


# ---------------------------------------------------------------------------
# Issue #4002: cost_basis and build_plan with non-Anthropic providers
# ---------------------------------------------------------------------------


class TestCostBasis:
    """cost_basis resolves provider correctly so plan and transport agree."""

    def test_anthropic_returns_usd(self):
        assert eval_common_mod.cost_basis("anthropic") == "usd"

    def test_none_defaults_to_usd(self):
        # No provider set: defaults to Anthropic path.
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("EVAL_PROVIDER", None)
            assert eval_common_mod.cost_basis(None) == "usd"

    def test_github_models_returns_requests(self):
        assert eval_common_mod.cost_basis("github-models") == "requests"

    def test_github_short_name_returns_requests(self):
        assert eval_common_mod.cost_basis("github") == "requests"

    def test_copilot_returns_requests(self):
        assert eval_common_mod.cost_basis("copilot") == "requests"

    def test_copilot_cli_returns_requests(self):
        assert eval_common_mod.cost_basis("copilot-cli") == "requests"

    def test_unknown_provider_defaults_to_usd(self):
        # Unknown transport is not evidence of a free one.
        assert eval_common_mod.cost_basis("some-future-vendor") == "usd"

    def test_env_var_sets_basis_when_no_arg(self, monkeypatch):
        monkeypatch.setenv("EVAL_PROVIDER", "github-models")
        assert eval_common_mod.cost_basis(None) == "requests"

    def test_explicit_arg_wins_over_env(self, monkeypatch):
        monkeypatch.setenv("EVAL_PROVIDER", "github-models")
        assert eval_common_mod.cost_basis("anthropic") == "usd"

    def test_case_insensitive(self):
        assert eval_common_mod.cost_basis("GitHub-Models") == "requests"
        assert eval_common_mod.cost_basis("  github-models  ") == "requests"


class TestBuildPlanWithQuotaProvider:
    """build_plan does not raise for quota-billed providers (fix for #4002)."""

    def test_github_models_skips_usd_cost(self):
        plan = plan_mod.PlanRunner.build_plan(
            fixtures=[_make_fixture()],
            model_id="openai/gpt-4o-mini",
            n_runs=1,
            provider="github-models",
        )
        assert plan.estimated_cost_usd is None
        assert plan.cost_basis == "requests"

    def test_copilot_cli_skips_usd_cost(self):
        plan = plan_mod.PlanRunner.build_plan(
            fixtures=[_make_fixture()],
            model_id="gpt-5.6-sol",
            n_runs=1,
            provider="copilot-cli",
        )
        assert plan.estimated_cost_usd is None
        assert plan.cost_basis == "requests"

    def test_anthropic_provider_still_computes_usd(self):
        plan = plan_mod.PlanRunner.build_plan(
            fixtures=[_make_fixture()],
            model_id="claude-sonnet-4-6",
            n_runs=1,
            provider="anthropic",
        )
        assert plan.estimated_cost_usd is not None
        assert plan.estimated_cost_usd > 0
        assert plan.cost_basis == "usd"

    def test_default_provider_still_raises_on_unpriced_model(self):
        # An unpriced model on the Anthropic (per-token) path must still raise.
        with pytest.raises(plan_mod.UnsupportedModelError):
            plan_mod.PlanRunner.build_plan(
                fixtures=[_make_fixture()],
                model_id="openai/gpt-4o-mini",
                n_runs=1,
                provider="anthropic",
            )

    def test_format_plan_lines_quota_path(self):
        plan = plan_mod.PlanRunner.build_plan(
            fixtures=[_make_fixture()],
            model_id="openai/gpt-4o-mini",
            n_runs=2,
            provider="github-models",
        )
        lines = plan_mod.PlanRunner.format_plan_lines(plan)
        cost_line = [ln for ln in lines if "cost" in ln]
        assert len(cost_line) == 1
        # Must not print a dollar figure for a quota provider.
        assert "cost_estimate_usd" not in cost_line[0]
        assert "cost_estimate_requests=" in cost_line[0]
        assert "basis=quota" in cost_line[0]

    def test_format_plan_lines_usd_path_unchanged(self):
        plan = plan_mod.PlanRunner.build_plan(
            fixtures=[_make_fixture()],
            model_id="claude-sonnet-4-6",
            n_runs=1,
            provider="anthropic",
        )
        lines = plan_mod.PlanRunner.format_plan_lines(plan)
        cost_line = [ln for ln in lines if ln.startswith("cost_estimate_usd=")]
        assert len(cost_line) == 1
        assert "rate_as_of=" in cost_line[0]


# ---------------------------------------------------------------------------
# Issue #3924: eval entry points use load_api_key_for_selected_provider
# ---------------------------------------------------------------------------


class TestApiKeyImport:
    """Verify scripts import the provider-aware key loader (fix for #3924).

    The expected import string is hard-coded here, not read from the source
    file, so a reversion in the source fails this test rather than passing it.
    """

    EXPECTED_IMPORT = "load_api_key_for_selected_provider"
    SCRIPTS = [
        "eval-agents.py",
        "eval-knowledge-integration.py",
        "eval-oneshot-vs-shipped.py",
        "eval-skill-overlap.py",
        "eval-rule-activation.py",
    ]

    @pytest.mark.parametrize("script", SCRIPTS)
    def test_script_imports_provider_aware_key_loader(self, script):
        path = EVAL_DIR / script
        source = path.read_text(encoding="utf-8")
        assert self.EXPECTED_IMPORT in source, (
            f"{script} still imports bare load_api_key; "
            f"expected {self.EXPECTED_IMPORT!r}"
        )

    @pytest.mark.parametrize("script", SCRIPTS)
    def test_script_does_not_import_bare_load_api_key(self, script):
        path = EVAL_DIR / script
        source = path.read_text(encoding="utf-8")
        # Bare import: "load_api_key as _load_api_key" without "for_selected_provider"
        bare = "load_api_key as _load_api_key"
        assert bare not in source, (
            f"{script} still has the bare {bare!r} import"
        )


# ---------------------------------------------------------------------------
# Issue #3935: rule scenario files for code-quality and pragmatic-programmer
# ---------------------------------------------------------------------------


class TestRuleScenarioFiles:
    """Scenario files exist and parse correctly for the two largest always-on rules."""

    @pytest.mark.parametrize("rule_id", ["code-quality", "pragmatic-programmer"])
    def test_scenario_file_exists(self, rule_id):
        path = RULE_SCENARIOS_DIR / f"{rule_id}.json"
        assert path.exists(), f"Missing scenario file: {path}"

    @pytest.mark.parametrize("rule_id", ["code-quality", "pragmatic-programmer"])
    def test_scenario_file_parses_as_json(self, rule_id):
        path = RULE_SCENARIOS_DIR / f"{rule_id}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data, dict)

    @pytest.mark.parametrize("rule_id", ["code-quality", "pragmatic-programmer"])
    def test_scenario_file_has_required_fields(self, rule_id):
        path = RULE_SCENARIOS_DIR / f"{rule_id}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "rule_id" in data
        assert "rule_path" in data
        assert "scenarios" in data
        assert isinstance(data["scenarios"], list)
        assert len(data["scenarios"]) >= 2, "Need at least 2 scenarios"

    @pytest.mark.parametrize("rule_id", ["code-quality", "pragmatic-programmer"])
    def test_scenarios_have_positive_and_negative(self, rule_id):
        path = RULE_SCENARIOS_DIR / f"{rule_id}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        has_positive = any(
            s.get("expected_signals") for s in data["scenarios"]
        )
        has_negative = any(
            not s.get("expected_signals") for s in data["scenarios"]
        )
        assert has_positive, f"{rule_id}: no positive scenario"
        assert has_negative, f"{rule_id}: no negative scenario"

    @pytest.mark.parametrize("rule_id", ["code-quality", "pragmatic-programmer"])
    def test_rule_path_points_to_existing_file(self, rule_id):
        path = RULE_SCENARIOS_DIR / f"{rule_id}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        rule_path = REPO_ROOT / data["rule_path"]
        assert rule_path.exists(), f"rule_path {data['rule_path']!r} does not exist"


# ---------------------------------------------------------------------------
# Issue #3956: run provenance in eval-rule-activation output
# ---------------------------------------------------------------------------


def _load_eval_rule_activation():
    spec = importlib.util.spec_from_file_location(
        "eval_rule_activation", EVAL_DIR / "eval-rule-activation.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestRunProvenance:
    """eval-rule-activation emits a run provenance block (fix for #3956)."""

    @pytest.fixture(scope="class")
    def mod(self):
        _path_added = str(EVAL_DIR) not in sys.path
        if _path_added:
            sys.path.insert(0, str(EVAL_DIR))
        try:
            return _load_eval_rule_activation()
        finally:
            if _path_added and str(EVAL_DIR) in sys.path:
                sys.path.remove(str(EVAL_DIR))

    def _make_args(self, mod):
        """Build a minimal argparse.Namespace for _build_run_provenance."""
        import argparse

        return argparse.Namespace(
            scenarios=[],
            model="claude-sonnet-4-6",
        )

    def test_build_run_provenance_returns_dict(self, mod):
        prov = mod._build_run_provenance(self._make_args(mod))
        assert isinstance(prov, dict)

    def test_provenance_has_timestamp(self, mod):
        prov = mod._build_run_provenance(self._make_args(mod))
        assert "timestamp_utc" in prov
        assert prov["timestamp_utc"] is not None
        ts = prov["timestamp_utc"]
        assert isinstance(ts, str)
        assert "T" in ts

    def test_provenance_has_git_commit_key(self, mod):
        prov = mod._build_run_provenance(self._make_args(mod))
        # git_commit is present; may be empty string in a detached env.
        assert "git_commit" in prov

    def test_provenance_has_provider_key(self, mod):
        prov = mod._build_run_provenance(self._make_args(mod))
        assert "provider" in prov
        assert isinstance(prov["provider"], str)

    def test_provenance_git_commit_is_str(self, mod):
        prov = mod._build_run_provenance(self._make_args(mod))
        assert isinstance(prov["git_commit"], str)

    def test_provenance_survives_git_unavailable(self, mod):
        # Simulate git not on PATH; provenance must still return a dict
        # with timestamp populated and git_commit as empty string.
        with patch("subprocess.run", side_effect=FileNotFoundError):
            prov = mod._build_run_provenance(self._make_args(mod))
        assert isinstance(prov, dict)
        assert prov["git_commit"] == ""
        assert prov["timestamp_utc"] is not None

    def test_provenance_injected_into_all_results(self):
        """all_results dict must include the 'run' key from _build_run_provenance.

        This is a source-code assertion: the injection must be present in the
        main() function of eval-rule-activation.py. The authority is the
        hard-coded expected string, not the production source read at runtime.
        """
        source = (EVAL_DIR / "eval-rule-activation.py").read_text(encoding="utf-8")
        assert '"run": _build_run_provenance(' in source, (
            "eval-rule-activation.py does not inject provenance into all_results; "
            "the 'run' key must appear in the all_results dict literal"
        )
