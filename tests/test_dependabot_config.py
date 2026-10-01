"""Guard .github/dependabot.yml, which keeps Dependabot security updates running.

Issue: Dependabot opened no PRs for pyjwt and urllib3 alerts on uv.lock after
the config file was deleted (#2544). Without it, security updates run on
defaults and the repo cannot tune them. Renovate owns version updates, so the
uv entry caps version PRs at zero and leaves security updates enabled.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / ".github" / "dependabot.yml"


@pytest.fixture(scope="module")
def config() -> dict:
    return yaml.safe_load(CONFIG.read_text())


@pytest.fixture(scope="module")
def uv_entry(config: dict) -> dict:
    entries = [u for u in config["updates"] if u["package-ecosystem"] == "uv"]
    assert len(entries) == 1
    return entries[0]


def test_config_version_is_2(config: dict) -> None:
    assert config["version"] == 2


def test_uv_entry_covers_every_uv_lock_directory(uv_entry: dict) -> None:
    lock_dirs = {
        "/" + p.parent.relative_to(ROOT).as_posix().removeprefix(".")
        for p in ROOT.glob("**/uv.lock")
        if ".venv" not in p.parts and "node_modules" not in p.parts
    }
    normalized = {d.rstrip("/") or "/" for d in lock_dirs}
    configured = {d.rstrip("/") or "/" for d in uv_entry["directories"]}
    assert normalized <= configured


def test_version_updates_stay_with_renovate(uv_entry: dict) -> None:
    assert uv_entry["open-pull-requests-limit"] == 0


def test_security_updates_are_grouped(uv_entry: dict) -> None:
    groups = uv_entry["groups"]
    assert any(g["applies-to"] == "security-updates" for g in groups.values())


def test_config_does_not_set_automerge(config: dict) -> None:
    assert "automerge" not in CONFIG.read_text().lower()
    assert all("auto-merge" not in u for u in config["updates"])
