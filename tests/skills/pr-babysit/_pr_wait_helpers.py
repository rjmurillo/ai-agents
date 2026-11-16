"""Shared loader and payload builders for the pr_wait.py tests."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

_SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "claude"
    / "skills"
    / "pr-babysit"
    / "scripts"
    / "pr_wait.py"
)


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("pr_wait", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["pr_wait"] = module
    spec.loader.exec_module(module)
    return module


pw = _load()


def node(node_id: str, login: str, **extra: Any) -> dict[str, Any]:
    return {"id": node_id, "url": f"https://x/{node_id}", "author": {"login": login}, **extra}


def pr_payload(**overrides: Any) -> dict[str, Any]:
    pr: dict[str, Any] = {
        "state": "OPEN",
        "headRefOid": "a" * 40,
        "baseRefName": "main",
        "baseRefOid": "b" * 40,
        "mergeStateStatus": "BLOCKED",
        "author": {"login": "me"},
        "comments": {"totalCount": 0, "nodes": []},
        "reviews": {"totalCount": 0, "nodes": []},
        "reviewThreads": {"totalCount": 0, "nodes": []},
    }
    pr.update(overrides)
    return pr


def gate_payload(**overrides: Any) -> dict[str, Any]:
    gate: dict[str, Any] = {
        "FailingRequired": [],
        "PendingRequired": [],
        "MissingRequired": [],
        "IndeterminateRequired": [],
        "UnresolvedThreads": 0,
        "RulesetContextsAvailable": True,
        "OverallState": "SUCCESS",
    }
    gate.update(overrides)
    return gate


# pr_wait imports its state module by name once loaded.
pws = sys.modules["pr_wait_state"]
