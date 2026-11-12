"""Ratchet for the legacy plugin-root form in authored files (ADR-121 rollout step 3).

``check_plugin_root_interpreter.py`` accepts two forms: the legacy
``python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/..."`` and
the locator. The legacy form stays valid for Class G and while sites migrate.
This ratchet keeps it from spreading. It counts legacy sites in authored files
and compares each group with ``LEGACY_SITE_BASELINE`` in
``plugin_root_interpreter_allowances.py``.

* A count above the baseline fails: a new site used the legacy form.
* A count below the baseline fails too: a batch migrated and the baseline did
  not move, which would leave room for new legacy sites to slip in.

Authored files are the ones a person edits. Renders are not counted, because one
site in a template would otherwise count once per host tree: ``SKILL.md`` renders,
and ``src/claude/{agents,rules,hooks,lib}``. Two modules under ``src/claude/lib`` are
the exception: ``build/scripts/lib_hand_files.py`` lists them in ``PLUGIN_LIB_FILES``
as hand-maintained, so they count as authored. Mirrors under the other ``src/``
trees are renders of those. Pure functions: no file reads, no git.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping
from pathlib import Path

from scripts.validation.plugin_root_interpreter_sites import LegacyCounts

_BUILD_SCRIPTS = Path(__file__).resolve().parents[2] / "build" / "scripts"
if str(_BUILD_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_BUILD_SCRIPTS))

from lib_hand_files import PLUGIN_LIB_FILES  # noqa: E402

# Rendered from templates/ or scripts/, never edited here (src/claude/AGENTS.md). The
# exception is `lib/<name>` for a name in PLUGIN_LIB_FILES (build/scripts/lib_hand_files.py):
# those modules are hand-maintained, so a person edits them in place and they count.
_RENDERED_UNDER_SRC_CLAUDE = frozenset({"agents", "rules", "hooks", "lib"})
_YAML_SUFFIXES = (".yaml", ".yml")
# Shipped YAML is Class G: the completion gate dispatches it and it keeps the
# legacy form for good (ADR-121 decision 1), so it ratchets apart from the rest.
GATE_YAML_GROUP = "src/claude yaml"
SRC_CLAUDE_GROUP = "src/claude"


def _is_hand_lib_file(parts: list[str]) -> bool:
    """Return whether ``parts`` name a hand-maintained module in ``src/claude/lib``."""
    return len(parts) == 4 and parts[2] == "lib" and parts[3] in PLUGIN_LIB_FILES


def authored_group(rel: str) -> str | None:
    """Return the ratchet group of an authored file, or ``None`` for a render or other tree.

    ``rel`` is a repository-relative POSIX path. ``templates/<class>/...`` groups by
    class (``templates/agents``, ``templates/skills``). Files under
    ``src/claude/skills/<name>/`` other than ``SKILL.md`` are hand-maintained
    support files and group as ``src/claude`` (or ``src/claude yaml``), as do the
    hand-maintained ``src/claude/lib`` modules in ``PLUGIN_LIB_FILES``.
    """
    parts = rel.split("/")
    if parts[0] == "templates":
        return f"templates/{parts[1]}" if len(parts) > 2 else "templates"
    if parts[:2] != ["src", "claude"] or len(parts) < 3:
        return None
    if parts[2] in _RENDERED_UNDER_SRC_CLAUDE and not _is_hand_lib_file(parts):
        return None
    if parts[2] == "skills" and len(parts) == 5 and parts[4] == "SKILL.md":
        return None
    return GATE_YAML_GROUP if rel.endswith(_YAML_SUFFIXES) else SRC_CLAUDE_GROUP


def tally(counts: dict[str, LegacyCounts], group: str, found: LegacyCounts) -> None:
    """Add ``found`` to the running count of ``group``."""
    before = counts.get(group, LegacyCounts())
    counts[group] = LegacyCounts(
        before.invocations + found.invocations, before.assignments + found.assignments
    )


def ratchet_messages(
    counts: Mapping[str, LegacyCounts], baseline: Mapping[str, tuple[int, int, str]]
) -> list[str]:
    """Return one message per group whose legacy-site count differs from its baseline."""
    messages: list[str] = []
    for group in sorted(set(counts) | set(baseline)):
        found = counts.get(group, LegacyCounts())
        allowed_inv, allowed_asg, _reason = baseline.get(group, (0, 0, ""))
        shown = (
            f"legacy plugin-root sites in {group}: {found.invocations} invocation(s) and "
            f"{found.assignments} assignment(s), baseline {allowed_inv} and {allowed_asg}"
        )
        if found.invocations > allowed_inv or found.assignments > allowed_asg:
            messages.append(
                f"{shown}. Write a new Class S command as the locator from "
                "build/scripts/plugin_run_launcher.py, or run build/scripts/plugin_run_fix.py "
                "--fix on the file (ADR-121). The baseline only moves down; lower the "
                "baseline when a batch migrates."
            )
        elif found.invocations < allowed_inv or found.assignments < allowed_asg:
            messages.append(
                f"{shown}. A batch migrated: lower the baseline when a batch migrates "
                "(LEGACY_SITE_BASELINE in plugin_root_interpreter_allowances.py), so the "
                "freed room cannot take new legacy sites."
            )
    return messages
