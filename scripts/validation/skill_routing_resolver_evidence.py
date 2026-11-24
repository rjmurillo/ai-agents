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
repository, or a downstream install), it credits nothing. A resolver that is
present but fails to load, or raises while routing an intent, fails the gate
loudly: the error propagates, so a broken resolver is never read as "no
intent reached".
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import yaml  # noqa: E402

from scripts.hook_utilities.frontmatter_block import (  # noqa: E402
    FrontmatterStatus,
    parse_frontmatter,
)

CATALOG_DIR = "src/claude/skills"
RESOLVER_PATH = f"{CATALOG_DIR}/autoplan/scripts/resolve_route.py"

_ROUTED_KINDS = frozenset({"specialist", "explicit"})


@dataclass(frozen=True)
class FrontDoor:
    """The facts the intent layer needs about one front-door skill."""

    name: str
    intents: tuple[str, ...]


def load_resolver(repo_root: Path) -> tuple[ModuleType, list[object]] | None:
    """Import the shipped resolver and build its catalog root.

    Returns None when the resolver script or the catalog is absent. Raises
    when the resolver fails to import or to build its roots.

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


def _mapping(value: object) -> dict[str, object]:
    """Return `value` when it is a mapping, else an empty one."""
    return value if isinstance(value, dict) else {}


def read_front_door(name: str, template: Path) -> FrontDoor | None:
    """Read one skill template's routing intents.

    Returns None when the frontmatter does not parse; the routing gate already
    reports that defect.
    """
    text = template.read_text(encoding="utf-8", errors="replace")
    result = parse_frontmatter(text, yaml, allow_duplicate_keys=True)
    if result.status is FrontmatterStatus.MALFORMED:
        return None
    routing = _mapping(_mapping(_mapping(result.metadata).get("metadata")).get("routing"))
    intents = routing.get("intents")
    if not isinstance(intents, list):
        return FrontDoor(name=name, intents=())
    return FrontDoor(name=name, intents=tuple(i for i in intents if isinstance(i, str)))


def intents_reached(repo_root: Path, templates: Mapping[str, Path]) -> set[str]:
    """Return the skills in `templates` whose own intents resolve to them alone."""
    if not templates:
        return set()
    resolver = load_resolver(repo_root)
    return {
        name
        for name, template in templates.items()
        if intent_reachable(resolver, read_front_door(name, template))
    }
