"""Vendor-portable path resolution for skill scripts (Issue #2050).

Skills that ship in a vendored plugin install (Copilot CLI and similar
harnesses) cannot assume the consumer repo has a `.claude/` directory or
the upstream `.agents/` tree. This module centralizes the two resolution
policies every skill needs so no script hard-codes an upstream-only path.

Two policies:

- `resolve_skill_resource(skill, relpath)` is the READ path. It locates a
  file that ships inside the plugin (a reference doc, a helper script). The
  candidate order mirrors the `/review` skill's documented "Path resolution
  (harness-agnostic)" section in `.claude/skills/review/SKILL.md`:
    1. `${CLAUDE_PLUGIN_ROOT}/skills/<skill>/<relpath>` when CLAUDE_PLUGIN_ROOT
       is set by the harness.
    2. `.claude/skills/<skill>/<relpath>` resolved from the current working
       directory (Claude Code project layout).
    3. `skills/<skill>/<relpath>` resolved relative to the plugin install
       root discovered by walking up from this file to the
       `.claude-plugin/plugin.json` marker (vendored install).
  Returns the first candidate that exists, else None. Read-only: it never
  creates anything.

- `resolve_artifact_root(subdir)` is the WRITE path. Skills write artifacts
  to a consumer-side location, defaulting to `<cwd>/.agents/<subdir>`. The
  directory is created lazily (parents=True, exist_ok=True). The root is
  overridable by the `AI_AGENTS_ARTIFACT_ROOT` environment variable so a
  consumer can redirect every skill's output to one place.

Stricter/looser/different than canonical:
  The read-path candidate order is a strict mirror of the `/review` skill's
  three-candidate chain (CLAUDE_PLUGIN_ROOT, `.claude/`, plugin-root-relative)
  with the verbatim contract preserved. The write path is new (the `/review`
  skill has no write artifact), modeled on `/spec` Step 0 writing
  `.agents/metrics/STEP-0-METRICS.md` lazily under the consumer cwd. The
  AI_AGENTS_ARTIFACT_ROOT override is added so the consumer, not the skill,
  owns the artifact location.

Canonical read-path pattern: `.claude/skills/review/SKILL.md`,
section "Path resolution (harness-agnostic)". Plugin-root marker reuse:
`.claude/lib/bootstrap.py::resolve_plugin_lib_dir` (CLAUDE_PLUGIN_ROOT then
the `.claude-plugin/plugin.json` walk-up). This file is a sibling write-path
resolver to that read-path resolver per the Issue #2050 batch decision.
"""

from __future__ import annotations

import os
from pathlib import Path

_PLUGIN_MARKER = Path(".claude-plugin") / "plugin.json"


def _plugin_install_root() -> Path | None:
    """Return the plugin install root, or None when no marker is found.

    Prefers CLAUDE_PLUGIN_ROOT. Otherwise walks up from this file looking
    for the `.claude-plugin/plugin.json` manifest marker, the same marker
    `bootstrap.resolve_plugin_lib_dir` uses.
    """
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if plugin_root:
        return Path(plugin_root).resolve()

    cur = Path(__file__).resolve().parent
    while True:
        if (cur / _PLUGIN_MARKER).is_file():
            return cur
        if cur.parent == cur:
            return None
        cur = cur.parent


def _normalize_relpath(relpath: str | Path) -> Path:
    """Reject absolute paths and parent-escapes in a skill relative path.

    A skill resource path is always relative to the skill directory. An
    absolute path or a `..` segment is a caller bug and a traversal risk,
    so raise rather than resolve it.
    """
    rel = Path(relpath)
    if rel.is_absolute():
        raise ValueError(f"relpath must be relative, got absolute: {relpath!r}")
    if ".." in rel.parts:
        raise ValueError(f"relpath must not contain '..': {relpath!r}")
    return rel


def resolve_skill_resource(skill: str, relpath: str | Path) -> Path | None:
    """Resolve a read-only resource shipped inside a skill.

    Tries each candidate in order and returns the first that exists:
      1. `${CLAUDE_PLUGIN_ROOT}/skills/<skill>/<relpath>`
      2. `<cwd>/.claude/skills/<skill>/<relpath>`
      3. `<plugin install root>/skills/<skill>/<relpath>`

    Args:
        skill: Skill directory name (for example "review").
        relpath: Path of the resource within the skill directory, relative
            (for example "references/analyst.md"). Must not be absolute or
            contain a `..` segment.

    Returns:
        The resolved absolute Path of the first existing candidate, or None
        when no candidate exists.

    Raises:
        ValueError: When skill is empty or relpath is absolute or escapes
            the skill directory with `..`.
    """
    if not skill or not skill.strip():
        raise ValueError("skill must be a non-empty name")
    rel = _normalize_relpath(relpath)

    candidates: list[Path] = []

    plugin_env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if plugin_env:
        candidates.append(Path(plugin_env).resolve() / "skills" / skill / rel)

    candidates.append(Path.cwd() / ".claude" / "skills" / skill / rel)

    install_root = _plugin_install_root()
    if install_root is not None:
        candidates.append(install_root / "skills" / skill / rel)

    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()

    return None


def resolve_artifact_root(subdir: str | Path) -> Path:
    """Resolve and create the write directory for a skill artifact.

    The default root is `<cwd>/.agents`, overridable by the
    `AI_AGENTS_ARTIFACT_ROOT` environment variable. The returned directory
    (`<root>/<subdir>`) is created lazily with parents.

    Args:
        subdir: Artifact subdirectory under the artifact root (for example
            "analysis" or "metrics"). Must not be absolute or escape the
            root with `..`.

    Returns:
        The resolved absolute Path of the created `<root>/<subdir>`.

    Raises:
        ValueError: When subdir is empty, absolute, or contains `..`.
        OSError: When the directory cannot be created.
    """
    if not str(subdir).strip():
        raise ValueError("subdir must be non-empty")
    sub = _normalize_relpath(subdir)

    override = os.environ.get("AI_AGENTS_ARTIFACT_ROOT")
    if override and override.strip():
        root = Path(override).expanduser()
    else:
        root = Path.cwd() / ".agents"

    target = (root / sub).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return target
