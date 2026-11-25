"""Shared constants and helpers for the CLI smoke workflow tests.

Imported by the ``tests/test_cli_smoke_security*.py`` modules (credential scope,
matrix, and gate wiring) and the ``tests/test_cli_smoke_trust*.py`` modules
(triggers, trust gate, fork denial, and trusted scripts), which test
``plugin-cli-smoke.yml``. Fixtures live in ``tests/lib/cli_smoke_fixtures.py``.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "plugin-cli-smoke.yml"
RENOVATE_CONFIG = REPO_ROOT / "renovate.json"
# No smoke job reads a model credential: the Claude and Copilot prompt legs were
# deleted with their agent-* environments. These names stay so a test can prove
# no step reads one again.
SECRET_NAMES = {"CLAUDE_CODE_OAUTH_TOKEN", "COPILOT_GITHUB_TOKEN"}
EVERY_MODEL_SECRET = SECRET_NAMES | {"ANTHROPIC_API_KEY", "OPENAI_API_KEY", "FACTORY_API_KEY"}
# Each CLI installs from its own committed package.json and package-lock.json
# (`npm ci`), so Renovate maintains the pin natively and npm checks integrity.
CLI_SMOKE_DIR = REPO_ROOT / ".github" / "cli-smoke"
PACKAGE_DIR = {
    "@anthropic-ai/claude-code": "claude",
    "@github/copilot": "copilot",
    "@openai/codex": "codex",
    "@earendil-works/pi-coding-agent": "pi",
}
# Packages a workflow step installs. Copilot keeps a manifest and lockfile, but no
# step installs it since the Copilot smoke leg was deleted.
INSTALLED_PACKAGES = tuple(p for p in PACKAGE_DIR if p != "@github/copilot")
# job id -> (package, install step name) for every job that installs a CLI.
INSTALL_JOBS = {
    "smoke-codex": ("@openai/codex", "Install pinned Codex CLI"),
    "smoke-claude-hooks": ("@anthropic-ai/claude-code", "Install pinned Claude CLI"),
    "smoke-pi": ("@earendil-works/pi-coding-agent", "Install pinned Pi CLI"),
}
OPERATING_SYSTEMS = ["ubuntu-latest", "macos-latest", "windows-latest"]
SMOKE_FILES = {
    "hook": "tests/e2e/test_cli_hook_e2e.py",
    "plugin": "tests/e2e/test_plugin_load_smoke.py",
    "hook-discovery": "tests/e2e/test_claude_hook_discovery_smoke.py",
}
BASE_CHECKOUT_PATH = "trusted-base"
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def load_workflow() -> dict[Any, Any]:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def load_renovate_config() -> dict[str, Any]:
    return yaml.safe_load(RENOVATE_CONFIG.read_text(encoding="utf-8"))


def _step_by_name(job: dict[str, Any], name: str) -> dict[str, Any]:
    return next(step for step in job["steps"] if step.get("name") == name)


def _collected_count(test_file: str, cli: str) -> int:
    """Count the tests ``-m "smoke and <cli>"`` selects, with RUN_CLI_E2E unset."""
    env = {k: v for k, v in os.environ.items() if k != "RUN_CLI_E2E"}
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            test_file,
            "-m",
            f"smoke and {cli}",
            "--collect-only",
            "-q",
            "-o",
            "addopts=",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    # Exit 5 means "no tests collected", which is a valid count of zero.
    assert result.returncode in (0, 5), result.stdout + result.stderr
    return sum(1 for line in result.stdout.splitlines() if "::" in line)


def _expected_count(step: dict[str, Any]) -> int:
    arguments = shlex.split(step["run"])
    assert arguments.count("--expected-count") == 1
    return int(arguments[arguments.index("--expected-count") + 1])


def _run_commands(step: dict[str, Any]) -> list[list[str]]:
    """Split a step's ``run`` into one argv list per command (continuations joined)."""
    joined = step["run"].replace("\\\n", " ")
    return [shlex.split(line) for line in joined.splitlines() if line.strip()]


def _checkouts(job: dict[str, Any]) -> list[dict[str, Any]]:
    return [step for step in job["steps"] if "actions/checkout" in step.get("uses", "")]
