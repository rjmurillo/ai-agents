"""Per-fixture activated instruction bytes for F1 through F6 (issue #5400).

A fixture is a stable, declared routing scenario: one representative edited path
(decides which path-scoped rules load) plus the skill and agent entrypoints the
scenario routes to. The entrypoints are declared here, never inferred from text.
Their dependencies are read from the ``metadata.capability.depends-on`` block
that ADR-110 (issue #5396) put in each artifact's frontmatter, resolved to
canonical owners with ``check_capability_graph.build_owner_index`` and followed
transitively.

Measured surface: the Claude Code load path. Always-on files come from
``control_plane_baseline.always_loaded()["claude_code"]``, the existing counter.
Activated skills, agents, and rules are the rendered copies under ``.claude/``,
which is what the harness reads. The capability declaration sits in the
canonical template; the projection repeats it (ADR-110 section 3).

Different than canonical: ``.claude/rules`` ``paths`` are matched with the same
Copilot-style glob compiler ``instruction_budget_globs`` uses for the always-on
budget, and ``control_plane_baseline`` already applies that compiler to Claude
rules. Claude Code's own matcher is not modeled here, so a path-scoped rule count
is an estimate of the Claude Code load, not an observation of it.

An entrypoint with no capability block counts as itself only and is named in the
fixture's ``findings``. A ``depends-on`` name with no canonical owner is also a
finding; ``check_capability_graph`` is the gate that refuses it.
"""

from __future__ import annotations

import importlib
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

# Bare-name imports for scripts/validation siblings: see instruction_bytes_corpus
# for why the per-file mypy gate needs one module name per file.
_VALIDATION_DIR = str(Path(__file__).resolve().parent)
if _VALIDATION_DIR not in sys.path:
    sys.path.insert(0, _VALIDATION_DIR)

from check_capability_graph import (  # noqa: E402
    NAME_RE,
    Node,
    _frontmatter,
    build_owner_index,
    collect_nodes,
)
from instruction_budget_globs import _glob_to_regex, _vscode_effective_glob  # noqa: E402

from scripts.validation.instruction_bytes_corpus import CorpusError, read_sized  # noqa: E402
from scripts.validation.instruction_bytes_types import ActivatedFile  # noqa: E402

__all__ = [
    "FIXTURES",
    "Fixture",
    "FixtureResult",
    "Graph",
    "load_always_on",
    "load_graph",
    "measure_fixture",
]

_RULES_DIR = ".claude/rules"


@dataclass(frozen=True)
class Fixture:
    """A declared routing scenario. ``edited_path`` is ``None`` when nothing is edited."""

    fixture_id: str
    name: str
    edited_path: str | None
    skills: tuple[str, ...]
    agents: tuple[str, ...]


FIXTURES: tuple[Fixture, ...] = (
    Fixture(
        "F1",
        "small-code-change",
        "scripts/example.py",
        ("build", "test", "review"),
        ("implementer", "qa"),
    ),
    Fixture(
        "F2",
        "rule-or-skill-change",
        "templates/rules/example.md",
        ("build", "test", "review"),
        ("implementer",),
    ),
    Fixture("F3", "docs-only-change", "docs/example.md", ("doc-accuracy",), ()),
    Fixture("F4", "autoplan", None, ("autoplan",), ("orchestrator",)),
    Fixture("F5", "explicit-specialist", None, ("security-review",), ("security",)),
    Fixture("F6", "code-review", None, ("review",), ("code-reviewer", "analyst")),
)


@dataclass(frozen=True)
class Graph:
    """The capability graph one measurement reads: nodes by path, owners by name."""

    nodes: dict[str, Node]
    owners: dict[str, Node]
    defects: tuple[str, ...]


@dataclass(frozen=True)
class FixtureResult:
    fixture: Fixture
    files: tuple[ActivatedFile, ...]
    findings: tuple[str, ...]


def load_always_on(repo_root: Path) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Return the existing always-loaded measurement per harness, plus its exclusions."""
    # control_plane_baseline imports the globs module under its package name, so a
    # static import here would put one file under two names in the per-file mypy run.
    baseline = importlib.import_module("scripts.metrics.control_plane_baseline")
    exclusions: list[dict[str, str]] = []
    try:
        loaded: dict[str, dict[str, Any]] = baseline.always_loaded(repo_root, exclusions)
    except ValueError as exc:  # UnsupportedApplyToError subclasses ValueError
        raise CorpusError(f"always-on measurement failed: {exc}") from exc
    return loaded, [f"always-on {e['dimension']}: {e['reason']}" for e in exclusions]


def load_graph(repo_root: Path) -> Graph:
    """Read the capability graph once. A tree the gate cannot read fails closed."""
    try:
        nodes, defects = collect_nodes(repo_root)
    except Exception as exc:  # TreeError lives in a module loaded under a second name.
        raise CorpusError(f"capability graph unreadable: {exc}") from exc
    owners, owner_findings = build_owner_index(nodes)
    return Graph({n.path: n for n in nodes}, owners, tuple(sorted(defects + owner_findings)))


def _canonical_path(kind: str, name: str) -> str:
    return {
        "skill": f"templates/skills/{name}.SKILL.md.tmpl",
        "agent": f"templates/agents/{name}.shared.md",
    }[kind]


def _loaded_path(kind: str, name: str) -> str:
    return {
        "skill": f".claude/skills/{name}/SKILL.md",
        "agent": f".claude/agents/{name}.md",
    }[kind]


def _loaded_from_canonical(path: str) -> str | None:
    """Map an owner's canonical template path to the copy the harness loads."""
    if path.startswith("templates/skills/") and path.endswith(".SKILL.md.tmpl"):
        name = path.removeprefix("templates/skills/").removesuffix(".SKILL.md.tmpl")
        return _loaded_path("skill", name)
    if path.startswith("templates/agents/") and path.endswith(".shared.md"):
        name = path.removeprefix("templates/agents/").removesuffix(".shared.md")
        return _loaded_path("agent", name)
    if path.startswith("templates/rules/"):
        return f"{_RULES_DIR}/{path.removeprefix('templates/rules/')}"
    return None


def _rule_globs(text: str, rel: str) -> list[str]:
    try:
        front = _frontmatter(text)
    except (ValueError, yaml.YAMLError) as exc:
        raise CorpusError(f"{rel}: frontmatter cannot be parsed: {exc}") from exc
    raw = front.get("paths")
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return [p for p in raw if isinstance(p, str)]
    return []


def _path_scoped_rules(repo_root: Path, edited_path: str | None, skip: set[str]) -> list[str]:
    """Return ``.claude/rules`` files whose ``paths`` match ``edited_path``."""
    rules_dir = repo_root / _RULES_DIR
    if edited_path is None or not rules_dir.is_dir():
        return []
    probe = f"/{edited_path}"
    matched: list[str] = []
    for path in sorted(rules_dir.glob("*.md")):
        rel = path.relative_to(repo_root).as_posix()
        if rel in skip:
            continue
        globs = _rule_globs(path.read_text(encoding="utf-8", errors="replace"), rel)
        if any(regex.match(probe) for regex in _compile_globs(globs, rel)):
            matched.append(rel)
    return matched


def _compile_globs(globs: list[str], rel: str) -> list[re.Pattern[str]]:
    """Compile a rule's ``paths`` globs. An unsupported glob fails closed."""
    try:
        return [_glob_to_regex(_vscode_effective_glob(g)) for g in globs]
    except ValueError as exc:  # UnsupportedApplyToError subclasses ValueError
        raise CorpusError(f"{rel}: {exc}") from exc


def _entrypoints(fixture: Fixture) -> list[tuple[str, str]]:
    entries = [("skill", n) for n in fixture.skills] + [("agent", n) for n in fixture.agents]
    for _, name in entries:
        if NAME_RE.match(name) is None:
            raise CorpusError(f"fixture {fixture.fixture_id}: invalid artifact name `{name}`")
    return entries


def _dependency_closure(entry_nodes: list[Node], graph: Graph, findings: list[str]) -> list[Node]:
    """Follow ``depends-on`` transitively to canonical owners, in path order."""
    found: dict[str, Node] = {}
    pending = [(node.path, dep) for node in entry_nodes for dep in node.depends_on]
    while pending:
        origin, dep = pending.pop()
        owner = graph.owners.get(dep)
        if owner is None:
            findings.append(f"{origin}: depends-on `{dep}` has no canonical owner")
            continue
        if owner.path in found:
            continue
        found[owner.path] = owner
        pending.extend((owner.path, d) for d in owner.depends_on)
    return [found[p] for p in sorted(found)]


def _entry_nodes(entries: list[tuple[str, str]], graph: Graph, findings: list[str]) -> list[Node]:
    nodes: list[Node] = []
    for kind, name in entries:
        node = graph.nodes.get(_canonical_path(kind, name))
        if node is None:
            findings.append(f"{kind} `{name}` has no capability block; counted as itself only")
        else:
            nodes.append(node)
    return nodes


def measure_fixture(
    repo_root: Path, fixture: Fixture, graph: Graph, always_on: list[str]
) -> FixtureResult:
    """Sum the bytes one fixture loads: always-on, path-scoped rules, entrypoints, dependencies.

    ``always_on`` is the Claude Code always-loaded file list, computed once by the
    caller so six fixtures do not re-read the same files.
    """
    findings: list[str] = []
    seen: dict[str, ActivatedFile] = {}

    def add(rel: str, source: str) -> None:
        if rel in seen:
            return
        sized = read_sized(repo_root, rel)
        seen[rel] = ActivatedFile(sized.path, sized.size_bytes, sized.estimated_tokens, source)

    for rel in always_on:
        add(rel, "always-on")
    for rel in _path_scoped_rules(repo_root, fixture.edited_path, set(seen)):
        add(rel, "path-scoped-rule")
    entries = _entrypoints(fixture)
    for kind, name in entries:
        loaded = _loaded_path(kind, name)
        if not (repo_root / loaded).is_file():
            raise CorpusError(f"fixture {fixture.fixture_id}: {kind} `{name}` has no {loaded}")
        add(loaded, "entrypoint")
    for owner in _dependency_closure(_entry_nodes(entries, graph, findings), graph, findings):
        owner_loaded = _loaded_from_canonical(owner.path)
        if owner_loaded is None or not (repo_root / owner_loaded).is_file():
            findings.append(f"{owner.path}: no loaded copy to measure")
            continue
        add(owner_loaded, "dependency")
    return FixtureResult(fixture, tuple(seen.values()), tuple(findings))
