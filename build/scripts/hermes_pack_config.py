"""Parse the ``artifacts.skills`` stanza of ``templates/platforms/hermes.yaml``.

ADR-115 Decision 6: the Hermes tree is a set of packs, each a portable Agent
Plugins v1 package under ``src/hermes/project-toolkit-<name>/``. A hand
maintained ``packs`` table says which pack carries each shipped skill, and an
``excluded`` table names the skills that ship nowhere, each with a reason.

This module only turns the YAML stanza into typed values and rejects a
malformed stanza. Whether the table matches the skills on disk is checked in
``hermes_pack_checks``; rendering lives in ``hermes_packs``.

Hermes install limits (``tools/plugin_guard.py`` lines 106-108 at hermes-agent
commit 63d0b94120027d487c9a5235b9ec64b696af1b26): 400 files, 10 MB in total,
1 MB per file. ``packMaxFiles`` is the toolkit's own budget under the 400-file
cap, so it may not exceed it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

HERMES_MAX_PACK_FILES = 400
HERMES_MAX_PACK_BYTES = 10 * 1024 * 1024
HERMES_MAX_FILE_BYTES = 1024 * 1024

PACK_PREFIX = "project-toolkit-"
PLUGIN_SCHEMA_URL = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
# Agent Plugins v1 name rule, copied from hermes_cli/agent_plugins.py at the
# pinned commit: at most 64 characters, lowercase alphanumerics and single
# hyphens. The pack directory name is ``PACK_PREFIX + <key>`` and must satisfy it.
PACK_DIR_RE = re.compile(r"^(?!.*--)[a-z0-9]+(?:-[a-z0-9]+)*$")
PACK_DIR_MAX_LEN = 64


class HermesPackError(Exception):
    """A malformed stanza or a pack build the generator refuses.

    ``problems`` holds one message per violation so the caller prints all of
    them, not only the first.
    """

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass(frozen=True)
class PackSpec:
    """One pack: its key, manifest description, and ordered skill names."""

    key: str
    description: str
    skills: tuple[str, ...]

    @property
    def dir_name(self) -> str:
        return f"{PACK_PREFIX}{self.key}"


@dataclass(frozen=True)
class HermesConfig:
    """Typed view of the ``hermes-packs`` skills stanza."""

    source_dir: str
    output_dir: str
    pack_max_files: int
    hermes_commit: str
    frontmatter_drop: frozenset[str]
    packs: tuple[PackSpec, ...]
    excluded: dict[str, str]


def _require_str(stanza: dict[str, object], key: str, problems: list[str]) -> str:
    value = stanza.get(key)
    if not isinstance(value, str) or not value.strip():
        problems.append(f"`artifacts.skills.{key}` must be a non-empty string")
        return ""
    return value


def _parse_max_files(stanza: dict[str, object], problems: list[str]) -> int:
    value = stanza.get("packMaxFiles")
    # bool is an int subclass; `packMaxFiles: true` must not read as 1.
    if not isinstance(value, int) or isinstance(value, bool):
        problems.append("`artifacts.skills.packMaxFiles` must be an integer")
        return 0
    if not 1 <= value <= HERMES_MAX_PACK_FILES:
        problems.append(
            f"`artifacts.skills.packMaxFiles` is {value}; it must be between 1 and "
            f"{HERMES_MAX_PACK_FILES}, the Hermes install cap"
        )
    return value


def _parse_drop(stanza: dict[str, object], problems: list[str]) -> frozenset[str]:
    raw = stanza.get("frontmatterDrop", [])
    if not isinstance(raw, list) or not all(isinstance(key, str) for key in raw):
        problems.append("`artifacts.skills.frontmatterDrop` must be a list of strings")
        return frozenset()
    return frozenset(raw)


def _parse_one_pack(key: object, body: object, problems: list[str]) -> PackSpec | None:
    label = f"`artifacts.skills.packs.{key}`"
    if not isinstance(key, str) or not key:
        problems.append("`artifacts.skills.packs` keys must be non-empty strings")
        return None
    dir_name = f"{PACK_PREFIX}{key}"
    if len(dir_name) > PACK_DIR_MAX_LEN or not PACK_DIR_RE.fullmatch(dir_name):
        problems.append(
            f"{label}: directory name {dir_name!r} must be at most {PACK_DIR_MAX_LEN} "
            "characters of lowercase letters, digits, and single hyphens"
        )
        return None
    if not isinstance(body, dict) or set(body) != {"description", "skills"}:
        problems.append(f"{label} must be a mapping with exactly `description` and `skills`")
        return None
    description, skills = body["description"], body["skills"]
    if not isinstance(description, str) or not 1 <= len(description) <= 1024:
        problems.append(f"{label}.description must be a string of 1 to 1024 characters")
        return None
    if not isinstance(skills, list) or not skills or not all(isinstance(s, str) for s in skills):
        problems.append(f"{label}.skills must be a non-empty list of skill names")
        return None
    return PackSpec(key=key, description=description, skills=tuple(skills))


def _parse_packs(stanza: dict[str, object], problems: list[str]) -> tuple[PackSpec, ...]:
    raw = stanza.get("packs")
    if not isinstance(raw, dict) or not raw:
        problems.append("`artifacts.skills.packs` must be a non-empty mapping")
        return ()
    parsed = [_parse_one_pack(key, body, problems) for key, body in raw.items()]
    return tuple(pack for pack in parsed if pack is not None)


def _parse_excluded(stanza: dict[str, object], problems: list[str]) -> dict[str, str]:
    raw = stanza.get("excluded")
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        problems.append("`artifacts.skills.excluded` must be a mapping of skill name to reason")
        return {}
    excluded: dict[str, str] = {}
    for name, reason in raw.items():
        if not isinstance(name, str) or not isinstance(reason, str) or not reason.strip():
            problems.append(f"`artifacts.skills.excluded.{name}` needs a non-empty reason string")
            continue
        excluded[name] = reason.strip()
    return excluded


def parse_stanza(stanza: dict[str, object]) -> HermesConfig:
    """Return the typed config, or raise :class:`HermesPackError` listing every problem."""
    problems: list[str] = []
    source_dir = _require_str(stanza, "sourceDir", problems)
    output_dir = _require_str(stanza, "outputDir", problems)
    commit = _require_str(stanza, "hermesCommit", problems)
    if commit and not COMMIT_RE.fullmatch(commit):
        problems.append("`artifacts.skills.hermesCommit` must be a 40-character lowercase SHA")
    max_files = _parse_max_files(stanza, problems)
    drop = _parse_drop(stanza, problems)
    packs = _parse_packs(stanza, problems)
    excluded = _parse_excluded(stanza, problems)
    if problems:
        raise HermesPackError(problems)
    return HermesConfig(
        source_dir=source_dir,
        output_dir=output_dir,
        pack_max_files=max_files,
        hermes_commit=commit,
        frontmatter_drop=drop,
        packs=packs,
        excluded=excluded,
    )
