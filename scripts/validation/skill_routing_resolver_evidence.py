"""Resolver-backed reachability evidence for the skill routing-role gate (DESIGN-036).

A report-only layer, added by the DESIGN-036 amendment that landed with
ADR-123: a `front-door` skill invoked by `autoplan` is reachable when
`resolve_route.resolve` routes one of its own `intents` to that skill alone.
This proves the resolver routes those intents and no other skill shadows them.
It does not prove a user words a request that way; the Skill Trigger Phrase
Resolution ratchet (`check_skill_trigger_resolution.py`) checks the phrases a
description advertises.

It reads the rendered catalog at `<repo_root>/src/claude/skills`, the tree the
resolver ships with. When that tree or the resolver is absent (a fixture
repository, or a downstream install), it credits nothing. It cannot change the
gate's exit code.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

CATALOG_DIR = "src/claude/skills"
RESOLVER_PATH = f"{CATALOG_DIR}/autoplan/scripts/resolve_route.py"

_ROUTED_KINDS = frozenset({"specialist", "explicit"})


@dataclass(frozen=True)
class FrontDoor:
    """The facts the two layers need about one front-door skill."""

    name: str
    shipped: bool
    intents: tuple[str, ...]
    description: str


def load_resolver(repo_root: Path) -> tuple[ModuleType, list[object]] | None:
    """Import the shipped resolver and build its catalog root, or None.

    The import executes only `resolve_route.py`, which reads `SKILL.md`
    frontmatter and runs no skill content (REQ-039 "Security").
    """
    script = repo_root / RESOLVER_PATH
    catalog = repo_root / CATALOG_DIR
    if not script.is_file() or not catalog.is_dir():
        return None
    spec = importlib.util.spec_from_file_location("_routing_evidence_resolver", script)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolves annotations through sys.modules, so register first.
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(spec.name, None)
        raise
    roots = module._build_roots([str(catalog)])
    if roots is None:
        return None
    return module, roots


def _routes_to(resolver: tuple[ModuleType, list[object]], request: str, name: str) -> bool:
    """Return True when the resolver routes `request` to `name` and nothing else."""
    module, roots = resolver
    result = module.resolve(request, roots)
    candidates = [str(c).rsplit(":", 1)[-1] for c in result.get("candidates") or []]
    return result.get("kind") in _ROUTED_KINDS and candidates == [name]


def intent_reachable(
    resolver: tuple[ModuleType, list[object]] | None, door: FrontDoor | None
) -> bool:
    """Return True when one of the skill's own intents resolves to it alone."""
    if resolver is None or door is None:
        return False
    return any(_routes_to(resolver, intent, door.name) for intent in door.intents)
