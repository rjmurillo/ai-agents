"""Guard .github/dependabot.yml, which keeps Dependabot security updates running.

Issue: Dependabot opened no PRs for pyjwt and urllib3 alerts on uv.lock after
the config file was deleted (#2544). Without it, security updates run on
defaults and the repo cannot tune them. Renovate owns version updates, so the
uv entry caps version PRs at zero and leaves security updates enabled.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / ".github" / "dependabot.yml"
WORKFLOW = ROOT / ".github" / "workflows" / "dependabot-approve-and-auto-merge.yml"


@pytest.fixture(scope="module")
def raw_text() -> str:
    return CONFIG.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def config(raw_text: str) -> dict:
    return yaml.safe_load(raw_text)


@pytest.fixture(scope="module")
def uv_entry(config: dict) -> dict:
    entries = [u for u in config["updates"] if u["package-ecosystem"] == "uv"]
    assert len(entries) == 1
    return entries[0]


def test_config_version_is_2(config: dict) -> None:
    assert config["version"] == 2


def test_uv_entry_covers_every_uv_lock_directory(uv_entry: dict) -> None:
    lock_dirs = {
        "/" + rel if rel != "." else "/"
        for rel in (
            p.parent.relative_to(ROOT).as_posix()
            for p in ROOT.glob("**/uv.lock")
            if ".venv" not in p.parts and "node_modules" not in p.parts
        )
    }
    normalized = {d.rstrip("/") or "/" for d in lock_dirs}
    configured = {d.rstrip("/") or "/" for d in uv_entry["directories"]}
    assert normalized <= configured


def test_version_updates_stay_with_renovate(uv_entry: dict) -> None:
    assert uv_entry["open-pull-requests-limit"] == 0


def test_security_updates_are_grouped(uv_entry: dict) -> None:
    groups = uv_entry["groups"]
    assert any(g["applies-to"] == "security-updates" for g in groups.values())


def test_uv_entry_sets_cooldown_matching_exclude_newer(uv_entry: dict) -> None:
    assert uv_entry["cooldown"]["default-days"] == 7


def test_config_has_no_automerge_key(config: dict) -> None:
    """dependabot.yml has no automerge key; the workflow owns auto-merge."""
    assert "automerge" not in json.dumps(config).lower().replace("-", "").replace("_", "")


def test_security_group_has_no_semver_filter(uv_entry: dict) -> None:
    """Edge: no update-types filter, so semver-major security fixes still open PRs."""
    group = uv_entry["groups"]["uv-security"]
    assert "update-types" not in group
    assert "exclude-patterns" not in group


def test_workflow_enables_auto_merge_for_every_dependabot_pr() -> None:
    wf = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = {s["name"]: s for s in wf["jobs"]["dependabot"]["steps"]}
    step = steps["Enable auto-merge"]
    assert "if" not in step
    assert "gh pr merge --auto --squash" in step["run"]


def test_workflow_does_not_filter_semver_major() -> None:
    assert "semver-major" not in WORKFLOW.read_text(encoding="utf-8")


def test_renovate_job_approves_major_updates() -> None:
    wf = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = {s["name"]: s for s in wf["jobs"]["renovate"]["steps"]}
    assert "if" not in steps["Approve PR"]
    assert "Detect major update" not in steps
