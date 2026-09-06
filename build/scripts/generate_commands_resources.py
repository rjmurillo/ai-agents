#!/usr/bin/env python3
"""Non-body files a Claude command ships, for ``generate_commands.py``.

A command's SKILL.md mirror is one file. Everything else the command needs at
runtime travels beside it, and this module owns discovering and copying that:

- **Resources.** Top-level sidecars matched by ``artifacts.commands.
  resourceSuffixes`` (``pr-review-config.yaml`` today), copied flat into
  ``resourceOutputDir``.
- **References.** A per-command progressive-disclosure tree at
  ``.claude/commands/<name>/references/**``, mirrored into
  ``referencesOutputDir`` at ``<name>/references/**``.

Progressive disclosure for commands
-----------------------------------

A command may carry a ``references/`` tree the same way a skill does. The body
at ``.claude/commands/<name>.md`` stays under the 200-line ceiling
``scripts/validation/command_size.py`` enforces, and the depth sits behind a
path the body points at. Both trees land the tree at the same
plugin-root-relative path, so one spelling resolves everywhere:

    ${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/commands/<name>/references/<file>

That is the root list ``.claude/commands/pr-review.md`` already walks to reach
``commands/pr-review-config.yaml``; its ``resolve_pr_review_config`` tries
``${COPILOT_PLUGIN_ROOT}``, ``${CLAUDE_PLUGIN_ROOT}``, ``$repo_root/.claude``,
then the two installed-plugin caches, testing ``$root/commands/pr-review-
config.yaml`` at each. Mirroring references into ``skills/<name>/references/``
instead would have made the Claude-relative and Copilot-relative spellings
differ, which is a broken link in whichever tree the author did not test.

Files are copied byte-for-byte. ``generate_skills.py`` translates only the
top-level ``SKILL.md`` of a skill and copies the rest verbatim; a command's
references get the same treatment, because they are read on demand rather than
loaded as a harness prompt.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))

from regen_guard import detect_reason as regen_detect_reason  # noqa: E402
from yaml_loader import validate_relative_path  # noqa: E402

# The per-command progressive-disclosure directory, named to match
# `.claude/skills/<name>/references/` so one convention covers both surfaces.
REFERENCES_DIR_NAME = "references"


class GenerateCommandsError(Exception):
    """Domain error for command-to-skill bridging.

    Defined here rather than in ``generate_commands.py`` because the config
    validation that raises it lives here; the bridge imports it so callers see
    one error type for the whole generator.
    """


def resolve_optional_output_dir(
    repo_root: Path, field: str, value: object, *, present: bool
) -> Path | None:
    """Resolve an optional output directory from the platform config."""
    if not present:
        return None
    errs = validate_relative_path(field, value)
    if errs:
        raise GenerateCommandsError("; ".join(errs))
    assert isinstance(value, str)
    return repo_root / value


def resolve_resource_suffixes(stanza: dict[str, object]) -> set[str]:
    """Validate and normalize optional command resource suffixes."""
    has_resource_output = "resourceOutputDir" in stanza
    has_resource_suffixes = "resourceSuffixes" in stanza
    if has_resource_output != has_resource_suffixes:
        raise GenerateCommandsError(
            "`artifacts.commands`: `resourceOutputDir` and "
            "`resourceSuffixes` must be set together"
        )
    if not has_resource_suffixes:
        return set()
    suffixes = stanza.get("resourceSuffixes")
    if (
        not isinstance(suffixes, list)
        or not suffixes
        or not all(
            isinstance(item, str)
            and item.startswith(".")
            and len(item) > 1
            for item in suffixes
        )
    ):
        raise GenerateCommandsError(
            "`artifacts.commands.resourceSuffixes`: must be a "
            "non-empty list of dotted suffix strings"
        )
    return set(suffixes)


def iter_resource_sources(
    source_dir: Path, suffixes: set[str], excludes: set[str]
) -> list[Path]:
    """Return top-level command resource files matching configured suffixes."""
    if not suffixes:
        return []
    resources: list[Path] = []
    for child in sorted(source_dir.iterdir()):
        if not child.is_file():
            continue
        if child.name in excludes:
            continue
        if child.suffix in suffixes:
            resources.append(child)
    return resources


def iter_reference_sources(command_dir: Path) -> list[Path]:
    """Return every file under one command's ``references/`` tree, sorted.

    Recurses, so a command may nest its depth the way a skill does. Python
    cache artifacts are skipped for the same reason ``generate_skills.py``
    skips them: they are build-time noise, not plugin content.
    """
    refs_dir = command_dir / REFERENCES_DIR_NAME
    if not refs_dir.is_dir():
        return []
    files: list[Path] = []
    for path in sorted(refs_dir.rglob("*")):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts or path.suffix in (".pyc", ".pyo"):
            continue
        files.append(path)
    return files


def collect_reference_sets(
    source_dir: Path, excludes: set[str]
) -> dict[str, list[Path]]:
    """Map each command-name directory holding a ``references/`` tree to its files.

    Keyed by directory name, which is the command stem the tree belongs to.
    Directories with no ``references/`` subtree, and trees holding only cache
    artifacts, are omitted so callers can treat a present key as real content.
    """
    sets: dict[str, list[Path]] = {}
    for child in sorted(source_dir.iterdir()):
        if not child.is_dir():
            continue
        if child.name in excludes:
            continue
        files = iter_reference_sources(child)
        if files:
            sets[child.name] = files
    return sets


def copy_resource(src: Path, target: Path, *, what_if: bool) -> bool:
    """Copy one command resource or reference. True on write, False on skip."""
    reason = regen_detect_reason(target)
    if reason is not None:
        print(f"  NOTICE: skipped {target} (NO-REGEN: {reason})")
        return False
    if what_if:
        print(f"  Would copy: {target}")
        return True
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(src.read_bytes())
    return True
