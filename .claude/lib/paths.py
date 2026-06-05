"""Vendor-portable path resolution for skill scripts (Issue #2050).

Skills that ship in a vendored plugin install (Copilot CLI and similar
harnesses) cannot assume the consumer repo has a `.claude/` directory or
the upstream `.agents/` tree. This module centralizes the two resolution
policies every skill needs so no script hard-codes an upstream-only path.

Two policies:

- `resolve_skill_resource(skill, relpath)` is the READ path. It locates a
  file that ships inside the plugin (a reference doc, a helper script). This
  helper uses this local candidate order:
    1. `${COPILOT_PLUGIN_ROOT}/skills/<skill>/<relpath>` or
       `${CLAUDE_PLUGIN_ROOT}/skills/<skill>/<relpath>` when set by the harness.
    2. `.claude/skills/<skill>/<relpath>` resolved from the current working
       directory (Claude Code project layout).
    3. `skills/<skill>/<relpath>` resolved relative to the plugin install
       root discovered by walking up from this file to the
       `.claude-plugin/plugin.json` marker (vendored install).
  Returns the first candidate that exists, else None. Read-only: it never
  creates anything.

- `resolve_artifact_root(subdir, base=None)` is the WRITE path. Skills write
  artifacts to a consumer-side location, defaulting to `<cwd>/.agents/<subdir>`.
  The directory is created lazily (parents=True, exist_ok=True). A caller that
  already knows the repository root (for example a session script that resolved
  it from git) passes it as `base` so the artifact anchors at
  `<base>/.agents/<subdir>` instead of the current working directory. The root
  is overridable by the `AI_AGENTS_ARTIFACT_ROOT` environment variable so a
  consumer can redirect every skill's output to one place; the override wins
  over both `base` and the cwd default.

Relationship to existing skills:
  The read path uses a three-location fallback like `/review`, but the
  environment variable and concrete resource paths are local to this helper.
  `/review` documents `CLAUDE_SKILL_DIR` for its first candidate. This helper
  uses `COPILOT_PLUGIN_ROOT` or `CLAUDE_PLUGIN_ROOT` because packaged plugin
  installs expose the plugin root, not one skill directory. The write path is
  new (the `/review` skill has no write artifact), modeled on `/spec` Step 0 writing
  `.agents/metrics/STEP-0-METRICS.md` lazily under the consumer cwd. The
  AI_AGENTS_ARTIFACT_ROOT override is added so the consumer, not the skill,
  owns the artifact location.

Related sources: `.claude/skills/review/SKILL.md`, section "Path resolution
(harness-agnostic)". Plugin-root marker reuse:
`.claude/lib/bootstrap.py::resolve_plugin_lib_dir` (CLAUDE_PLUGIN_ROOT then
the `.claude-plugin/plugin.json` walk-up). This file is a sibling write-path
resolver to that read-path resolver per the Issue #2050 batch decision.
"""

from __future__ import annotations

import os
from pathlib import Path

_PLUGIN_MARKER = Path(".claude-plugin") / "plugin.json"


def _plugin_root_env() -> str | None:
    """Return the harness-provided plugin root, if any."""
    return os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT")


def _plugin_install_root() -> Path | None:
    """Return the marker-discovered plugin install root, or None."""
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
    if str(rel) == ".":
        raise ValueError(f"relpath must not be empty or '.': {relpath!r}")
    if rel.is_absolute():
        raise ValueError(f"relpath must be relative, got absolute: {relpath!r}")
    if ".." in rel.parts:
        raise ValueError(f"relpath must not contain '..': {relpath!r}")
    return rel


def _normalize_skill_name(skill: str) -> str:
    """Reject skill names that escape the skills directory."""
    name = skill.strip()
    if not name:
        raise ValueError("skill must be a non-empty name")
    rel = _normalize_relpath(name)
    if len(rel.parts) != 1:
        raise ValueError("skill must be a single directory name")
    return rel.as_posix()


def resolve_skill_resource(skill: str, relpath: str | Path) -> Path | None:
    """Resolve a read-only resource shipped inside a skill.

    Tries each candidate in order and returns the first that exists:
      1. `${COPILOT_PLUGIN_ROOT}/skills/<skill>/<relpath>` or
         `${CLAUDE_PLUGIN_ROOT}/skills/<skill>/<relpath>`
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
    skill_name = _normalize_skill_name(skill)
    rel = _normalize_relpath(relpath)

    candidates: list[Path] = []

    plugin_env = _plugin_root_env()
    if plugin_env:
        candidates.append(Path(plugin_env).resolve() / "skills" / skill_name / rel)

    candidates.append(Path.cwd() / ".claude" / "skills" / skill_name / rel)

    install_root = _plugin_install_root()
    if install_root is not None:
        candidates.append(install_root / "skills" / skill_name / rel)

    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()

    return None


def resolve_artifact_root(subdir: str | Path, base: str | Path | None = None) -> Path:
    """Resolve and create the write directory for a skill artifact.

    The default root is `<cwd>/.agents`. A caller that already knows the
    repository root passes it as `base` so the root becomes `<base>/.agents`.
    Both are overridden by the `AI_AGENTS_ARTIFACT_ROOT` environment variable,
    which a consumer sets to redirect every skill's output to one place. The
    returned directory (`<root>/<subdir>`) is created lazily with parents.

    Args:
        subdir: Artifact subdirectory under the artifact root (for example
            "analysis" or "metrics"). Must not be absolute or escape the
            root with `..`.
        base: Optional base directory whose `.agents` subdirectory anchors the
            artifact root. Defaults to the current working directory. The
            `AI_AGENTS_ARTIFACT_ROOT` override, when set, takes precedence.

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
    elif base is not None:
        root = Path(base).expanduser() / ".agents"
    else:
        root = Path.cwd() / ".agents"

    target = (root / sub).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return target
