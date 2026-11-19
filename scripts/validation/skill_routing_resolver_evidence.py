"""Resolver-backed evidence for the skill routing-role gate (DESIGN-036).

Two report-only layers, added by the DESIGN-036 amendment that landed with
ADR-123:

- Intent reachability: a `front-door` skill invoked by `autoplan` is
  reachable when `resolve_route.resolve` routes one of its own `intents` to
  that skill alone. This proves the resolver routes those intents and no
  other skill shadows them. It does not prove a user words a request that way.
- Phrase misses: trigger phrases quoted after "Use when you say" in a shipped
  front door's description that the resolver does not route to that skill.

Both read the rendered catalog at `<repo_root>/src/claude/skills`, the tree
the resolver ships with. When that tree or the resolver is absent (a fixture
repository, or a downstream install), both layers report "not measured" and
credit nothing. Neither layer can change the gate's exit code.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

CATALOG_DIR = "src/claude/skills"
RESOLVER_PATH = f"{CATALOG_DIR}/autoplan/scripts/resolve_route.py"

_LEAD = re.compile(r"use when you say", re.IGNORECASE)
_QUOTED = re.compile(r"`([^`]+)`|\"([^\"]+)\"")
_ROUTED_KINDS = frozenset({"specialist", "explicit"})


@dataclass(frozen=True)
class FrontDoor:
    """The facts the two layers need about one front-door skill."""

    name: str
    shipped: bool
    intents: tuple[str, ...]
    description: str


@dataclass(frozen=True)
class PhraseReport:
    """Result of the phrase layer. `measured` is False when no resolver loads."""

    measured: bool
    examined: int
    misses: tuple[tuple[str, str], ...]
    no_lead: tuple[str, ...]
    without_intents: int


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


def trigger_phrases(description: str) -> tuple[str, ...] | None:
    """Return quoted phrases after "Use when you say", or None with no lead-in.

    The clause ends at the first `.` outside a quoted span. Quotes are backticks
    or U+0022.
    """
    text = " ".join(description.split())
    lead = _LEAD.search(text)
    if lead is None:
        return None
    clause: list[str] = []
    quote: str | None = None
    for char in text[lead.end() :]:
        if quote is not None:
            if char == quote:
                quote = None
        elif char in '`"':
            quote = char
        elif char == ".":
            break
        clause.append(char)
    return tuple(a or b for a, b in _QUOTED.findall("".join(clause)))


def phrase_report(
    resolver: tuple[ModuleType, list[object]] | None, doors: list[FrontDoor]
) -> PhraseReport:
    """Run the phrase layer over shipped front doors."""
    shipped = [door for door in doors if door.shipped]
    with_intents = [door for door in shipped if door.intents]
    without = len(shipped) - len(with_intents)
    if resolver is None:
        return PhraseReport(False, 0, (), (), without)
    examined = 0
    misses: list[tuple[str, str]] = []
    no_lead: list[str] = []
    for door in sorted(with_intents, key=lambda d: d.name):
        phrases = trigger_phrases(door.description)
        if phrases is None:
            no_lead.append(door.name)
            continue
        for phrase in phrases:
            examined += 1
            if not _routes_to(resolver, phrase, door.name):
                misses.append((door.name, phrase))
    return PhraseReport(True, examined, tuple(misses), tuple(no_lead), without)
