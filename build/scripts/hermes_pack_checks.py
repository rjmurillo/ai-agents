"""Checks that gate the Hermes pack build (ADR-115 Decision 6).

Every check returns a list of problem strings and never raises for a rule
violation, so the caller can print all of them in one run. Filesystem access is
limited to reading the skill tree; rendering and writing live in ``hermes_packs``.

What counts as a reference
--------------------------

A skill refers to another shipped skill when any text file in its folder holds
either form below with a shipped skill's name in the ``<name>`` slot:

- ``skills/<name>/<sub>``, the repository-style path;
- ``../<name>/<sub>``, a relative link out of the skill folder;

where ``<sub>`` is ``scripts``, ``references``, ``lib``, ``templates``,
``assets``, or ``resources``. ADR-115 measured the first form (43 edges). The
second form finds 10 more real links, such as ``memory-gate`` linking to
``../../memory-search/references/``, which the first form misses. A bare
``name/scripts`` is not matched: ``build/scripts`` names a repository folder and
a skill at once, so it would fire on every path into the build tree. A reference
the regexes cannot see (a path assembled at run time) is outside this check.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from binplace_manifest import is_bytecode_artifact
from hermes_pack_config import (
    HERMES_MAX_FILE_BYTES,
    HERMES_MAX_PACK_BYTES,
    HERMES_MAX_PACK_FILES,
    HermesConfig,
    HermesPackError,
)

_SUBDIRS = r"(?:scripts|references|lib|templates|assets|resources)"
_NAME = r"([a-z0-9][a-z0-9-]*)"
REFERENCE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(rf"(?<![\w-])skills/{_NAME}/{_SUBDIRS}\b"),
    re.compile(rf"(?<![\w.-])(?:\.\./)+{_NAME}/{_SUBDIRS}\b"),
)

# skill -> {referenced skill: "<file>: <matched text>"}
References = dict[str, dict[str, str]]


@dataclass(frozen=True)
class PackFile:
    """One file of a rendered pack: its bytes and permission bits."""

    data: bytes
    mode: int


def discover_skills(source_root: Path) -> list[str]:
    """Return the sorted names of immediate subfolders that hold a ``SKILL.md``."""
    if not source_root.is_dir():
        raise HermesPackError([f"skills sourceDir not found: {source_root}"])
    return sorted(
        child.name
        for child in source_root.iterdir()
        if child.is_dir() and (child / "SKILL.md").is_file()
    )


def skill_files(skill_dir: Path) -> list[Path]:
    """Return every file in a skill folder, sorted, without bytecode caches.

    A symlink anywhere is refused: the pack copies bytes with no containment
    check of its own, so a link could pull a file from outside the skill into a
    customer-installed package (CWE-22, CWE-59).
    """
    found: list[Path] = []
    for path in sorted(skill_dir.rglob("*")):
        if path.is_symlink():
            raise HermesPackError([f"{path}: symlink inside a skill folder refused"])
        if path.is_dir() or is_bytecode_artifact(path.relative_to(skill_dir)):
            continue
        found.append(path)
    return found


def find_references(source_root: Path, skills: list[str]) -> References:
    """Map each skill to the other shipped skills its files refer to."""
    shipped = set(skills)
    refs: References = {}
    for name in skills:
        skill_dir = source_root / name
        for path in skill_files(skill_dir):
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            where = path.relative_to(skill_dir).as_posix()
            for pattern in REFERENCE_PATTERNS:
                for match in pattern.finditer(text):
                    target = match.group(1)
                    if target in shipped and target != name:
                        refs.setdefault(name, {}).setdefault(target, f"{where}: {match.group(0)}")
    return refs


def exclusion_closure(refs: References, seeds: set[str]) -> set[str]:
    """Return ``seeds`` plus every skill that refers to a member, transitively."""
    closure = set(seeds)
    changed = True
    while changed:
        changed = False
        for name, targets in refs.items():
            if name not in closure and closure.intersection(targets):
                closure.add(name)
                changed = True
    return closure


def _pack_of(config: HermesConfig) -> dict[str, str]:
    return {skill: pack.key for pack in config.packs for skill in pack.skills}


def check_assignment(shipped: list[str], config: HermesConfig) -> list[str]:
    """Every shipped skill is in exactly one pack or in ``excluded``; no stale names."""
    problems: list[str] = []
    seen: dict[str, str] = {}
    for pack in config.packs:
        for skill in pack.skills:
            if skill in seen:
                problems.append(
                    f"skill {skill!r} is in two packs: {seen[skill]!r} and {pack.key!r}"
                )
            seen.setdefault(skill, pack.key)
    for skill in sorted(set(seen) & set(config.excluded)):
        problems.append(f"skill {skill!r} is in pack {seen[skill]!r} and in `excluded`")
    known = set(shipped)
    for skill in sorted((set(seen) | set(config.excluded)) - known):
        problems.append(
            f"skill {skill!r} is named in hermes.yaml but no shipped skill has that name"
        )
    for skill in sorted(known - set(seen) - set(config.excluded)):
        problems.append(f"shipped skill {skill!r} is in no pack and not in `excluded`")
    return problems


def check_references(config: HermesConfig, refs: References) -> list[str]:
    """No packed skill refers to a skill in another pack or to an excluded skill."""
    problems: list[str] = []
    pack_of = _pack_of(config)
    closure = exclusion_closure(refs, set(config.excluded))
    for skill in sorted(pack_of):
        for target, example in sorted(refs.get(skill, {}).items()):
            if target in config.excluded:
                problems.append(
                    f"skill {skill!r} refers to excluded skill {target!r} ({example}); "
                    f"exclude {skill!r} too, or remove the reference"
                )
            elif target in pack_of and pack_of[target] != pack_of[skill]:
                problems.append(
                    f"skill {skill!r} (pack {pack_of[skill]!r}) refers to {target!r} "
                    f"(pack {pack_of[target]!r}) ({example}); keep them in one pack"
                )
    missing = sorted(closure - set(config.excluded))
    if missing:
        problems.append(f"the exclusion closure also needs: {', '.join(missing)}")
    return problems


def check_pack_limits(pack_dir: str, files: dict[str, PackFile], config: HermesConfig) -> list[str]:
    """A pack, counting ``lib/``, stays under the file, size, and per-file caps."""
    problems: list[str] = []
    if len(files) > config.pack_max_files:
        problems.append(
            f"pack {pack_dir} has {len(files)} files; packMaxFiles is {config.pack_max_files} "
            f"(Hermes refuses more than {HERMES_MAX_PACK_FILES})"
        )
    total = sum(len(f.data) for f in files.values())
    if total > HERMES_MAX_PACK_BYTES:
        problems.append(
            f"pack {pack_dir} is {total} bytes; Hermes refuses more than {HERMES_MAX_PACK_BYTES}"
        )
    for rel, packed in sorted(files.items()):
        if len(packed.data) > HERMES_MAX_FILE_BYTES:
            problems.append(
                f"{pack_dir}/{rel} is {len(packed.data)} bytes; "
                f"Hermes refuses a file over {HERMES_MAX_FILE_BYTES}"
            )
    return problems
