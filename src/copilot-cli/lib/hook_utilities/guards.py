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

from .utilities import get_project_directory

# The internal guards (LSP-first, skill-first, session protocol) must run only
# in the ai-agents project repository, never in a consumer repo that vendors the
# plugin. Repository identity is authoritative from the git origin remote, not
# from incidental on-disk files: a consumer repo may keep its own .agents/
# directory for unrelated tooling, which the previous .agents/-presence check
# mistook for the project repo and so denied ordinary tool calls (issue #2610).
# The remote must match owner AND name: a name-only match let ``acme/ai-agents``
# pass as the project repo (issue #7227).
_PROJECT_REPO_SLUG = "rjmurillo/ai-agents"
# The pyproject.toml fallback has no remote, so it can only match the bare name.
_PROJECT_REPO_NAME = "ai-agents"

# Override and cache hook. "1" forces project-repo behavior, "0" forces
# consumer-repo behavior; any other value falls through to the git lookup. Tests
# and CI set it directly, and a one-time remote lookup can persist it here.
_PROJECT_REPO_ENV = "AI_AGENTS_PROJECT_REPO"

# Per-root, per-process memo so the Copilot in-process dispatcher (every shim in
# one interpreter, ADR-068) pays the git lookup at most once per repository root.
RepoIdentity = Literal["project", "consumer", "unknown"]
_origin_repo_cache: dict[str, RepoIdentity] = {}


def _repo_slug(url: str) -> str | None:
    """Return ``owner/name`` (lowercase) from a git remote URL, or None.

    Handles ``https://host/owner/name.git``, ``git@host:owner/name.git``, and
    ``ssh://git@host/owner/name.git``. A URL with no owner segment yields None.
    """
    path = url.strip().rstrip("/").replace("\\", "/")
    if "://" in path:
        after_scheme = path.split("://", 1)[1]
        path = after_scheme.split("/", 1)[1] if "/" in after_scheme else ""
    elif ":" in path:
        path = path.rsplit(":", 1)[-1]
    if path.endswith(".git"):
        path = path[:-4]
    parts = [part for part in path.split("/") if part]
    if len(parts) < 2:
        return None
    return f"{parts[-2]}/{parts[-1]}".lower()


def _remote_urls(project_root: str) -> dict[str, str] | None:
    """Return fetch URLs keyed by remote name, or None when git cannot answer.

    One ``git remote -v`` call reads ``origin`` and ``upstream`` together, so the
    lookup stays a single subprocess under the host hook budget.
    """
    git = shutil.which("git")
    if git is None:
        return None
    try:
        result = subprocess.run(
            [git, "-C", project_root, "remote", "-v"],
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
            # A local `git remote -v` reads .git/config in <10ms;
            # 1s only trips on a genuine hang, which is exactly when we want to
            # degrade fast. Enforced by tests/test_hook_plugin_guards.py::
            # test_origin_lookup_timeout_under_host_budget.
            timeout=1,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    urls: dict[str, str] = {}
    for line in result.stdout.splitlines():
        name, separator, rest = line.partition("\t")
        if not separator or not rest.endswith("(fetch)"):
            continue
        url = rest[: -len("(fetch)")].strip()
        if name and url and name not in urls:
            urls[name] = url
    return urls


def _project_remote_identity(project_root: str) -> RepoIdentity:
    """Classify a checkout from its ``origin`` (and, for forks, ``upstream``).

    ``origin`` must be ``rjmurillo/ai-agents``. A contributor's fork has an
    ``origin`` under their own account, so a remote named ``upstream`` that
    points at the project repo also qualifies. No usable ``origin`` is
    "unknown" so the caller can fail open outside the project.
    """
    urls = _remote_urls(project_root)
    origin = urls.get("origin") if urls else None
    slug = _repo_slug(origin) if origin else None
    if slug is None:
        return "unknown"
    if slug == _PROJECT_REPO_SLUG:
        return "project"
    upstream = urls.get("upstream") if urls else None
    if upstream and _repo_slug(upstream) == _PROJECT_REPO_SLUG:
        return "project"
    return "consumer"


def _project_repo_identity() -> RepoIdentity:
    """Resolve whether the current checkout is project, consumer, or unknown."""
    override = os.environ.get(_PROJECT_REPO_ENV, "").strip()
    if override == "1":
        return "project"
    if override == "0":
        return "consumer"

    project_root = get_project_directory()
    if project_root not in _origin_repo_cache:
        _origin_repo_cache[project_root] = _project_remote_identity(project_root)
    return _origin_repo_cache[project_root]


def is_project_repo() -> bool:
    """Return True when running inside the rjmurillo/ai-agents project repository.

    Identity comes from the git origin remote (authoritative; a fork also
    qualifies through an ``upstream`` remote), not from
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
