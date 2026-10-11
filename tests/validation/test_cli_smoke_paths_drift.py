"""Drift guards for the CLI smoke path list (REQ-047 AC10).

lefthook.yml keeps a copy of each glob tuple, and the workflow runs repo scripts
that must themselves match the smoke globs.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from scripts.validation import cli_smoke_paths as paths

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _find_named_jobs(node: object, job_name: str) -> list[dict]:
    """Collect every mapping named ``job_name`` anywhere in the lefthook tree."""
    found: list[dict] = []
    if isinstance(node, dict):
        if node.get("name") == job_name:
            found.append(node)
        for value in node.values():
            found.extend(_find_named_jobs(value, job_name))
    elif isinstance(node, list):
        for item in node:
            found.extend(_find_named_jobs(item, job_name))
    return found


def _lefthook_globs(job_name: str) -> tuple[str, ...]:
    config = yaml.safe_load((_REPO_ROOT / "lefthook.yml").read_text(encoding="utf-8"))
    jobs = _find_named_jobs(config, job_name)
    assert len(jobs) == 1, f"expected one lefthook job named {job_name}, found {len(jobs)}"
    return tuple(jobs[0]["glob"])


def test_lefthook_hook_globs_equal_the_module_tuple() -> None:
    assert _lefthook_globs("hook-anchoring-e2e") == paths.HOOK_E2E_GLOBS


def test_lefthook_plugin_globs_equal_the_module_tuple() -> None:
    assert _lefthook_globs("plugin-load-e2e") == paths.PLUGIN_E2E_GLOBS


def test_drift_guard_fails_when_a_glob_is_removed() -> None:
    drifted = paths.PLUGIN_E2E_GLOBS[:-1]
    assert drifted != paths.PLUGIN_E2E_GLOBS
    assert _lefthook_globs("plugin-load-e2e") != drifted


_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "plugin-cli-smoke.yml"


_REPO_PATH_RE = re.compile(r"(?<![\w.-])((?:scripts|tests)/[\w./-]+\.py)")


def _workflow_invoked_repo_paths() -> set[str]:
    doc = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    return {
        match
        for job in doc["jobs"].values()
        for step in job["steps"]
        for match in _REPO_PATH_RE.findall(str(step.get("run", "")))
    }


def test_workflow_invokes_repo_scripts_and_tests() -> None:
    """Guard: the extraction below finds the paths it is meant to check."""
    invoked = _workflow_invoked_repo_paths()

    assert "scripts/validation/assert_smoke_ran.py" in invoked
    assert "tests/e2e/test_plugin_load_smoke.py" in invoked
    assert "tests/integration/test_e2e_install.py" in invoked


def test_every_repo_path_the_workflow_runs_matches_the_smoke_globs() -> None:
    """A change to a script or test the smoke runs must trigger the smoke."""
    unmatched = sorted(p for p in _workflow_invoked_repo_paths() if not paths.matched_paths([p]))

    assert unmatched == []
