"""Shared pytest fixtures for the CLI smoke workflow tests.

Test modules load these with ``pytest_plugins``. The workflow and Renovate
documents parse once per module.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.lib.cli_smoke_workflow import load_renovate_config, load_workflow


@pytest.fixture(scope="module")
def workflow_doc() -> dict[Any, Any]:
    return load_workflow()


@pytest.fixture(scope="module")
def smoke_job(workflow_doc: dict[Any, Any]) -> dict[str, Any]:
    return workflow_doc["jobs"]["smoke"]


@pytest.fixture(scope="module")
def codex_job(workflow_doc: dict[Any, Any]) -> dict[str, Any]:
    return workflow_doc["jobs"]["smoke-codex"]


@pytest.fixture(scope="module")
def renovate_config() -> dict[str, Any]:
    return load_renovate_config()
