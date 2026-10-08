"""Trusted-script and checkout-hygiene tests for the CLI smoke workflow.

Trusted gate scripts run only from the base checkout, in isolated mode, and
import only the standard library.
"""

from __future__ import annotations

import ast
import re
import sys
from typing import Any

import pytest

from tests.lib.cli_smoke_workflow import (
    BASE_CHECKOUT_PATH,
    REPO_ROOT,
    _checkouts,
)

pytest_plugins = ["tests.lib.cli_smoke_fixtures"]


TRUSTED_SCRIPTS = (
    "assert_trusted_smoke_context.py",
    "require_job_results.py",
    "assert_smoke_ran.py",
)


def _run_lines(workflow_doc: dict[Any, Any]) -> list[tuple[str, str]]:
    return [
        (job_name, line)
        for job_name, job in workflow_doc["jobs"].items()
        for step in job["steps"]
        for line in str(step.get("run", "")).splitlines()
    ]


@pytest.mark.parametrize("script", TRUSTED_SCRIPTS)
def test_trusted_scripts_run_only_from_the_base_checkout_in_isolated_mode(
    workflow_doc: dict[Any, Any], script: str
) -> None:
    """P1: a pull request cannot edit the gate that judges it."""
    invocations = [(job, line) for job, line in _run_lines(workflow_doc) if script in line]

    assert invocations, script
    for job, line in invocations:
        match = re.search(r"(?:^|[\s(])python3? -I (\S+)", line)
        assert match is not None, (job, line)
        assert match.group(1).startswith(f"{BASE_CHECKOUT_PATH}/"), (job, line)
        assert "uv run" not in line, (job, line)


@pytest.mark.parametrize("script", TRUSTED_SCRIPTS)
def test_every_job_that_runs_a_trusted_script_checks_it_out_from_the_base(
    workflow_doc: dict[Any, Any], script: str
) -> None:
    for job_name, job in workflow_doc["jobs"].items():
        runs_it = any(script in str(step.get("run", "")) for step in job["steps"])
        if not runs_it:
            continue
        bases = [
            c["with"]
            for c in _checkouts(job)
            if c.get("with", {}).get("path") == BASE_CHECKOUT_PATH
        ]
        assert any(
            "github.event.pull_request.base.sha" in b["ref"] and script in b["sparse-checkout"]
            for b in bases
        ), (job_name, script)


def _imported_top_level_modules(tree: ast.AST) -> set[str]:
    """Top-level names of absolute imports in ``tree``; relative imports are skipped."""
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            modules.add(node.module.split(".")[0])
    return modules


@pytest.mark.parametrize("script", TRUSTED_SCRIPTS)
def test_trusted_scripts_import_only_the_standard_library(script: str) -> None:
    """`python -I` runs without the project environment, so third-party imports break."""
    path = next(REPO_ROOT.glob(f"scripts/**/{script}"))
    modules = _imported_top_level_modules(ast.parse(path.read_text(encoding="utf-8")))

    assert modules <= set(sys.stdlib_module_names), modules - set(sys.stdlib_module_names)


def test_every_checkout_drops_persisted_credentials(workflow_doc: dict[Any, Any]) -> None:
    """P2: no later step in a job can reuse the checkout token."""
    checkouts = [c for job in workflow_doc["jobs"].values() for c in _checkouts(job)]

    assert checkouts
    for checkout in checkouts:
        assert checkout.get("with", {}).get("persist-credentials") is False, checkout
