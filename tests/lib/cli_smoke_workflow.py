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
CLIS = ("claude", "copilot")
# Claude legs use the subscription OAuth token (REQ-047 owner decision); the API
# key ran out of credit on 2026-10-07 and must not be read by the smoke.
CLI_SECRET = {"claude": "CLAUDE_CODE_OAUTH_TOKEN", "copilot": "COPILOT_GITHUB_TOKEN"}
SECRET_NAMES = set(CLI_SECRET.values())
EVERY_MODEL_SECRET = SECRET_NAMES | {"ANTHROPIC_API_KEY", "OPENAI_API_KEY", "FACTORY_API_KEY"}
CLI_PACKAGE = {"claude": "@anthropic-ai/claude-code", "copilot": "@github/copilot"}
PACKAGE_VERSION_ENV = {
    "@anthropic-ai/claude-code": "CLAUDE_CODE_VERSION",
    "@github/copilot": "COPILOT_CLI_VERSION",
    "@openai/codex": "CODEX_CLI_VERSION",
}
OPERATING_SYSTEMS = ["ubuntu-latest", "macos-latest", "windows-latest"]
INSTALL_STEP = {"claude": "Install pinned Claude CLI", "copilot": "Install pinned Copilot CLI"}
HOOK_STEP = {
    "claude": "Run real-CLI hook smoke (claude)",
    "copilot": "Run real-CLI hook smoke (copilot)",
}
PLUGIN_STEP = {
    "claude": "Run real-CLI plugin-load smoke (claude)",
    "copilot": "Run real-CLI plugin-load smoke (copilot)",
}
HOOK_GATE = {
    "claude": "Assert the hook smoke actually ran (claude)",
    "copilot": "Assert the hook smoke actually ran (copilot)",
}
PLUGIN_GATE = {
    "claude": "Assert the plugin-load smoke actually ran (claude)",
    "copilot": "Assert the plugin-load smoke actually ran (copilot)",
}
CREDENTIAL_STEPS = set(HOOK_STEP.values()) | set(PLUGIN_STEP.values())
SMOKE_FILES = {
    "hook": "tests/e2e/test_cli_hook_e2e.py",
    "plugin": "tests/e2e/test_plugin_load_smoke.py",
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


def _gate_arguments(step: dict[str, Any]) -> list[str]:
    return shlex.split(step["run"])


def _checkouts(job: dict[str, Any]) -> list[dict[str, Any]]:
    return [step for step in job["steps"] if "actions/checkout" in step.get("uses", "")]
