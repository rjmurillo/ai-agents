#!/usr/bin/env python3
"""Find and prune rendered skills and agents whose template was deleted (issue #7224).

Deleting ``templates/skills/<name>.SKILL.md.tmpl`` or the three templates of an
agent used to leave the rendered output behind in every harness tree, and
neither ``build_all.py`` nor ``build_all.py --check`` noticed. This module is the
whole-directory check ``build_all.py`` now runs first, in both modes.

Owners
------

* A skill directory is owned by ``templates/skills/<name>.SKILL.md.tmpl``.
* An agent file is owned by any of ``templates/agents/<stem>.shared.md``,
  ``<stem>.claude.md.tmpl`` or ``<stem>.copilot.md.tmpl``.

An entry with no owner is an orphan unless something already declares it
hand-maintained. The declarations are read at run time, nothing is listed here:

* ``templates/platforms/surface-parity.yaml``: a path owned by an
  ``independent`` surface (``src/vs-code-agents/copilot-instructions.md``).
* ``metadata.distribution: repo-local`` in a skill's own ``SKILL.md`` (the
  hand-maintained repo-only skill that ``skill_distribution`` already supports).
* ``NO-REGEN`` protection (``regen_guard``) on an agent file.
* The file suffix a tree's platform YAML emits: a file that does not end in
  ``outputSuffix`` or ``fileExtension`` is not an agent file at all.

Trees are not listed here either. They come from the platform YAMLs
(``artifacts.skills``, ``artifacts.agents``, ``legacy``) and from the install
trees ``binplace.yaml`` links to those plugin trees.

Pruning and reporting live in ``orphan_prune.py``.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import binplace_manifest  # noqa: E402
import surface_manifest  # noqa: E402
from regen_guard import detect_reason as regen_detect_reason  # noqa: E402
from skill_distribution import SkillDistributionError, is_repo_local  # noqa: E402
from yaml_loader import ConfigError, load_platform_config  # noqa: E402

_SKILL_TEMPLATE_SUFFIX = ".SKILL.md.tmpl"
_SKILL_NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_AGENT_TEMPLATE_SUFFIXES = (".shared.md", ".claude.md.tmpl", ".copilot.md.tmpl")
_SKILL_MD = "SKILL.md"
_DEFAULT_AGENT_SUFFIX = ".md"
_ALWAYS_EXCLUDED = frozenset({"AGENTS.md", "CLAUDE.md"})
_GIT_LOCATION_ENV_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE")

KIND_SKILL = "skill"
KIND_AGENT = "agent"
ROLE_SOURCE = "source"  # holds hand-maintained support files next to the rendered SKILL.md
ROLE_MIRROR = "mirror"  # fully generated copy of src/claude/skills
ROLE_FILE = "file"  # one generated agent file
ROLE_LINK = "link"  # install-tree symlink, swept by binplace_links


class OrphanScanError(Exception):
    """A platform YAML, binplace manifest or surface manifest could not be read. Exit 2."""


@dataclass(frozen=True)
class Tree:
    """One generated tree to scan."""

    path: Path
    kind: str
    role: str
    suffix: str = ""
    excludes: frozenset[str] = _ALWAYS_EXCLUDED


@dataclass(frozen=True)
class Orphan:
    """One entry with no owning template."""

    path: Path
    kind: str
    name: str
    role: str
    template_rels: tuple[str, ...]

    @property
    def is_link(self) -> bool:
        return self.path.is_symlink()


@dataclass
class OrphanScan:
    """Result of :func:`scan`: how many entries were examined and which are orphans."""

    examined: int = 0
    trees: int = 0
    orphans: list[Orphan] = field(default_factory=list)


# --- Discovery -------------------------------------------------------------


def template_names(repo_root: Path) -> tuple[frozenset[str], frozenset[str]]:
    """Return ``(skill names, agent stems)`` that have a template on disk."""
    skills_dir = repo_root / "templates" / "skills"
    skills = frozenset(
        p.name[: -len(_SKILL_TEMPLATE_SUFFIX)]
        for p in skills_dir.glob(f"*{_SKILL_TEMPLATE_SUFFIX}")
        if skills_dir.is_dir()
    )
    agents_dir = repo_root / "templates" / "agents"
    stems: set[str] = set()
    if agents_dir.is_dir():
        for path in agents_dir.iterdir():
            for suffix in _AGENT_TEMPLATE_SUFFIXES:
                if path.is_file() and path.name.endswith(suffix):
                    stems.add(path.name[: -len(suffix)])
    return skills, frozenset(stems)


def _template_rels(kind: str, name: str) -> tuple[str, ...]:
    if kind == KIND_SKILL:
        return (f"templates/skills/{name}{_SKILL_TEMPLATE_SUFFIX}",)
    return tuple(f"templates/agents/{name}{suffix}" for suffix in _AGENT_TEMPLATE_SUFFIXES)


def _platform_configs(repo_root: Path) -> list[dict[str, object]]:
    """Load every platform YAML. ``binplace.yaml`` and the parity manifest carry no provider."""
    platforms = repo_root / "templates" / "platforms"
    configs: list[dict[str, object]] = []
    if not platforms.is_dir():
        return configs
    for path in sorted(platforms.glob("*.yaml")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise OrphanScanError(f"{path}: {exc}") from exc
        if not any(line.startswith(("provider:", "platform:")) for line in text.splitlines()):
            continue
        try:
            configs.append(load_platform_config(path))
        except ConfigError as exc:
            raise OrphanScanError(str(exc)) from exc
    return configs


def _mapping(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _excludes(stanza: dict[str, object]) -> frozenset[str]:
    raw = stanza.get("excludeFilenames")
    names = {n for n in raw if isinstance(n, str)} if isinstance(raw, list) else set()
    return frozenset(names) | _ALWAYS_EXCLUDED


def discover_trees(repo_root: Path) -> list[Tree]:
    """Return every generated skill and agent tree, read from the build's manifests."""
    trees: dict[tuple[Path, str], Tree] = {}

    def add(rel: str | None, kind: str, role: str, suffix: str, excludes: frozenset[str]) -> None:
        if rel is None:
            return
        tree = Tree((repo_root / rel).resolve(), kind, role, suffix, excludes)
        trees.setdefault((tree.path, suffix), tree)

    for config in _platform_configs(repo_root):
        artifacts = _mapping(config.get("artifacts"))
        skills = _mapping(artifacts.get("skills"))
        if skills:
            excludes = _excludes(skills)
            if skills.get("mode") == "hermes-packs":
                out = _text(skills.get("outputDir"))
                for pack_skills in sorted((repo_root / out).glob("*/skills")) if out else ():
                    add(
                        str(pack_skills.relative_to(repo_root)),
                        KIND_SKILL,
                        ROLE_MIRROR,
                        "",
                        excludes,
                    )
            else:
                add(_text(skills.get("sourceDir")), KIND_SKILL, ROLE_SOURCE, "", excludes)
                add(_text(skills.get("outputDir")), KIND_SKILL, ROLE_MIRROR, "", excludes)
        agents = _mapping(artifacts.get("agents"))
        legacy = _mapping(config.get("legacy"))
        if agents:
            excludes = _excludes(agents)
            suffix = _text(agents.get("outputSuffix")) or _DEFAULT_AGENT_SUFFIX
            add(_text(agents.get("outputDir")), KIND_AGENT, ROLE_FILE, suffix, excludes)
            source = _text(agents.get("sourceDir"))
            if source is not None and source.startswith("src/"):
                add(source, KIND_AGENT, ROLE_FILE, _DEFAULT_AGENT_SUFFIX, excludes)
        if legacy:
            suffix = _text(legacy.get("fileExtension")) or _DEFAULT_AGENT_SUFFIX
            add(_text(legacy.get("outputDir")), KIND_AGENT, ROLE_FILE, suffix, _ALWAYS_EXCLUDED)

    plugin = {(t.path, t.kind): t for t in trees.values()}
    try:
        rows = binplace_manifest.load(repo_root)
    except binplace_manifest.BinplaceConfigError as exc:
        raise OrphanScanError(f"binplace manifest: {exc}") from exc
    for row in rows:
        if row.plugin_tree is None or row.install_tree is None:
            continue
        for kind in (KIND_SKILL, KIND_AGENT):
            source_tree = plugin.get((row.plugin_tree.resolve(), kind))
            if source_tree is not None:
                install = row.install_tree.resolve()
                role = ROLE_SOURCE if kind == KIND_SKILL else ROLE_FILE
                trees.setdefault(
                    (install, source_tree.suffix),
                    Tree(install, kind, role, source_tree.suffix, source_tree.excludes),
                )
    return sorted(trees.values(), key=lambda t: (t.kind, str(t.path), t.suffix))


def _independent(manifest: surface_manifest.Manifest | None, rel: str) -> bool:
    if manifest is None:
        return False
    surface, _ = surface_manifest.owner_of(manifest, rel)
    return surface is not None and surface.relation == "independent"


def _declared_repo_local(repo_root: Path, name: str) -> bool:
    try:
        return bool(is_repo_local(repo_root, name))
    except (SkillDistributionError, OSError):
        return False


def scan(repo_root: Path) -> OrphanScan:
    """Walk every generated tree and return the entries that no template owns."""
    repo_root = repo_root.resolve()
    skill_names, agent_stems = template_names(repo_root)
    try:
        manifest = surface_manifest.load_manifest(repo_root)
    except surface_manifest.SurfaceManifestError as exc:
        raise OrphanScanError(f"surface parity manifest: {exc}") from exc
    result = OrphanScan()
    for tree in discover_trees(repo_root):
        if not tree.path.is_dir():
            continue
        result.trees += 1
        for entry in sorted(tree.path.iterdir()):
            found = (
                _skill_orphan(repo_root, manifest, tree, entry, skill_names)
                if tree.kind == KIND_SKILL
                else _agent_orphan(repo_root, manifest, tree, entry, agent_stems)
            )
            if found is None:
                continue
            result.examined += 1
            if isinstance(found, Orphan):
                result.orphans.append(found)
    return result


def _skill_orphan(
    repo_root: Path,
    manifest: surface_manifest.Manifest | None,
    tree: Tree,
    entry: Path,
    names: frozenset[str],
) -> Orphan | bool | None:
    """Return an :class:`Orphan`, ``True`` when examined and owned, ``None`` when not a skill."""
    if not (entry.is_dir() or entry.is_symlink()) or not _SKILL_NAME.match(entry.name):
        return None
    if entry.name in names:
        return True
    skill_md = f"{relative_posix(repo_root, entry)}/{_SKILL_MD}"
    if _independent(manifest, skill_md) or _declared_repo_local(repo_root, entry.name):
        return True
    role = ROLE_LINK if entry.is_symlink() else tree.role
    return Orphan(entry, KIND_SKILL, entry.name, role, _template_rels(KIND_SKILL, entry.name))


def _agent_orphan(
    repo_root: Path,
    manifest: surface_manifest.Manifest | None,
    tree: Tree,
    entry: Path,
    stems: frozenset[str],
) -> Orphan | bool | None:
    if not (entry.is_file() or entry.is_symlink()) or entry.is_dir():
        return None
    if entry.name in tree.excludes or not entry.name.endswith(tree.suffix):
        return None
    stem = entry.name[: -len(tree.suffix)]
    if not stem or "." in stem:
        return None
    if stem in stems:
        return True
    if _independent(manifest, relative_posix(repo_root, entry)):
        return True
    if not entry.is_symlink() and regen_detect_reason(entry) is not None:
        return True
    role = ROLE_LINK if entry.is_symlink() else ROLE_FILE
    return Orphan(entry, KIND_AGENT, stem, role, _template_rels(KIND_AGENT, stem))


def relative_posix(repo_root: Path, path: Path) -> str:
    """Return ``path`` relative to ``repo_root`` with forward slashes, else as given."""
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()
