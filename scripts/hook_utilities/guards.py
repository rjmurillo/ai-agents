"""Plugin-mode guards for hook scripts."""

import json
import os
import shutil
import subprocess
import sys
from typing import Literal

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - 3.10 fallback path
    tomllib = None

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
RepoIdentity = Literal["project", "consumer", "unknown"]
_origin_repo_cache: dict[str, RepoIdentity] = {}


def _remote_repo_name(project_root: str) -> str | None:
    """Return the origin remote's repository name, or None when unavailable.

    Parses both HTTPS (``https://host/owner/ai-agents.git``) and SSH
    (``git@host:owner/ai-agents.git``) forms. Any failure (git missing, no
    origin, timeout) yields None so the caller can fail open outside the project.
    """
    git = shutil.which("git")
    if git is None:
        return None
    try:
        result = subprocess.run(
            [git, "-C", project_root, "remote", "get-url", "origin"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            # skip_if_consumer_repo() runs this on every tool use. The tightest
            # host hook timeout that invokes it is 2s (topical-memory-injection
            # in .claude/settings.json), so keep this subprocess timeout strictly
            # below that: a slow or hung git must degrade to None here, not let
            # the host SIGKILL the whole hook. A SIGKILL cannot be caught by the
            # caller's fail-open try/except, so it surfaces as a hard "hook
            # errored" deny of the command (repo-settings Bash-hook wedge RCA).
            # A local `git remote get-url origin` reads .git/config in <10ms;
            # 1s only trips on a genuine hang, which is exactly when we want to
            # degrade fast. Enforced by tests/test_hook_plugin_guards.py::
            # test_origin_lookup_timeout_under_host_budget.
            timeout=1,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
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


def _project_repo_identity() -> RepoIdentity:
    """Resolve whether the current checkout is project, consumer, or unknown."""
    override = os.environ.get(_PROJECT_REPO_ENV, "").strip()
    if override == "1":
        return "project"
    if override == "0":
        return "consumer"

    project_root = get_project_directory()
    if project_root not in _origin_repo_cache:
        name = _remote_repo_name(project_root)
        if name is None:
            _origin_repo_cache[project_root] = "unknown"
        elif name.lower() == _PROJECT_REPO_NAME:
            _origin_repo_cache[project_root] = "project"
        else:
            _origin_repo_cache[project_root] = "consumer"
    return _origin_repo_cache[project_root]


def is_project_repo() -> bool:
    """Return True when running inside the ai-agents project repository.

    Identity comes from the git origin remote (authoritative), not from
    incidental on-disk files. The AI_AGENTS_PROJECT_REPO environment variable
    overrides the lookup ("1"/"0") and caches a one-time resolution; tests set
    it directly. Uses get_project_directory() so it works from a subdirectory.
    """
    return _project_repo_identity() == "project"


def _project_repo_corroborated(project_root: str) -> bool:
    """Second cheap signal that ``project_root`` is the ai-agents project repo.

    Used only when the git origin remote is unavailable (identity "unknown").
    Reads ``pyproject.toml``'s ``[project].name``: the ai-agents project repo
    declares ``name = "ai-agents"`` (verified in the repo-root pyproject.toml),
    while a consumer repo that vendors the plugin declares its own name, so this
    stays False there. A missing file, unavailable tomllib (Python 3.10), or a
    parse error yields False so the caller still fails open outside the project.
    """
    if tomllib is None:
        return False
    pyproject = os.path.join(project_root, "pyproject.toml")
    try:
        with open(pyproject, "rb") as handle:
            data = tomllib.load(handle)
    except (OSError, ValueError):
        return False
    project = data.get("project")
    if not isinstance(project, dict):
        return False
    name = project.get("name")
    return isinstance(name, str) and name.strip().lower() == _PROJECT_REPO_NAME


def _emit_skip_event(hook_name: str, reason: str, detail: str) -> None:
    """Emit a structured ``EVENT=...`` line when an unknown-identity checkout
    skips every internal guard, so a silent whole-surface fail-open is
    observable in telemetry.

    Mirrors the fail-open EVENT shape emitted by
    ``.claude/hooks/PreToolUse/push_guard_base.py::_emit_fail_open``:
        event = {
            "guard": name,
            "code": f"E_{code}",
            "outcome": "fail_open",
            "reason": reason,
            "detail": detail,
        }
        print(f"EVENT={json.dumps(event, separators=(',', ':'))}", file=sys.stderr)
    """
    code = hook_name.upper().replace("-", "_")
    event = {
        "guard": hook_name,
        "code": f"E_{code}",
        "outcome": "fail_open",
        "reason": reason,
        "detail": detail,
    }
    print(f"EVENT={json.dumps(event, separators=(',', ':'))}", file=sys.stderr)


def skip_if_consumer_repo(hook_name: str) -> bool:
    """Print skip message and return True unless this is confirmed project repo."""
    identity = _project_repo_identity()
    if identity == "consumer":
        print(
            f"[SKIP] {hook_name}: not the ai-agents project repo (consumer repo)",
            file=sys.stderr,
        )
        return True
    if identity == "unknown":
        # Git origin is unavailable, so identity is indeterminate. Before
        # skipping every internal guard (a silent whole-surface fail-open),
        # corroborate with a second cheap signal: pyproject.toml's
        # [project].name. Only the ai-agents project repo declares that name,
        # so a consumer repo that vendors the plugin still skips here.
        if _project_repo_corroborated(get_project_directory()):
            return False
        _emit_skip_event(
            hook_name,
            "identity_unknown",
            "git origin unavailable and pyproject name corroboration absent",
        )
        print(
            f"[SKIP] {hook_name}: cannot verify ai-agents project repo identity; "
            "treating as consumer repo",
            file=sys.stderr,
        )
        return True
    return False
