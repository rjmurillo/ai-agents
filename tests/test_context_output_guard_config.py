"""Tests for the context-output Lefthook and CI guard wiring."""

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))

from test_lefthook_gate_config import LEFTHOOK_PATH, _iter_all_jobs


class TestContextOutputGuard:
    def test_precommit_checks_the_complete_manifest(self) -> None:
        """AC: pre-commit runs the read-only manifest check without path filters."""
        data = yaml.safe_load(LEFTHOOK_PATH.read_text(encoding="utf-8"))
        job = next(
            job
            for job in _iter_all_jobs(data["pre-commit"])
            if job.get("name") == "context-output-check"
        )

        assert "--check --staged --manifest .project-toolkit/context-output-manifest.json" in job["run"]
        assert "glob" not in job
        assert job["timeout"] == "5s"
        assert job["env"]["PYTHONDONTWRITEBYTECODE"] == "1"

    def test_premerge_checks_the_complete_manifest(self) -> None:
        """AC: merge commits cannot bypass the staged manifest check."""
        data = yaml.safe_load(LEFTHOOK_PATH.read_text(encoding="utf-8"))
        job = next(
            job
            for job in _iter_all_jobs(data["pre-merge-commit"])
            if job.get("name") == "context-output-check"
        )

        assert "--check --staged --manifest .project-toolkit/context-output-manifest.json" in job["run"]
        assert job["timeout"] == "5s"

    def test_ci_guard_is_unfiltered_and_reaches_required_aggregators(self) -> None:
        """AC: CI checks the complete manifest even when path filters skip tests."""
        workflow_path = LEFTHOOK_PATH.parent / ".github" / "workflows" / "pytest.yml"
        data = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
        guard = data["jobs"]["context-output-guard"]

        assert "needs" not in guard
        assert "if" not in guard
        assert (
            "--check --manifest .project-toolkit/context-output-manifest.json" in (guard["steps"][-1]["run"])
        )
        for aggregator in ("test-result", "skip-tests", "main-failure-alert"):
            assert "context-output-guard" in data["jobs"][aggregator]["needs"]
