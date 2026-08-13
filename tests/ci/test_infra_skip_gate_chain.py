"""End-to-end fail-closed chain for an infrastructure skip (issue #4778).

The unit suites prove each link. This proves the chain, because that is the
acceptance criterion the issue actually states:

    An infrastructure skip still produces explicit review artifacts so Aggregate
    Results can post a report and fail closed without a missing-artifact crash.

Three links, run in the order the workflow runs them:

1. ``scripts/ci/agent_review_save_results.py`` writes an artifact per agent.
2. ``scripts/quality_gate/validate_artifact_download.py`` finds them all.
3. ``.github/scripts/aggregate_quality_verdicts.py`` produces a final verdict
   that ``scripts/quality_gate/check_critical_failures.py`` treats as blocking.

Before this fix, link 1 wrote nothing when the preflight blocked reviews, so
link 2 exited 1 and the run died before any report could be posted.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.ci.agent_review_save_results import run as save_results  # noqa: E402
from scripts.quality_gate.check_critical_failures import (  # noqa: E402
    main as check_critical_failures,
)
from scripts.quality_gate.validate_artifact_download import find_missing  # noqa: E402

sys.path.insert(0, str(REPO_ROOT / ".github" / "scripts"))
from quality_gate_agents import QUALITY_GATE_AGENTS, agent_env_name  # noqa: E402


def _import_aggregate():
    path = REPO_ROOT / ".github" / "scripts" / "aggregate_quality_verdicts.py"
    spec = importlib.util.spec_from_file_location("aggregate_quality_verdicts", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["aggregate_quality_verdicts"] = module
    spec.loader.exec_module(module)
    return module


_aggregate = _import_aggregate()


def _save_all(tmp_path: Path, *, infra_ready: str | None) -> Path:
    """Run the save step once per agent and collect the artifacts in one dir."""
    results = tmp_path / "ai-review-results-merged"
    results.mkdir()
    for agent in QUALITY_GATE_AGENTS:
        work = tmp_path / f"work-{agent}"
        work.mkdir()
        env = {
            "AGENT": agent,
            "VERDICT": "",
            "FINDINGS": "",
            "INFRASTRUCTURE_FAILURE": "",
            "RETRY_COUNT": "0",
            "CACHE_HIT": "false",
        }
        if infra_ready is not None:
            env["INFRA_READY"] = infra_ready
        original_cwd = os.getcwd()
        os.chdir(work)
        try:
            with patch.dict(os.environ, env):
                assert save_results() == 0
        finally:
            os.chdir(original_cwd)
        for produced in (work / "ai-review-results").iterdir():
            (results / produced.name).write_text(
                produced.read_text(encoding="utf-8"), encoding="utf-8"
            )
    return results


def _read_outputs(path: Path) -> dict[str, str]:
    outputs: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            outputs[key] = value
    return outputs


def _aggregate_from(results: Path, tmp_path: Path, monkeypatch) -> dict[str, str]:
    output_file = tmp_path / "aggregate-output"
    output_file.touch()
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
    argv: list[str] = []
    for agent in QUALITY_GATE_AGENTS:
        verdict = (results / f"{agent}-verdict.txt").read_text(encoding="utf-8")
        infra = (results / f"{agent}-infrastructure-failure.txt").read_text(encoding="utf-8")
        argv.extend([f"--{agent}-verdict", verdict, f"--{agent}-infra", infra])
    assert _aggregate.main(argv) == 0
    return _read_outputs(output_file)


class TestInfrastructureSkipFailsClosed:
    """The preflight blocked reviews; the merge must be blocked, not crashed."""

    @pytest.fixture
    def outputs(self, tmp_path: Path, monkeypatch) -> dict[str, str]:
        results = _save_all(tmp_path, infra_ready="false")
        assert find_missing(results) == []
        return _aggregate_from(results, tmp_path, monkeypatch)

    def test_no_verdict_artifact_is_missing(self, tmp_path: Path) -> None:
        assert find_missing(_save_all(tmp_path, infra_ready="false")) == []

    def test_every_agent_is_categorized_as_infrastructure(
        self, outputs: dict[str, str]
    ) -> None:
        for agent in QUALITY_GATE_AGENTS:
            assert outputs[f"{agent}_category"] == "INFRASTRUCTURE", agent

    def test_the_security_review_is_reported_as_not_having_run(
        self, outputs: dict[str, str]
    ) -> None:
        assert outputs["security_review_ran"] == "false"

    def test_the_final_verdict_is_did_not_run(self, outputs: dict[str, str]) -> None:
        assert outputs["final_verdict"] == "DID_NOT_RUN"

    def test_the_gate_blocks_the_merge(self, outputs: dict[str, str]) -> None:
        env = {"FINAL_VERDICT": outputs["final_verdict"]}
        for agent in QUALITY_GATE_AGENTS:
            env[f"{agent_env_name(agent)}_VERDICT"] = outputs[f"{agent}_verdict"]
        with patch.dict(os.environ, env):
            assert check_critical_failures([]) == 1

    def test_a_missing_preflight_output_fails_closed_identically(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """The infra job failed or was skipped, so it published nothing."""
        results = _save_all(tmp_path, infra_ready=None)
        assert find_missing(results) == []
        outputs = _aggregate_from(results, tmp_path, monkeypatch)
        assert outputs["final_verdict"] == "DID_NOT_RUN"
