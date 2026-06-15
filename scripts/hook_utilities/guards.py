"""Plugin-mode guards for hook scripts."""

import os
import shutil
import subprocess
import sys

from scripts.hook_utilities.utilities import get_project_directory

# The internal guards (LSP-first, skill-first, session protocol) must run only
# in the ai-agents project repository, never in a consumer repo that vendors the
# plugin. Repository identity is authoritative from the git origin remote, not
# from incidental on-disk files: a consumer repo may keep its own .agents/
# directory for unrelated tooling, which the previous .agents/-presence check
# mistook for the project repo and so denied ordinary tool calls (issue #2610).
_PROJECT_REPO_NAME = "ai-agents"

# Override and cache hook. "1" forces project-repo behavior, "0" forces
# consumer-repo behavior; any other value falls through to the git lookup. Tests
# and CI set it directly, and a one-time remote lookup can persist it here.
_PROJECT_REPO_ENV = "AI_AGENTS_PROJECT_REPO"

# Per-root, per-process memo so the Copilot in-process dispatcher (every shim in
# one interpreter, ADR-068) pays the git lookup at most once per repository root.
_origin_repo_cache: dict[str, bool] = {}


def _remote_repo_name(project_root: str) -> str | None:
    """Return the origin remote's repository name, or None when unavailable.

    Parses both HTTPS (``https://host/owner/ai-agents.git``) and SSH
    (``git@host:owner/ai-agents.git``) forms. Any failure (git missing, no
    origin, timeout) yields None so the caller treats the repo as a consumer.
    """
    git = shutil.which("git")
    if git is None:
        return None
    try:
        result = subprocess.run(
            [git, "-C", project_root, "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    url = result.stdout.strip()
    if not url:
        return None
    # Repository name is the last path segment, minus an optional ".git".
    tail = url.rstrip("/").replace("\\", "/").rsplit("/", 1)[-1]
    tail = tail.rsplit(":", 1)[-1]  # bare SSH "host:repo" with no owner segment
    if tail.endswith(".git"):
        tail = tail[:-4]
    return tail or None


def is_project_repo() -> bool:
    """Return True when running inside the ai-agents project repository.

    Identity comes from the git origin remote (authoritative), not from
    incidental on-disk files. The AI_AGENTS_PROJECT_REPO environment variable
    overrides the lookup ("1"/"0") and caches a one-time resolution; tests set
    it directly. Uses get_project_directory() so it works from a subdirectory.
    """
    override = os.environ.get(_PROJECT_REPO_ENV, "").strip()
    if override in ("0", "1"):
        return override == "1"
    project_root = get_project_directory()
    if project_root not in _origin_repo_cache:
        name = _remote_repo_name(project_root)
        if name is None:
            return False
        _origin_repo_cache[project_root] = name.lower() == _PROJECT_REPO_NAME
    return _origin_repo_cache[project_root]


def skip_if_consumer_repo(hook_name: str) -> bool:
    """Print skip message and return True if this is a consumer repo."""
    if not is_project_repo():
        print(
            f"[SKIP] {hook_name}: not the ai-agents project repo (consumer repo)",
            file=sys.stderr,
        )
        return True
    return False
