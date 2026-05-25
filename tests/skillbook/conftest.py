"""Shared fixtures for skillbook tests."""

from __future__ import annotations

import importlib.util
import json
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

_DEFAULT_META = {
    "total_discovered": 0,
    "total_retired": 0,
    "total_merged": 0,
    "last_promotion_at": 0,
    "promotion_count": 0,
}


def make_policy(policy_id: str = "pol-test-policy", **overrides: Any) -> dict[str, Any]:
    """Return a schema-complete policy dict, with field overrides applied."""
    policy: dict[str, Any] = {
        "id": policy_id,
        "owner_agent": "architect",
        "name": "Test policy",
        "description": "A policy used by the skillbook test suite.",
        "tier": "hypothesis",
        "status": "active",
        "confirms": 0,
        "contradicts": 0,
        "application_count": 0,
        "evidence": [],
        "related_policies": [],
        "contradicts_policies": [],
        "supersedes": [],
        "created_at": 1778976000,
        "last_tested_at": 0,
        "version": 1,
    }
    policy.update(overrides)
    return policy


def make_evidence(
    evidence_type: str = "confirmed",
    eval_id: str = "eval-1",
    context_type: str = "external",
    ts: int = 1778976000,
) -> dict[str, Any]:
    """Return a schema-complete evidence entry."""
    return {
        "ts": ts,
        "type": evidence_type,
        "eval_id": eval_id,
        "pass": evidence_type == "confirmed",
        "context_type": context_type,
    }


@pytest.fixture()
def policy_factory() -> Callable[..., dict[str, Any]]:
    """Expose make_policy as a fixture."""
    return make_policy


@pytest.fixture()
def evidence_factory() -> Callable[..., dict[str, Any]]:
    """Expose make_evidence as a fixture."""
    return make_evidence


@pytest.fixture()
def write_skillbook(tmp_path: Path) -> Callable[..., Path]:
    """Return a factory that writes a skillbook directory and returns its path."""

    def _write(
        policies: list[dict[str, Any]] | None = None,
        tensions: list[dict[str, Any]] | None = None,
        workflows: list[dict[str, Any]] | None = None,
        meta: dict[str, Any] | None = None,
    ) -> Path:
        skillbook_dir = tmp_path / ".agents" / "skillbook"
        skillbook_dir.mkdir(parents=True, exist_ok=True)
        (skillbook_dir / "policies.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "policies": policies or [],
                    "meta": meta or dict(_DEFAULT_META),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        (skillbook_dir / "tensions.json").write_text(
            json.dumps({"schema_version": 1, "tensions": tensions or []}, indent=2),
            encoding="utf-8",
        )
        (skillbook_dir / "workflows.json").write_text(
            json.dumps({"schema_version": 1, "workflows": workflows or []}, indent=2),
            encoding="utf-8",
        )
        return skillbook_dir

    return _write


@pytest.fixture(scope="session")
def post_eval_module() -> ModuleType:
    """Load .agents/hooks/post-eval.py as an importable module (hyphenated path)."""
    hook_path = _PROJECT_ROOT / ".agents" / "hooks" / "post-eval.py"
    spec = importlib.util.spec_from_file_location("post_eval_hook", hook_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
