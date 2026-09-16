"""The change-class table for gate_latency.py (REQ-027 data model: ChangeClass).

Split out so ``scripts/metrics/gate_latency.py`` stays under the project's
500-line taste-lint ceiling, the same reason ``lefthook_summary.py`` and
``gate_latency_io.py`` were split out (see those modules' docstrings).

Fixed, in-module, never user-supplied free text (REQ-027 Security section):
a caller selects a name; the file list behind it is this table's, not the
caller's, so no path escapes into the lefthook subprocess as untrusted
data. Every path is validated to exist at startup (AC-08, via
``missing_change_class_paths``, called from ``gate_latency.main``). "none"
is the reserved no-file class; every other class names one repo-relative
path known to exist at the time this module was written, chosen to be
stable (owned by this repository's own tooling, not a scratch file).

Each class is chosen so that one of the five pre-push jobs issue #5318 item
1 names actually fires, which is what AC-08 asks for. The mapping, read off
``lefthook.yml`` this session: ``python`` fires ``python-type-check``
(glob ``**/*.py``); ``skills`` fires ``plugin-load-e2e`` (glob
``.claude/skills/**``); ``workflows`` fires ``workflow-local-run`` (glob
``.github/workflows/**/*.{yml,yaml}``); ``hooks`` fires
``hook-anchoring-e2e`` (whose glob list names
``build/scripts/generate_hooks.py`` outright); and ``security-scan``
declares no glob, so it runs on every pre-push regardless of class.
"""

from __future__ import annotations

from pathlib import Path

CHANGE_CLASSES: dict[str, tuple[str, ...]] = {
    "none": (),
    "markdown": ("README.md",),
    "python": ("scripts/ci/lefthook_budget_model.py",),
    "skills": (".claude/skills/spec/SKILL.md",),
    "workflows": (".github/workflows/pytest.yml",),
    "hooks": ("build/scripts/generate_hooks.py",),
}


def get_change_class_files(name: str) -> tuple[str, ...] | None:
    """The file list for ``name``, or ``None`` if ``name`` is not a known class."""
    return CHANGE_CLASSES.get(name)


def missing_change_class_paths(repo: Path, files: tuple[str, ...]) -> list[str]:
    """Repo-relative paths in ``files`` that do not exist under ``repo`` (AC-08)."""
    return [rel for rel in files if not (repo / rel).is_file()]
