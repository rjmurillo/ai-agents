#!/usr/bin/env python3
"""Surface parity manifest: the data model, the loader, and file ownership.

Split from ``check_surface_parity.py`` (issue #5637) so the checks and the CLI
stay under the file-size ratchet. ``templates/platforms/surface-parity.yaml``
holds one row per shipped surface; :func:`load_manifest` parses it into
:class:`Surface` rows, :func:`list_files` names the files to classify, and
:func:`owner_of` picks the one surface that owns a path. The relation
vocabulary is documented in ``check_surface_parity.py``.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from yaml_loader import ConfigError, load_platform_config, validate_relative_path  # noqa: E402

MANIFEST_REL = "templates/platforms/surface-parity.yaml"

RELATIONS = frozenset({"generated", "binplaced", "mirrored", "translated", "independent"})
EXTRAS_MODES = frozenset({"allow", "forbid"})
_ALLOWED_KEYS = frozenset(
    {
        "id",
        "path",
        "relation",
        "owner",
        "authority",
        "generator",
        "include",
        "exclude",
        "extras",
        "divergent",
        "authority_exclude",
        "reason",
    }
)
_GENERATOR_REQUIRED = frozenset({"generated", "binplaced"})
_OUTPUT_KEYS = ("outputDir", "outputDirs", "outputConfig", "outputScripts")
_GIT_LOCATION_ENV_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE")
_SKIPPED_DIR_NAMES = frozenset(
    {"__pycache__", ".git", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
)


class SurfaceManifestError(Exception):
    """The surface manifest is missing a required field or is malformed. Exit 2."""


@dataclass(frozen=True, slots=True)
class Surface:
    """One shipped surface: where it lives, what it answers to, who validates it."""

    id: str
    path: str
    relation: str
    owner: str | None = None
    authority: str | None = None
    generator: str | None = None
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    extras: str = "forbid"
    divergent: tuple[str, ...] | None = None
    authority_exclude: tuple[str, ...] = ()
    reason: str | None = None

    @property
    def hand_maintained(self) -> bool:
        """True when no generator keeps the copy fresh and this module must."""
        return self.relation in {"mirrored", "translated"} and self.generator is None

    @property
    def specificity(self) -> tuple[int, int]:
        """Longer path wins; at equal depth a surface with ``include`` wins."""
        return (len(PurePosixPath(self.path).parts), 1 if self.include else 0)


@dataclass(frozen=True, slots=True)
class Manifest:
    """Parsed manifest: roots that must be fully classified, plus every surface."""

    roots: tuple[str, ...]
    surfaces: tuple[Surface, ...]
    # Sorted once here. ``owner_of`` asks for this order once per file, and
    # sorting the rows by path depth each time put the specificity key on the hot
    # path of the classification check (issue #5382). ``dataclasses.replace``
    # rebuilds it, so a manifest with rows removed gets its own order.
    ordered: tuple[Surface, ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Order the rows from most to least specific."""
        ordered = tuple(sorted(self.surfaces, key=lambda s: s.specificity, reverse=True))
        object.__setattr__(self, "ordered", ordered)


@dataclass(frozen=True, slots=True)
class Finding:
    """One parity violation with a file-level location."""

    kind: str
    surface: str
    path: str
    detail: str = ""

    def render(self) -> str:
        tail = f" ({self.detail})" if self.detail else ""
        return f"{self.kind}: [{self.surface or '-'}] {self.path}{tail}"


# --- Manifest loading ------------------------------------------------------


def _relative(label: str, value: object) -> str:
    errors = validate_relative_path(label, value)
    if errors:
        raise SurfaceManifestError("; ".join(errors))
    return str(value).rstrip("/")


def _optional_text(entry: dict[str, object], key: str, label: str) -> str | None:
    value = entry.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise SurfaceManifestError(f"{label}: `{key}` must be a non-empty string")
    return value.strip()


def _optional_path(entry: dict[str, object], key: str, label: str) -> str | None:
    if entry.get(key) is None:
        return None
    return _relative(f"{label}.{key}", entry[key])


def _string_list(entry: dict[str, object], key: str, label: str) -> tuple[str, ...] | None:
    if key not in entry:
        return None
    value = entry[key]
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        raise SurfaceManifestError(f"{label}: `{key}` must be a list of non-empty strings")
    return tuple(value)


def _validate_relation_fields(s: Surface, label: str) -> None:
    if s.relation not in RELATIONS:
        raise SurfaceManifestError(f"{label}: unknown relation {s.relation!r}")
    if s.extras not in EXTRAS_MODES:
        raise SurfaceManifestError(f"{label}: `extras` must be one of {sorted(EXTRAS_MODES)}")
    if s.relation == "independent":
        if not s.reason:
            raise SurfaceManifestError(f"{label}: an independent surface needs a `reason`")
        if s.authority or s.generator:
            raise SurfaceManifestError(f"{label}: an independent surface has no authority")
        return
    if not s.owner:
        raise SurfaceManifestError(f"{label}: `owner` (the validating gate) is required")
    if not s.authority:
        raise SurfaceManifestError(f"{label}: `authority` is required for {s.relation}")
    if s.relation in _GENERATOR_REQUIRED and not s.generator:
        raise SurfaceManifestError(f"{label}: `generator` is required for {s.relation}")
    _validate_divergence(s, label)


def _validate_divergence(s: Surface, label: str) -> None:
    hand_translated = s.relation == "translated" and s.generator is None
    if hand_translated and s.divergent is None:
        raise SurfaceManifestError(
            f"{label}: a hand-maintained translated surface must list `divergent` files"
        )
    if s.divergent is not None and not hand_translated:
        raise SurfaceManifestError(
            f"{label}: `divergent` applies only to a translated surface with no generator"
        )


def _parse_surface(entry: object, index: int) -> Surface:
    label = f"surfaces[{index}]"
    if not isinstance(entry, dict):
        raise SurfaceManifestError(f"{label}: must be a mapping")
    unknown = sorted(set(entry) - _ALLOWED_KEYS)
    if unknown:
        raise SurfaceManifestError(f"{label}: unknown keys {unknown}")
    sid = _optional_text(entry, "id", label)
    if not sid:
        raise SurfaceManifestError(f"{label}: `id` is required")
    label = f"surfaces[{sid}]"
    surface = Surface(
        id=sid,
        path=_relative(f"{label}.path", entry.get("path")),
        relation=str(entry.get("relation") or ""),
        owner=_optional_text(entry, "owner", label),
        authority=_optional_path(entry, "authority", label),
        generator=_optional_path(entry, "generator", label),
        include=_string_list(entry, "include", label) or (),
        exclude=_string_list(entry, "exclude", label) or (),
        extras=str(entry.get("extras") or "forbid"),
        divergent=_string_list(entry, "divergent", label),
        authority_exclude=_string_list(entry, "authority_exclude", label) or (),
        reason=_optional_text(entry, "reason", label),
    )
    _validate_relation_fields(surface, label)
    return surface


def _reject_duplicates(surfaces: Sequence[Surface]) -> None:
    ids: set[str] = set()
    shapes: set[tuple[str, tuple[str, ...], tuple[str, ...]]] = set()
    for s in surfaces:
        if s.id in ids:
            raise SurfaceManifestError(f"duplicate surface id {s.id!r}")
        ids.add(s.id)
        shape = (s.path, s.include, s.exclude)
        if shape in shapes:
            raise SurfaceManifestError(f"surface {s.id!r} repeats path/include/exclude {shape}")
        shapes.add(shape)


def load_manifest(repo_root: Path) -> Manifest | None:
    """Parse the manifest; ``None`` when the file is absent.

    Raises :class:`SurfaceManifestError` on any malformed field.
    """
    manifest_path = repo_root / MANIFEST_REL
    if not manifest_path.is_file():
        return None
    try:
        doc = load_platform_config(manifest_path)
    except ConfigError as exc:
        raise SurfaceManifestError(str(exc)) from exc
    raw_roots = doc.get("roots")
    raw_surfaces = doc.get("surfaces")
    if not isinstance(raw_roots, list) or not raw_roots:
        raise SurfaceManifestError(f"{manifest_path}: `roots` must be a non-empty list")
    if not isinstance(raw_surfaces, list) or not raw_surfaces:
        raise SurfaceManifestError(f"{manifest_path}: `surfaces` must be a non-empty list")
    roots = tuple(_relative(f"roots[{i}]", r) for i, r in enumerate(raw_roots))
    surfaces = tuple(_parse_surface(e, i) for i, e in enumerate(raw_surfaces))
    _reject_duplicates(surfaces)
    return Manifest(roots=roots, surfaces=surfaces)


# --- File universe and ownership -------------------------------------------


def _scrubbed_env() -> dict[str, str]:
    env = dict(os.environ)
    for key in _GIT_LOCATION_ENV_VARS:
        env.pop(key, None)
    return env


def _git_listing(repo_root: Path) -> list[str] | None:
    try:
        proc = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "ls-files",
                "-z",
                "--cached",
                "--others",
                "--exclude-standard",
            ],
            capture_output=True,
            check=False,
            timeout=60,
            env=_scrubbed_env(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0 or not proc.stdout:
        return None
    return [n for n in proc.stdout.decode("utf-8", "replace").split("\0") if n]


def _walk_listing(repo_root: Path) -> list[str]:
    names: list[str] = []
    for dirpath, dirnames, filenames in os.walk(repo_root):
        dirnames[:] = [d for d in dirnames if d not in _SKIPPED_DIR_NAMES]
        base = Path(dirpath).relative_to(repo_root)
        names.extend((base / f).as_posix() for f in filenames if not f.endswith(".pyc"))
    return names


def list_files(repo_root: Path) -> list[str]:
    """Repo-relative POSIX paths of tracked and untracked-not-ignored files.

    Falls back to a directory walk outside a git work tree. A path git still
    lists after deletion is dropped so the answer reflects the working tree.
    """
    names = _git_listing(repo_root)
    if names is None:
        names = _walk_listing(repo_root)
    return sorted(n for n in set(names) if (repo_root / n).is_file())


def rel_to(path: str, base: str) -> str | None:
    """``path`` relative to ``base``: ``""`` when equal, ``None`` when outside."""
    if path == base:
        return ""
    if path.startswith(base + "/"):
        return path[len(base) + 1 :]
    return None


def join(base: str, rel: str) -> str:
    return f"{base}/{rel}" if rel else base


def matches(surface: Surface, rel: str) -> bool:
    if not rel:
        return True
    pure = PurePosixPath(rel)
    if surface.include and not any(pure.full_match(g) for g in surface.include):
        return False
    return not any(pure.full_match(g) for g in surface.exclude)


def owner_of(manifest: Manifest, path: str) -> tuple[Surface | None, bool]:
    """Return ``(owning surface, ambiguous)`` for a repo-relative path."""
    first: Surface | None = None
    for surface in manifest.ordered:
        rel = rel_to(path, surface.path)
        if rel is None or not matches(surface, rel):
            continue
        if first is None:
            first = surface
            continue
        return first, surface.specificity == first.specificity
    return first, False
