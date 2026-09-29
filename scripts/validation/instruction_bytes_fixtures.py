"""Per-fixture activated instruction bytes for F1 through F6 (issue #5400).

A fixture is a stable, declared routing scenario: one representative edited path
plus the skill and agent entrypoints the scenario routes to. The entrypoints are
declared here, never inferred from text.

What one fixture loads, on the Claude Code path:

* **Harness context** for the edited path, from ``effective_context_claude.resolve_claude``
  (the #4880 model): root ``CLAUDE.md`` files and their ``@`` imports, nested
  ``CLAUDE.md`` down the edited file's directory chain, and every
  ``.claude/rules`` file whose ``paths`` match the path or that has none. A
  fixture with no edited path resolves against the repository root.
* **Always-on skills**: a skill whose frontmatter ``description`` declares
  unconditional loading, found by ``instruction_budget.load_instruction_files``
  (issue #4871).
* **Entrypoints**: the fixture's skills and agents, as rendered under ``.claude/``.
* **Dependencies**: each entrypoint's ``metadata.capability.depends-on`` names,
  resolved to canonical owners (ADR-110, issue #5396) and followed transitively.

Different than the issue text: a fixture with no edited path loads the same root
context as the always-on measurement. Claude Code's real load also depends on which
files the model reads at run time, which a static fixture cannot know. Nested
``@`` imports are followed to the depth ``resolve_claude`` follows them.

An entrypoint with no capability block counts as itself only and is named in the
fixture's ``findings``. A dependency whose loaded copy is missing raises
``CorpusError``: dropping it would lower the total without a signal.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.metrics.control_plane_baseline import always_loaded
from scripts.validation.effective_context_claude import resolve_claude
from scripts.validation.effective_context_sources import Repo, resolve_base_directory
from scripts.validation.instruction_budget import load_instruction_files
from scripts.validation.instruction_bytes_corpus import CorpusError, read_sized
from scripts.validation.instruction_bytes_graph import Capability, Graph, name_pattern
from scripts.validation.instruction_bytes_graph import load_graph as _load_graph
from scripts.validation.instruction_bytes_types import ActivatedFile

__all__ = [
    "FIXTURES",
    "SOURCES",
    "AlwaysOn",
    "Fixture",
    "FixtureResult",
    "Graph",
    "load_always_on",
    "load_graph",
    "measure_fixture",
]

SOURCES = ("root", "nested", "scoped-rule", "always-on-skill", "entrypoint", "dependency")
_LAYER_SOURCE = {"root": "root", "nested": "nested", "scoped": "scoped-rule"}
_ALWAYS_ON_SKILL_ACTIVATION = "skill-description"


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
class AlwaysOn:
    """Always-loaded context: the report section per harness, and the always-on skill paths."""

    harnesses: dict[str, dict[str, Any]]
    skills: tuple[str, ...]
    findings: tuple[str, ...]


@dataclass(frozen=True)
class FixtureResult:
    fixture: Fixture
    files: tuple[ActivatedFile, ...]
    findings: tuple[str, ...]


def load_graph(repo_root: Path) -> Graph:
    """Read the capability graph once. A tree the gate cannot read fails closed."""
    try:
        return _load_graph(repo_root)
    except ValueError as exc:
        raise CorpusError(str(exc)) from exc


def load_always_on(repo_root: Path) -> AlwaysOn:
    """Return always-loaded context per harness, from the existing counters.

    Workspace files and universal rules come from
    ``control_plane_baseline.always_loaded``. Always-on skills come from
    ``instruction_budget.load_instruction_files`` and join the ``claude_code``
    entry only, because they live under ``.claude/skills``.
    """
    exclusions: list[dict[str, str]] = []
    try:
        loaded: dict[str, dict[str, Any]] = always_loaded(repo_root, exclusions)
        skill_paths = tuple(
            sorted(
                f.name
                for f in load_instruction_files(repo_root)
                if f.activation == _ALWAYS_ON_SKILL_ACTIVATION
            )
        )
    except ValueError as exc:  # UnsupportedApplyToError and MalformedSkillFrontmatterError
        raise CorpusError(f"always-on measurement failed: {exc}") from exc
    claude = loaded["claude_code"]
    sized = [read_sized(repo_root, p) for p in skill_paths if p not in claude["files"]]
    loaded["claude_code"] = {
        "files": sorted([*claude["files"], *(s.path for s in sized)]),
        "bytes": claude["bytes"] + sum(s.size_bytes for s in sized),
        "tokens": claude["tokens"] + sum(s.estimated_tokens for s in sized),
    }
    findings = tuple(f"always-on {e['dimension']}: {e['reason']}" for e in exclusions)
    return AlwaysOn(loaded, skill_paths, findings)


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
        return f".claude/rules/{path.removeprefix('templates/rules/')}"
    return None


def _entrypoints(fixture: Fixture) -> list[tuple[str, str]]:
    entries = [("skill", n) for n in fixture.skills] + [("agent", n) for n in fixture.agents]
    pattern = name_pattern()
    for _, name in entries:
        if pattern.match(name) is None:
            raise CorpusError(f"fixture {fixture.fixture_id}: invalid artifact name `{name}`")
    return entries


def _dependency_closure(
    entry_nodes: list[Capability], graph: Graph, findings: list[str]
) -> list[Capability]:
    """Follow ``depends-on`` transitively to canonical owners, in path order."""
    found: dict[str, Capability] = {}
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


def _entry_nodes(
    entries: list[tuple[str, str]], graph: Graph, findings: list[str]
) -> list[Capability]:
    nodes: list[Capability] = []
    for kind, name in entries:
        node = graph.nodes.get(_canonical_path(kind, name))
        if node is None:
            findings.append(f"{kind} `{name}` has no capability block; counted as itself only")
        else:
            nodes.append(node)
    return nodes


def _harness_context(repo_root: Path, target: str) -> tuple[list[tuple[str, str]], list[str]]:
    """Return ``(source, path)`` pairs Claude Code loads for ``target``, plus import problems."""
    repo = Repo(repo_root, None)
    try:
        base_dir = resolve_base_directory(repo, target)
        loaded, problems = resolve_claude(repo, base_dir, target, include_user=False)
    except ValueError as exc:
        raise CorpusError(f"cannot resolve Claude Code context for `{target}`: {exc}") from exc
    pairs = [(_LAYER_SOURCE[f.layer], f.path) for f in loaded]
    return pairs, [f"@ import {p.kind}: {p.target} in {p.location}" for p in problems]


def measure_fixture(
    repo_root: Path, fixture: Fixture, graph: Graph, always_on: AlwaysOn
) -> FixtureResult:
    """Sum the bytes one fixture loads. Each file counts once, under its first source."""
    findings: list[str] = []
    seen: dict[str, ActivatedFile] = {}

    def add(rel: str, source: str) -> None:
        if rel in seen:
            return
        sized = read_sized(repo_root, rel)
        seen[rel] = ActivatedFile(sized.path, sized.size_bytes, sized.estimated_tokens, source)

    context, problems = _harness_context(repo_root, fixture.edited_path or "")
    findings.extend(problems)
    for source, rel in context:
        add(rel, source)
    for rel in always_on.skills:
        add(rel, "always-on-skill")
    entries = _entrypoints(fixture)
    for kind, name in entries:
        loaded = _loaded_path(kind, name)
        if not (repo_root / loaded).is_file():
            raise CorpusError(f"fixture {fixture.fixture_id}: {kind} `{name}` has no {loaded}")
        add(loaded, "entrypoint")
    for owner in _dependency_closure(_entry_nodes(entries, graph, findings), graph, findings):
        owner_loaded = _loaded_from_canonical(owner.path)
        if owner_loaded is None or not (repo_root / owner_loaded).is_file():
            raise CorpusError(
                f"fixture {fixture.fixture_id}: dependency {owner.path} has no loaded copy"
            )
        add(owner_loaded, "dependency")
    return FixtureResult(fixture, tuple(seen.values()), tuple(findings))
