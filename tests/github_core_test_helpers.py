"""Shared values and subprocess fixtures for GitHub Core cases."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    """Build a CompletedProcess for mocking."""
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


def _mock_run(stdout: str = "", stderr: str = "", rc: int = 0):
    """Return a side_effect function that always returns a fixed CompletedProcess."""

    def _side_effect(*args, **kwargs):
        return _completed(stdout=stdout, stderr=stderr, rc=rc)

    return _side_effect


def _thread(tid: str, resolved: bool, db_id: int) -> dict:
    """Build a minimal review thread dict for GraphQL response mocking."""
    return {
        "id": tid,
        "isResolved": resolved,
        "comments": {"nodes": [{"databaseId": db_id}]},
    }


_RATE_LIMIT_RESOURCES = {
    "core": (5000, 5000),
    "search": (30, 30),
    "code_search": (10, 10),
    "graphql": (5000, 5000),
}


def _rate_limit_response(resources: dict[str, tuple[int, int]]) -> str:
    return json.dumps(
        {
            "resources": {
                name: {"remaining": remaining, "limit": limit, "reset": 1234567890}
                for name, (remaining, limit) in resources.items()
            }
        }
    )


RATE_LIMIT_ALL_OK = _rate_limit_response(_RATE_LIMIT_RESOURCES)
RATE_LIMIT_CORE_LOW = _rate_limit_response({**_RATE_LIMIT_RESOURCES, "core": (50, 5000)})
RATE_LIMIT_MISSING_RESOURCE = _rate_limit_response(
    {name: limits for name, limits in _RATE_LIMIT_RESOURCES.items() if name != "code_search"}
)
