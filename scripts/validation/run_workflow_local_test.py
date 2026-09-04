#!/usr/bin/env python3
"""Local-run gate for changed GitHub Actions workflows (ADR-006 module).

Policy (Issue tracked in PR): a changed file under ``.github/workflows/`` MUST
be exercised locally and pass before the push is allowed. The pre-push hook and
the pre-PR runner delegate here so the YAML stays out of shell logic and the
behavior is unit-tested.

Belt-and-suspenders, three ordered stages per the repository owner's decision.
Stages run in order and short-circuit on the first failure:

    1. actionlint            static analysis (syntax, action refs, exprs)
    2. gh act -n             dry-run: job graph, step wiring, resolvable uses
    3. gh act (full)         real execution in Docker

Why all three: actionlint catches what never reaches a runner; the dry-run
catches graph/wiring errors without spending minutes; the full run catches
logic that only fails at execution time (the class of defect that slipped
through static checks in PR #2120's CI runner).

Tool / environment gaps are reported, not silently skipped: a missing
actionlint, gh act, or Docker daemon yields exit 3 (external) so the caller can
block with an actionable message. A documented bypass exists for workflows that
genuinely cannot run under act (secrets, ARM-only runners): set
``SKIP_WORKFLOW_LOCAL_TEST=true``; the bypass is logged, not hidden.

Tool gaps degrade instead of blocking where the developer may not be able to
provision the tool: when actionlint, ``gh``, the ``gh act`` extension, or the
Docker daemon is unavailable and ``CLAUDECODE`` or ``CODESPACES`` is set, the
gate returns exit 0 with ``degraded=True`` and a logged warning. Such a session
may not be able to install those tools, so blocking every workflow-touching push
there is friction, not safety. A truthy ``CI`` marker overrides both env
markers, so CI, where the tools are provisioned, keeps the hard exit 3. With
neither marker set the gap also stays exit 3, so the local-run requirement is
unchanged on a dev laptop. Issue #2548 item 3 introduced this degrade for the
``gh``/``gh act`` gap; Issue #3064 extended it to the actionlint and Docker gaps
so a session without those tools can still push a workflow edit.

That degrade reads env markers only, in :func:`_tool_gap_is_environmental`. It
is a different question from "am I inside a container", which
:func:`_is_remote_container` answers from ``CODESPACES``, an image-set marker,
and the filesystem. A container that sets neither env marker keeps the hard exit
3 like any other host, because a tool it can install is not an environment gap.
Issue #5479 has why the two questions stopped sharing one answer.

CLI
---

::

    python3 scripts/validation/run_workflow_local_test.py --files .github/workflows/x.yml
    python3 scripts/validation/run_workflow_local_test.py --files x.yml --no-full
    python3 scripts/validation/run_workflow_local_test.py --files x.yml --format json

EXIT CODES (per ADR-035, exit-code contract in AGENTS.md)
---------------------------------------------------------

0 - all stages passed (or no workflow files, or bypassed)
1 - a stage ran and failed (block the push)
2 - configuration error (bad args, repo root absent)
3 - a required tool is unavailable (actionlint, gh act, or Docker). Under
    ``CLAUDECODE`` or ``CODESPACES`` this gap degrades to exit 0
    (degraded=True) instead, because the tool may not be provisionable there;
    CI and a plain dev laptop keep the hard exit 3 (Issue #3064, #5479)
4 - unrunnable locally: actionlint passed but every changed workflow
    references a secret absent from this environment, so act has nothing to
    supply (auth per ADR-035). Skipped the act run audibly; CI runs it with the
    real secrets (Issue #2841).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

_BYPASS_ENV = "SKIP_WORKFLOW_LOCAL_TEST"

# Truthy values for the bypass env. Matches the repo convention for boolean
# env flags (see REVIEW_MARKER_ENFORCED in scripts/validation/checks_coverage.py,
# which accepts "1" and "true").
_TRUTHY = {"1", "true"}

# Env markers that say the developer may not be able to provision ``gh act``.
# Observed on Claude web containers and the Claude Code CLI, which both set
# ``CLAUDECODE``, and on GitHub Codespaces. Where one is set a missing ``gh
# act`` is an environment gap, not a code defect, so the gate degrades to a
# logged warning instead of blocking the push (Issue #2548, item 3). The same
# gate keeps its hard failure in CI, where ``gh act`` is provisioned: the ``CI``
# marker (set to a truthy value by GitHub Actions) overrides these in
# :func:`_tool_gap_is_environmental`.
#
# This tuple is about tool provisioning only. It is NOT evidence of a container,
# and until Issue #5479 it was read as both: ``CLAUDECODE`` names the client,
# not the execution environment, and the Claude Code CLI sets it on a laptop, a
# workstation and a VM. Reading it as a container took the semgrep budget in
# ``git_hook_policy`` from 840s to 150s on a workstation, so a branch whose scan
# needs more than 150s could not be pushed from a Claude Code session while the
# same push succeeded from a plain terminal on the same machine. The container
# question now has its own answer in :func:`_is_remote_container`.
_TOOL_GAP_ENV_MARKERS = ("CLAUDECODE", "CODESPACES")
_CI_ENV = "CI"

# ``CODESPACES`` names a managed remote container, so it is a container signal
# as well as a tool-provisioning one. ``CLAUDECODE`` is not, which is the whole
# of Issue #5479.
#
# ``AI_AGENTS_REMOTE_CONTAINER`` is the marker an image sets for itself, which
# is what Issue #5479 asked for in place of borrowing the client's variable. It
# exists because the filesystem probe below is evidence, not a guarantee: a
# runtime that writes no marker file and runs under cgroup v2 (where
# ``/proc/1/cgroup`` is ``0::/`` and names nothing) leaves nothing to read. The
# Claude web container is the class ADR-104 rule 8 was measured against (679s
# push, reclaimed mid-hook) and its filesystem has not been measured here, so an
# image that needs the clamp declares itself instead of being inferred. Setting
# it is the whole install: `ENV AI_AGENTS_REMOTE_CONTAINER=1` in the image, or
# export it in the session's shell profile.
_REMOTE_CONTAINER_ENV_MARKERS = ("CODESPACES", "AI_AGENTS_REMOTE_CONTAINER")

# Files that exist only inside a container: Docker writes ``/.dockerenv`` and
# Podman writes ``/run/.containerenv``.
_CONTAINER_MARKER_FILES = ("/.dockerenv", "/run/.containerenv")
# Under cgroup v1 the init process's cgroup paths name the container runtime.
# cgroup v2 collapses them to ``0::/``, which is why the marker files above
# carry the common cases and this is a supplement rather than the primary test.
#
# ``/proc/self/mountinfo`` is deliberately not consulted, though it carries the
# same hints. On an Ubuntu 6.17 workstation with Docker installed and no
# container running it holds two matching lines, ``/run/docker/netns/default``
# and ``/var/lib/lxcfs``, so it reports a container on a machine that is not
# one. That is the same false positive this function exists to remove.
_CONTAINER_CGROUP_HINTS = ("docker", "containerd", "kubepods", "lxc", "podman")
_CONTAINER_CGROUP_FILE = "/proc/1/cgroup"

# Only GitHub Actions workflow files can run under ``gh act``. Custom actions
# under ``.github/actions/`` and any other path are filtered out before the act
# stages so a caller that over-collects (the pre-push hook globs changed files)
# does not hand a non-runnable path to ``gh act``.
_WORKFLOW_PREFIX = ".github/workflows/"
_WORKFLOW_SUFFIXES = (".yml", ".yaml")

# Per-stage timeouts (seconds). The full act run pulls images and executes
# composite actions, so it gets the largest budget.
#
# The dry run gets the same budget as the full run because ``act`` clones every
# referenced action into ``~/.cache/act`` before it can plan the graph, and that
# cache is keyed by action ref, not by workflow. Planning itself is cheap: on a
# warm cache ``gh act -n -W .github/workflows/codeql-analysis.yml`` returns rc=0
# in 17s. On an empty cache the same command was still cloning at 130s with 787M
# pulled and 8 ``git clone`` lines emitted, so the old 120s budget killed a
# correct workflow and reported a bare ``TimeoutExpired`` (Issue #3949). A
# Renovate digest bump re-cold-starts one action at a time, so this is not a
# once-per-machine cost.
_ACTIONLINT_TIMEOUT = 60
_ACT_FULL_TIMEOUT = 600
_ACT_DRYRUN_TIMEOUT = _ACT_FULL_TIMEOUT
_PYTEST_WORKFLOW = ".github/workflows/pytest.yml"

# actionlint shells out to shellcheck for ``run:`` scripts. The info and style
# tiers are advisory (SC2086 quoting advice, SC2129 grouped redirects) and are
# not defects in a given change; on a clean checkout they produced 100+ findings
# across untouched workflows and turned this gate red on baseline (Issue #2374).
# Raise the shellcheck severity floor to ``warning`` so only ``warning`` and
# ``error`` findings block. This keeps the gate consistent with
# ``scripts/validation/pre_pr.py:validate_workflow_yaml``, which applies the same
# floor; real bugs (SC2034 unused variable, SC2068 unquoted array) still fail.
_SHELLCHECK_SEVERITY = "--severity=warning"


def _shellcheck_env() -> dict[str, str]:
    """Child env that raises the shellcheck severity floor to ``warning``.

    Merges with the current ``SHELLCHECK_OPTS`` so an operator-set option (for
    example ``--exclude=SC1091``) is preserved alongside the severity floor.
    """
    env = dict(os.environ)
    existing = env.get("SHELLCHECK_OPTS", "").strip()
    env["SHELLCHECK_OPTS"] = (
        f"{existing} {_SHELLCHECK_SEVERITY}".strip() if existing else _SHELLCHECK_SEVERITY
    )
    return env


@dataclass
class StageResult:
    """Outcome of one stage for one (or all) workflow file(s)."""

    stage: str
    ok: bool
    detail: str = ""


@dataclass
class Report:
    """Aggregate result. ``exit_code`` follows the module contract."""

    exit_code: int
    stages: list[StageResult] = field(default_factory=list)
    bypassed: bool = False
    degraded: bool = False
    secret_skipped: bool = False
    note: str = ""


# --- Tool detection (mockable seams) -------------------------------------


def _have(tool: str) -> bool:
    return shutil.which(tool) is not None


def _docker_ready() -> bool:
    """True when a Docker daemon answers. ``gh act`` cannot run without it."""
    rc, _, _ = _run(["docker", "info"], timeout=20)
    return rc == 0


def _gh_act_available() -> bool:
    """True when the ``gh act`` extension is installed."""
    rc, _, _ = _run(["gh", "act", "--help"], timeout=20)
    return rc == 0


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUTHY


def _has_container_filesystem_signal() -> bool:
    """True when the filesystem says this process is inside a container.

    Total and cheap: two ``stat`` calls and one small read, no subprocess, and
    no error escapes (``Path.exists`` already answers False rather than raising
    on an unreadable path). It runs once per clamped subprocess in
    ``git_hook_policy``, which is orders of magnitude cheaper than the spawn it
    bounds, so nothing here is cached and no invalidation problem exists. On a
    host without these paths (Windows, macOS) it returns False without raising.
    """
    if any(Path(marker).exists() for marker in _CONTAINER_MARKER_FILES):
        return True
    try:
        cgroups = Path(_CONTAINER_CGROUP_FILE).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    lowered = cgroups.lower()
    return any(hint in lowered for hint in _CONTAINER_CGROUP_HINTS)


def _is_remote_container() -> bool:
    """True when this process really is running inside a container.

    A truthy ``CI`` marker overrides every container signal: CI provisions the
    tools and a real hang there is a real failure, so it must keep failing the
    way CI expects. Outside CI the answer comes from ``CODESPACES``, from an
    image that declares itself with ``AI_AGENTS_REMOTE_CONTAINER``, or from the
    filesystem, never from a variable that names the client rather than the
    environment (Issue #5479).

    The filesystem probe is the fallback and not the guarantee: it reads real
    evidence, so it answers False on a runtime that writes no marker file and
    reports ``0::/`` under cgroup v2. An image whose reclamation bound must hold
    sets ``AI_AGENTS_REMOTE_CONTAINER`` rather than relying on being inferred.

    Callers use this to decide whether the environment can end the process out
    from under them: ``git_hook_policy._container_clamped`` and
    ``_arm_container_watchdog`` both bound work against container reclamation.
    A false positive there is a hard stop, not a warning, which is why this is
    the strict predicate and :func:`_tool_gap_is_environmental` is the loose one.
    """
    if _env_truthy(_CI_ENV):
        return False
    if any(_env_truthy(marker) for marker in _REMOTE_CONTAINER_ENV_MARKERS):
        return True
    return _has_container_filesystem_signal()


def _tool_gap_is_environmental() -> bool:
    """True where a missing local tool is the environment, not a code defect.

    Deliberately wider than :func:`_is_remote_container`. This one only decides
    whether a missing ``gh``, ``gh act``, ``actionlint`` or Docker daemon
    degrades to a warning instead of blocking the push (Issue #2548, item 3),
    and firing too widely costs a warning. The container predicate cuts
    subprocess budgets, and firing too widely there costs a push that cannot
    complete at all, so the two questions get two answers.
    """
    if _env_truthy(_CI_ENV):
        return False
    return any(_env_truthy(marker) for marker in _TOOL_GAP_ENV_MARKERS)


def _decode_partial(raw: bytes | str | None) -> str:
    """Decode the partial output carried on a ``TimeoutExpired``.

    ``subprocess`` builds the exception from the raw pipe buffers before the
    text-mode decoder runs, so the attributes arrive as ``bytes`` even when the
    call passed ``text=True``, and they are ``None`` when the child wrote
    nothing. Match the decoding ``_run`` asks ``subprocess.run`` for
    (``encoding="utf-8"``, ``errors="replace"``) so a timed-out run and a
    completed one read the same.
    """
    if raw is None:
        return ""
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    return raw


def _killpg_safe(pid: int) -> None:
    """Send SIGTERM then SIGKILL to the process group containing ``pid``.

    Uses SIGTERM first (giving the group a chance to clean up open ports such
    as the gh-act artifact server), then SIGKILL after a short grace window.
    Guards against signalling the current process group when ``setsid`` did not
    fire (Windows, or a failed exec where the child reuses our PGID).
    """
    try:
        pgid = os.getpgid(pid)
    except OSError:
        return
    if pgid == os.getpgid(0):
        return
    try:
        os.killpg(pgid, signal.SIGTERM)
    except OSError:
        pass
    try:
        os.killpg(pgid, signal.SIGKILL)
    except OSError:
        pass


def _run(
    cmd: list[str],
    *,
    timeout: int,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    """Run a command. Returns (exit_code, stdout, stderr); -1 on spawn error.

    When ``env`` is provided it replaces the child environment entirely, so a
    caller that only wants to add a variable should merge it with
    ``os.environ`` first.

    On timeout the whole process group is killed, not just the direct child.
    This matters for ``gh act``: the gh-act artifact server is a grandchild of
    gh, so a ``proc.kill()`` leaves it holding port 34567 and every later
    invocation fails with "address already in use" (Issue #3948).
    """
    _supports_pgroup = hasattr(os, "killpg")
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd) if cwd else None,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
            start_new_session=_supports_pgroup,
        )
    except FileNotFoundError:
        return -1, "", f"command not found: {cmd[0]}"
    except OSError as exc:
        return -1, "", f"{type(exc).__name__}: {exc}"
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        # Kill the full process group so grandchildren (gh-act artifact server)
        # do not survive to hold ports open (Issue #3948).
        if _supports_pgroup:
            _killpg_safe(proc.pid)
        else:
            proc.kill()
        # Collect whatever the child had written before we killed it. The act
        # stage reads this to distinguish a cold-cache run from a slow one
        # (Issue #3949).
        stdout_raw, stderr_raw = proc.communicate()
        out = _decode_partial(exc.stdout) or stdout_raw
        err_head = f"{type(exc).__name__}: {exc}\n{_decode_partial(exc.stderr) or stderr_raw}"
        return -1, out, err_head.rstrip()
    except BaseException:
        if _supports_pgroup:
            _killpg_safe(proc.pid)
        else:
            proc.kill()
        proc.communicate()
        raise
    return proc.returncode, stdout, stderr


def _read_worktree_gitdir(repo_root: Path) -> str | None:
    """Return the absolute GIT_DIR for a LINKED worktree, else None.

    In a linked worktree ``<repo_root>/.git`` is a FILE containing
    ``gitdir: <path>`` that points at the per-worktree admin directory under
    the main checkout's ``.git/worktrees/<name>``. ``gh act`` runs with
    ``cwd=repo_root`` and cannot follow that pointer itself, so it fails to
    find the git metadata (#2344). Returns the resolved absolute gitdir, or
    None when ``.git`` is a normal directory or the pointer is unreadable.
    """
    git_path = repo_root / ".git"
    if not git_path.is_file():
        return None
    try:
        content = git_path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not content.startswith("gitdir:"):
        return None
    pointer = content.split(":", 1)[1].strip()
    if not pointer:
        return None
    gitdir = Path(pointer)
    if not gitdir.is_absolute():
        gitdir = (repo_root / gitdir).resolve()
    else:
        gitdir = gitdir.resolve()
    return str(gitdir)


def _unsupported_worktree_gitdir_error(repo_root: Path) -> str | None:
    git_path = repo_root / ".git"
    if not git_path.is_file():
        return None
    try:
        content = git_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        return (
            f"linked git worktree marker is unreadable: {git_path} ({exc}). "
            f"Re-run from the main worktree or set {_BYPASS_ENV}=true to bypass (logged)."
        )
    if not content.startswith("gitdir:") or not content.split(":", 1)[1].strip():
        return (
            f"unsupported linked git worktree marker at {git_path}; expected "
            f"'gitdir: <path>'. Re-run from the main worktree or set {_BYPASS_ENV}=true "
            "to bypass (logged)."
        )
    gitdir = _read_worktree_gitdir(repo_root)
    if gitdir is None or not Path(gitdir).is_dir():
        return (
            f"linked git worktree gitdir is missing: {gitdir or '<unresolved>'}. "
            f"Re-run from the main worktree or set {_BYPASS_ENV}=true to bypass (logged)."
        )
    return None


def _act_env(repo_root: Path) -> dict[str, str]:
    """Build the subprocess env for gh act, GIT_DIR-aware for linked worktrees."""
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in {"GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE"}
    }
    gitdir = _read_worktree_gitdir(repo_root)
    if gitdir is not None:
        env["GIT_DIR"] = gitdir
    return env


def _select_workflow_files(
    workflow_files: Sequence[str], repo_root: Path
) -> tuple[list[str], str | None]:
    """Resolve, contain, and filter the candidate files.

    Returns ``(files, error)``. ``files`` are repo-relative workflow paths safe
    to hand to ``actionlint`` and ``gh act``. ``error`` is non-None when a path
    escapes ``repo_root`` (CWE-22 path traversal); the caller maps that to a
    configuration error (exit 2).

    Containment uses ``Path.resolve()`` + ``is_relative_to`` rather than a
    string prefix check, so symlinks and ``..`` segments cannot smuggle a path
    outside the repository. Non-workflow paths (custom actions, unrelated YAML)
    are dropped silently because only ``.github/workflows`` files run under act.
    """
    root = repo_root.resolve()
    selected: list[str] = []
    for candidate in workflow_files:
        if not candidate:
            continue
        resolved = (root / candidate).resolve()
        if not resolved.is_relative_to(root):
            return [], f"path escapes repository root: {candidate}"
        rel = resolved.relative_to(root).as_posix()
        if rel.startswith(_WORKFLOW_PREFIX) and rel.endswith(_WORKFLOW_SUFFIXES):
            selected.append(rel)
    return selected, None


# --- Secret availability -------------------------------------------------

# GitHub secret references appear as ``${{ secrets.NAME }}`` in workflow YAML.
# act cannot supply a secret the developer does not have locally, so a changed
# workflow that references an absent secret cannot run under act. Forcing a
# manual bypass for that case is the friction this gate removes (Issue #2841).
# Names follow GitHub's rule: a letter or ``_`` followed by word characters.
# Match only inside ``${{ ... }}`` expressions: ``secrets.FOO`` in a comment or
# a plain string is not a real secret reference and must not block the run.
_EXPR_RE = re.compile(r"\$\{\{(.*?)\}\}", re.DOTALL)
_SECRET_REF_RE = re.compile(r"\bsecrets\.([A-Za-z_][A-Za-z0-9_]*)")

# act reads secrets from a repo-root ``.secrets`` file (dotenv ``KEY=VALUE``) by
# default, in addition to the process environment. A secret defined there is
# runnable locally, so it does not count as "missing".
_ACT_SECRET_FILE = ".secrets"
_ACT_BUILTIN_SECRETS = {"GITHUB_TOKEN"}


def _has_secret_value(value: str) -> bool:
    """Return true when a local secret value can supply act."""
    stripped = value.strip()
    if not stripped:
        return False
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {"'", '"'}:
        return bool(stripped[1:-1].strip())
    return True


def _act_secret_file_keys(repo_root: Path) -> set[str]:
    """Secret names defined in the act default secret file (repo-root .secrets).

    Parsed as dotenv: ``KEY=VALUE`` per line; ``#`` comments and blank lines are
    ignored. A missing or unreadable file yields an empty set (no secrets
    supplied from disk).
    """
    keys: set[str] = set()
    try:
        text = (repo_root / _ACT_SECRET_FILE).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return keys
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if key and _has_secret_value(value):
            keys.add(key.upper())
    return keys


def _referenced_secrets(path: Path) -> set[str]:
    """Secret names a workflow file references via ``${{ secrets.NAME }}``.

    An unreadable file yields an empty set. Fail-open here is safe: the act
    stages still run and fail closed, so a file we cannot read is treated as
    runnable rather than skipped.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return set()
    refs: set[str] = set()
    for expr in _EXPR_RE.findall(text):
        refs.update(name.upper() for name in _SECRET_REF_RE.findall(expr))
    return refs


def _missing_secrets(path: Path, available: set[str]) -> list[str]:
    """Secrets ``path`` references that are absent from ``available`` (sorted)."""
    return sorted(name for name in _referenced_secrets(path) if name not in available)


# --- Stages --------------------------------------------------------------


def _actionlint_stage(files: Sequence[str], repo_root: Path) -> StageResult:
    rc, out, err = _run(
        ["actionlint", *files],
        timeout=_ACTIONLINT_TIMEOUT,
        cwd=repo_root,
        env=_shellcheck_env(),
    )
    if rc == 0:
        return StageResult("actionlint", True)
    return StageResult("actionlint", False, _with_timeout_hint((out + err).strip()))


# gh act defaults to the ``push`` event. A workflow with no ``push`` trigger
# (for example schedule-only or workflow_dispatch-only) then makes act error
# with "Could not find any stages to run", which used to fail this gate for a
# changed schedule-only workflow even though the workflow is valid
# (Issue #2374). Pick an event the workflow actually declares so act has
# a job graph to walk. Preference order keeps the common PR-style events first.
_ACT_EVENT_PREFERENCE = (
    "push",
    "pull_request",
    "workflow_dispatch",
    "schedule",
    "workflow_call",
)


def _workflow_events(wf_path: Path) -> list[str]:
    """Return the trigger event names declared in a workflow's ``on:`` block.

    Handles the three YAML shapes for ``on``: a scalar (``on: push``), a list
    (``on: [push, pull_request]``), and a map (``on:\\n  push:`` ...). The YAML
    1.1 boolean coercion of the bare key ``on`` to ``True`` is handled by
    checking both ``"on"`` and ``True`` keys. Returns an empty list when the
    file cannot be read or parsed, so the caller falls back to act's default.
    """
    try:
        import yaml
    except ImportError:
        return []
    try:
        data = yaml.safe_load(wf_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return []
    if not isinstance(data, dict):
        return []
    on = data.get("on", data.get(True))
    if isinstance(on, str):
        return [on]
    if isinstance(on, list):
        return [str(e) for e in on]
    if isinstance(on, dict):
        return [str(k) for k in on]
    return []


def _workflow_jobs(wf_path: Path) -> list[str]:
    """Return workflow job ids in file order, or empty when unavailable."""
    try:
        import yaml
    except ImportError:
        return []
    try:
        data = yaml.safe_load(wf_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return []
    if not isinstance(data, dict):
        return []
    jobs = data.get("jobs")
    if not isinstance(jobs, dict):
        return []
    return [str(name) for name in jobs if isinstance(name, str)]


def _pytest_matrix_entries(data: object) -> list[object]:
    """Return the test job's explicit matrix entries."""
    if not isinstance(data, dict):
        return []
    jobs = data.get("jobs")
    if not isinstance(jobs, dict):
        return []
    test_job = jobs.get("test")
    if not isinstance(test_job, dict):
        return []
    strategy = test_job.get("strategy")
    if not isinstance(strategy, dict):
        return []
    matrix = strategy.get("matrix")
    if not isinstance(matrix, dict):
        return []
    includes = matrix.get("include")
    return includes if isinstance(includes, list) else []


def _local_pytest_commands(
    files: Sequence[str], repo_root: Path
) -> tuple[list[tuple[list[str], dict[str, str]]], str]:
    try:
        import yaml
    except ImportError:
        return [], "PyYAML is required for the local fallback"

    commands: list[tuple[list[str], dict[str, str]]] = []
    for rel in files:
        try:
            data = yaml.safe_load((repo_root / rel).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
            return [], f"{rel}: {type(exc).__name__}: {exc}"
        for index, entry in enumerate(_pytest_matrix_entries(data)):
            partition = entry.get("partition") if isinstance(entry, dict) else None
            if not isinstance(partition, str) or not partition.strip():
                continue
            command = [
                "uv",
                "run",
                "--frozen",
                "python",
                "scripts/ci/run_pytest_selected.py",
                "--partition",
                partition,
                "--cov",
                "--cov-report=",
                f"--junitxml=pytest-{index}.xml",
            ]
            commands.append(
                (
                    command,
                    {
                        "COVERAGE_FILE": f".coverage.{index}",
                        "PYTEST_NON_TMP_ROOT": f"pytest-{index}",
                    },
                )
            )
    return commands, ""


def _local_pytest_stage(files: Sequence[str], repo_root: Path) -> StageResult:
    """Run pytest matrix entries directly when already inside act."""
    stage = "gh act (local-fallback)"
    commands, error = _local_pytest_commands(files, repo_root)
    if error:
        return StageResult(stage, False, error)

    if not commands:
        return StageResult(stage, False, "no test matrix partitions found")

    env = dict(os.environ)
    env.pop("ACT", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    plugin_root = str(repo_root / ".claude")
    env["COPILOT_PLUGIN_ROOT"] = plugin_root
    env["CLAUDE_PLUGIN_ROOT"] = plugin_root
    with tempfile.TemporaryDirectory(prefix="ai-agents-pytest-") as temp_root:
        output_root = Path(temp_root)
        for command, partition_env in commands:
            # merge_group forces the selection runner to run the whole partition,
            # so local workflow validation exercises the full matrix rather than
            # an import-graph subset of it.
            command_env = env | {
                "COVERAGE_FILE": str(output_root / partition_env["COVERAGE_FILE"]),
                "PYTEST_NON_TMP_ROOT": str(
                    output_root / partition_env["PYTEST_NON_TMP_ROOT"]
                ),
                "GITHUB_EVENT_NAME": "merge_group",
            }
            for position, token in enumerate(command):
                if token.startswith("--junitxml="):
                    relative = token.removeprefix("--junitxml=")
                    command[position] = f"--junitxml={output_root / relative}"
                    break
            returncode, stdout, stderr = _run(
                command,
                timeout=_ACT_FULL_TIMEOUT,
                cwd=repo_root,
                env=command_env,
            )
            if returncode != 0:
                detail = _with_timeout_hint((stdout + stderr).strip())
                return StageResult(stage, False, detail)
    return StageResult(stage, True)


def _select_act_event(wf_path: Path) -> str | None:
    """Choose an event for ``gh act -n`` based on the workflow's triggers.

    Returns None when ``push`` is declared (act's default needs no override) or
    when no events can be read (let act use its default and report its own
    error). Otherwise returns the highest-preference declared event so act has
    a runnable job graph.
    """
    events = _workflow_events(wf_path)
    if not events or "push" in events:
        return None
    for candidate in _ACT_EVENT_PREFERENCE:
        if candidate in events:
            return candidate
    return events[0]


# Emitted by git (and surfaced through act) when a command runs in a tree with
# no reachable .git. The act container mounts the workflow file but not the host
# .git directory, so git-calling actions such as dorny/paths-filter abort with
# this exact prefix. See issue #2719.
_GIT_REPO_MISSING_PATTERN = "fatal: not a git repository"
# dorny/paths-filter shells out to git through @actions/exec, which annotates a
# nonzero exit as ``::error::The process '<argv0>' failed with exit code N``.
# In the act container the repository arrives through ``docker cp`` without a
# usable .git, so that git call exits 128 and the annotation is the act-only
# limitation one layer up from _GIT_REPO_MISSING_PATTERN.
#
# ``<argv0>`` is not stable across releases of the action. It emitted
# ``git rev-parse --abbrev-ref HEAD`` when this rule was written and emits the
# resolved executable path ``/usr/bin/git`` at digest 61f87a10 (measured
# 2026-08-10 against an unmodified main, so the stale literal blocked every push
# that touched a workflow using the action). Match either shape, still pinned to
# a git executable and to exit code 128, so a genuine action failure with a
# different exit code keeps blocking.
_ACT_GIT_PROCESS_ANNOTATION = re.compile(
    r"::error::The process '(?:[^']*/)?git(?: [^']*)?' failed with exit code 128"
)

# dorny/paths-filter resolves its comparison base from the event payload. On a
# real push or pull_request run GitHub always populates
# ``repository.default_branch``, so this branch is unreachable in CI. act builds
# a synthetic payload that omits it, and the action aborts with this exact text.
# Seen only when the act container CAN reach a .git (otherwise the action fails
# earlier with _GIT_REPO_MISSING_PATTERN instead), which is why a linked
# worktree hits the other pattern and a normal checkout hits this one. See
# issue #3331.
_ACT_PATHS_FILTER_BASE_PATTERN = re.compile(
    r"requires 'base' input to be configured or 'repository\.default_branch' "
    r"to be set in the event payload"
)

# act stages a cached action into the container at /var/run/act/actions/<ref>/
# and copies it with `docker cp`. Recent dockerd rejects that destination with
# "path escapes from parent" before the action's own code runs, so the step
# fails on transport, not on anything the workflow does. Reproduced on an
# unmodified main against .github/workflows/validate-plugin-version-bump.yml,
# so it is independent of any branch. GitHub does not stage actions this way.
_ACT_ACTION_CACHE_COPY_PATTERN = re.compile(
    r"failed to copy content to container: Error response from daemon: "
    r"statat .*?/?var/run/act/actions/.*?: path escapes from parent"
)

_ACT_PR_CONTEXT_MISSING_PATTERN = re.compile(
    r"Cannot read properties of undefined \(reading "
    r"'(?:number|head|base|title|body|labels|draft|merged|user|html_url|state|id"
    r"|assignee|assignees|requested_reviewers|milestone)'\)"
)

# The pull_request context is also consumed indirectly: workflows map
# github.event.pull_request.* into step ``env:`` vars (PR_NUMBER, PR_TITLE) that
# feed validation scripts. act leaves those vars empty on a local run, so the
# scripts fail with their own signatures rather than the JS "Cannot read
# properties of undefined" form above. These are the same act-only limitation,
# event-scoped to pull_request:
#   * PR_TITLE empty  -> parse_pr_standards.py prints "PR_TITLE environment
#     variable is required".
#   * PR_NUMBER empty -> pr_description.py's int("") raises "invalid literal for
#     int() with base 10: ''".
# Under a real pull_request run both env vars are populated, so neither signature
# can arise in CI; downgrading them for pull_request events is safe. See #3265.
_ACT_PR_CONTEXT_EMPTY_ENV_PATTERN = re.compile(
    r"PR_TITLE environment variable is required"
    r"|invalid literal for int\(\) with base 10: ''"
    r"|argument --[A-Za-z0-9-]+: invalid int value: ''"
)

# run_with_retry.py wraps a called script and translates its exit code into an
# ADR-035 annotation. That annotation is derived, not a cause: when the wrapped
# script failed for an attributed act limitation, the wrapper annotation
# describes the same limitation one layer up. Attributing it unconditionally
# would excuse every genuine configuration error, so it is only excused for a
# run that already carries an attributed limitation.
_ACT_WRAPPER_ANNOTATION_PATTERN = re.compile(r"::error::Configuration error \(ADR-035 exit 2\)")

_ACT_SERVER_PORT_BIND_PATTERN = re.compile(r"listen tcp [0-9.]+:\d+: bind: address already in use")

# act embeds its own artifact server, which lags the protobuf schema the current
# actions/upload-artifact client sends. act rejects the body ("unknown field
# mime_type"), the client reads the rejection as malformed JSON, retries, and
# aborts. GitHub's real artifact service accepts the field, so this is
# unreachable in CI.
#
# Anchored on the retry-exhaustion suffix, not on the artifact verb: that suffix
# comes from the @actions/artifact transport retry helper and is emitted only
# when the HTTP conversation itself fails. Artifact *defects* carry different
# text ("No files were found with the provided path", "artifact name is not
# valid") and keep blocking, which is the point of scoping it this way. See
# issue #3690.
_ACT_ARTIFACT_SERVICE_PATTERN = re.compile(
    r"Failed to \w+: Failed to make request after \d+ attempts:"
)

# Workflows that call ``gh api`` or Python scripts that auto-detect the
# repository via ``gh repo view`` (e.g. scripts/github_core/api.py
# resolve_repo_params) fail in act because no GH_TOKEN with real repo context
# is available in the container. In real CI ``github.token`` is always
# populated and the repository is resolvable. The exact message comes from
# scripts/github_core/api.py:resolve_repo_params when every auto-detection
# path is exhausted. See issue #3981.
_ACT_NO_REPO_CONTEXT_PATTERN = (
    "Could not infer repository info. Please provide -Owner and -Repo parameters."
)

# Known act-only limitation signatures. A nonzero act exit whose combined output
# matches one of these rules can be a local environment gap, not a workflow
# defect. The pull_request context rules are event-scoped in _act_limitation_hint;
# every other nonzero exit still blocks.
_ACT_LIMITATION_RULES: tuple[tuple[str | None, Callable[[str], bool], str], ...] = (
    (
        None,
        lambda text: _GIT_REPO_MISSING_PATTERN in text,
        "act container lacks .git; git-calling actions (e.g. dorny/paths-filter) "
        "fail only in local act, not in CI.",
    ),
    (
        None,
        lambda text: (
            _GIT_REPO_MISSING_PATTERN in text
            and bool(_ACT_GIT_PROCESS_ANNOTATION.search(text))
        ),
        "act container cannot resolve the linked-worktree git metadata, so "
        "dorny/paths-filter fails only in local act, not in CI.",
    ),
    (
        None,
        lambda text: bool(_ACT_PATHS_FILTER_BASE_PATTERN.search(text)),
        "act's synthetic event payload omits repository.default_branch, so "
        "dorny/paths-filter cannot resolve a comparison base. GitHub always "
        "populates it, so this fails only in local act, not in CI.",
    ),
    (
        None,
        lambda text: bool(_ACT_SERVER_PORT_BIND_PATTERN.search(text)),
        "act's local reusable-workflow server port is already bound by another "
        "local act process. GitHub does not bind this local server in CI.",
    ),
    (
        None,
        lambda text: bool(_ACT_ARTIFACT_SERVICE_PATTERN.search(text)),
        "act's embedded artifact server rejects the request body the current "
        "actions/upload-artifact client sends, so artifact transport fails only "
        "in local act, not in CI. Artifact defects (no files matched, invalid "
        "name) carry different text and still block.",
    ),
    (
        None,
        lambda text: bool(_ACT_ACTION_CACHE_COPY_PATTERN.search(text)),
        "act could not copy its cached action into the container because dockerd "
        "rejects the /var/run/act/actions staging path, so the step fails on "
        "local transport before the action runs. CI does not stage actions this "
        "way, so this fails only in local act.",
    ),
    (
        "pull_request",
        lambda text: bool(_ACT_PR_CONTEXT_MISSING_PATTERN.search(text)),
        "act does not populate the pull_request event context on a local run, so "
        "workflows reading github.event.pull_request properties fail only in local "
        "act, not in CI.",
    ),
    (
        "pull_request",
        lambda text: bool(_ACT_PR_CONTEXT_EMPTY_ENV_PATTERN.search(text)),
        "act leaves env vars mapped from github.event.pull_request (PR_NUMBER, "
        "PR_TITLE) empty on a local run, so validation scripts fail only in local "
        "act, not in CI.",
    ),
    (
        None,
        lambda text: _ACT_NO_REPO_CONTEXT_PATTERN in text,
        "act container cannot authenticate or resolve the repository context "
        "that gh needs for API calls; workflows that call gh api or Python "
        "scripts that auto-detect the repository via gh repo view fail only "
        "in local act, not in CI where GH_TOKEN and repo info are available.",
    ),
    (
        # scope is matched against the GitHub event, not a workflow name, so it
        # must stay None. Narrowness lives in the predicate below, which requires
        # this workflow's own job and step names to appear on the failing line.
        None,
        lambda text: any(
            "Vanilla Windows" in line
            and "row is not vanilla" in line.lower()
            and "still resolve" in line.lower()
            and "vanilla-windows" in line.lower()
            for line in text.splitlines()
        ),
        "act maps windows-latest to a Linux container that ships Python, so "
        "the vanilla guard's precondition correctly reports that interpreters "
        "still resolve and refuses to run a row that is not vanilla. This "
        "fails only under local act. On a real Windows runner the harness "
        "removes every interpreter-bearing directory from the PATH the hook "
        "receives, and the precondition passes. The assertion firing here is "
        "the guard working, not a defect: a row that silently stopped being "
        "vanilla would prove nothing.",
    ),
    (
        # scope is matched against the GitHub event, not a workflow name, so it
        # must stay None. Narrowness lives in the predicate below, which requires
        # this workflow's own job and step names to appear on the failing line.
        None,
        lambda text: any(
            "VANILLA GUARD CANNOT RUN" in line
            and "docker" in line.lower()
            and (
                "permission denied" in line.lower()
                or "cannot connect to the docker daemon" in line.lower()
                or "docker is not available" in line.lower()
            )
            for line in text.splitlines()
        ),
        "the Vanilla Linux row runs the hook inside a Python-free container, "
        "which needs a Docker socket. act executes jobs inside a container "
        "that has no access to one, so the guard reports CANNOT RUN and exits "
        "3. That is the guard distinguishing an unavailable environment from a "
        "failing check, which is the behavior we want: the earlier version "
        "misread the empty output of a failed docker call as an interpreter "
        "having resolved. Real CI runners provide Docker and this row runs "
        "there.",
    ),
)

# ``_run`` stringifies a stage timeout as ``TimeoutExpired: ...`` (the exception
# class name), and ``act`` logs each action fetch as a ``git clone`` line. The
# pair tells a cold-action-cache timeout apart from a genuinely slow run.
_ACT_TIMEOUT_MARKER = "TimeoutExpired"
_ACT_CLONE_MARKER = "git clone "

# act forwards GitHub workflow commands verbatim, so an action that aborts with
# ``core.setFailed`` surfaces as a ``::error::`` line. Those lines are the only
# failure signal this module can attribute to a specific cause.
_ACT_ERROR_ANNOTATION = "::error::"

# Required-check aggregator jobs commonly echo ``::<error>::<upstream> result:
# failure`` from ``needs.<job>.result`` so branch protection sees FAILURE instead
# of SKIPPED. When that upstream job has an act-only limitation already
# explained, the aggregator annotation is a cascade symptom (#3869).
_ACT_LOG_SCOPE = re.compile(r"^\[(?P<scope>[^\]]+)\]")
_ACT_AGGREGATOR_RESULT_ANNOTATION = re.compile(
    r"::error::(?P<upstream>[^\n:]+?)\s+result: "
    r"(?:failure|cancelled|skipped|timed_out)\b",
    re.IGNORECASE,
)


def _normalized_act_label(value: str) -> str:
    """Return a case-insensitive label suitable for act job/step matching."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.lower()).split())


def _act_scope_label(line: str) -> str | None:
    """Return the rightmost act log scope label from ``[workflow/job]``."""
    match = _ACT_LOG_SCOPE.match(line.strip())
    if match is None:
        return None
    label = match.group("scope").rsplit("/", 1)[-1]
    normalized = _normalized_act_label(label)
    return normalized or None


def _git_annotation_has_missing_repository_signature(line: str, combined: str) -> bool:
    """Return whether a Git exit-128 annotation has its documented root cause."""
    if _ACT_GIT_PROCESS_ANNOTATION.search(line) is None:
        return False
    annotation_scope = _act_scope_label(line)
    return any(
        _GIT_REPO_MISSING_PATTERN in candidate
        and (
            annotation_scope is None
            or _act_scope_label(candidate) == annotation_scope
        )
        for candidate in combined.splitlines()
    )


def _explained_act_limitation_labels(combined: str, event: str | None) -> set[str]:
    """Act log scope labels whose own output matches a known limitation."""
    labels: set[str] = set()
    for line in combined.splitlines():
        if _git_annotation_has_missing_repository_signature(line, combined):
            label = _act_scope_label(line)
            if label is not None:
                labels.add(label)
            continue
        if any(
            (scope is None or scope == event) and matches(line)
            for scope, matches, _ in _ACT_LIMITATION_RULES
        ):
            label = _act_scope_label(line)
            if label is not None:
                labels.add(label)
    return labels


def _is_aggregator_cascade_annotation(
    line: str,
    explained_limitation_labels: set[str],
) -> bool:
    """True when an aggregator reports an already-explained upstream job."""
    match = _ACT_AGGREGATOR_RESULT_ANNOTATION.search(line)
    if match is None:
        return False
    upstream = _normalized_act_label(match.group("upstream"))
    return upstream in explained_limitation_labels


def _unexplained_error_annotations(
    combined: str,
    event: str | None,
    *,
    explained_limitation_labels: set[str] | None = None,
) -> list[str]:
    """``::error::`` lines that no known act limitation explains.

    Without this the downgrade is output-wide: one limitation anywhere in a
    workflow's act run would excuse every other failure in the same run. Scoping
    the match to individual annotation lines means a genuine action failure
    alongside a limitation still blocks. Aggregator ``needs.*.result``
    annotations are ignored only when their named upstream job has matched a
    known act-only limitation; otherwise, they remain unexplained.
    """
    labels = explained_limitation_labels or set()
    unexplained = []
    run_is_attributed = any(
        (scope is None or scope == event) and matches(combined)
        for scope, matches, _ in _ACT_LIMITATION_RULES
    )
    for line in combined.splitlines():
        if _ACT_ERROR_ANNOTATION not in line:
            continue
        if _git_annotation_has_missing_repository_signature(line, combined):
            continue
        if any(
            (scope is None or scope == event) and matches(line)
            for scope, matches, _ in _ACT_LIMITATION_RULES
        ):
            continue
        if run_is_attributed and _ACT_WRAPPER_ANNOTATION_PATTERN.search(line):
            continue
        if labels and _is_aggregator_cascade_annotation(line, labels):
            continue
        unexplained.append(line.strip())
    return unexplained


def _act_limitation_hint(combined: str, event: str | None = None) -> str | None:
    """Return the WARN hint when ``combined`` matches a known act limitation.

    Returns a hint for a known act-only limitation, or None when no known
    limitation is present, or when the run also carries an ``::error::``
    annotation that no limitation explains. The pull_request context errors are
    downgraded only for pull_request runs. Under workflow_dispatch, the same
    error can be a real workflow defect and must remain blocking.

    Residual gap: a failure that exits nonzero without emitting an ``::error::``
    annotation is invisible to the attribution check, so it can still ride along
    with a limitation in the same workflow run.
    """
    hint = next(
        (
            text
            for scope, matches, text in _ACT_LIMITATION_RULES
            if (scope is None or scope == event) and matches(combined)
        ),
        None,
    )
    if hint is None:
        return None
    unexplained = _unexplained_error_annotations(
        combined,
        event,
        explained_limitation_labels=_explained_act_limitation_labels(combined, event),
    )
    if unexplained:
        return None
    return hint


def _stage_timeout_hint(combined: str) -> str | None:
    """Return the cause-and-remedy line when ``combined`` shows a killed run.

    ``_run`` reports a timeout as ``TimeoutExpired: ...``, which on its own names
    no cause: the operator sees a correct workflow blamed for a wall-clock
    deadline (Issue #3949). Counting the ``git clone`` lines the child emitted
    before the kill separates the two cases that matter. Clone lines mean ``act``
    was still populating its ref-keyed ``~/.cache/act``, which a re-run turns
    into a warm-cache run of seconds. No clone lines mean the run itself was
    slow, and claiming a cold cache there would point at the wrong suspect.
    Returns None when the output carries no timeout marker.

    Every stage routes its failure detail through this, not the act stages only.
    The detail is truncated for readability and the timeout marker sits at its
    tail, so a chatty child that outruns the cap would otherwise leave the
    operator a failure with no stated reason at all.
    """
    if _ACT_TIMEOUT_MARKER not in combined:
        return None
    clones = sum(1 for line in combined.splitlines() if _ACT_CLONE_MARKER in line)
    if clones == 0:
        return (
            "[cause] the command was killed by the stage timeout. Its output shows no "
            "action-clone activity, so a cold gh act action cache is not the cause: the run "
            "itself is slow."
        )
    return (
        f"[cause] act was still cloning actions when the stage timeout fired: {clones} "
        f"'git clone' line(s) in the partial output. This is a cold gh act action cache, not a "
        f"workflow defect. act clones every referenced action into ~/.cache/act before it can "
        f"plan, and that cache is keyed by action ref, so a bumped action digest re-pays the "
        f"clone. Re-run: the second run reuses the cache and finishes in seconds."
    )


def _with_timeout_hint(combined: str) -> str:
    """Truncate a failure detail, then append the timeout cause line if any.

    Order matters: the hint is derived from the full text and appended after the
    truncation, because reading it out of the truncated copy would lose it on a
    run whose partial output outruns the cap.
    """
    detail = combined[:4000]
    hint = _stage_timeout_hint(combined)
    return detail if hint is None else f"{detail}\n{hint}"


_ACT_CONTENTION_PATTERN = re.compile(
    r"docker (?:pull|create)|failed to (?:pull|create container)|"
    r"toomanyrequests|context canceled|connection reset by peer|"
    r"server misbehaving|temporary failure",
    re.IGNORECASE,
)


def _is_act_contention_failure(detail: str) -> bool:
    return bool(_ACT_CONTENTION_PATTERN.search(detail))


def _run_act_stage(
    stage: str,
    base_cmd: Sequence[str],
    timeout: int,
    files: Sequence[str],
    repo_root: Path,
) -> StageResult:
    """Run an ``act`` invocation per workflow file, with act-limitation downgrade.

    A nonzero exit whose output carries a known act-only limitation signature
    (a missing .git in the container, an unpopulated ``pull_request`` event
    context, or an empty PR-context env var during a pull_request run) is a
    local environment gap, not a workflow defect: actionlint and the act dry-run
    already validated the workflow shape. Downgrade it to a passing stage with a
    ``[WARN]`` detail instead of a hard FAIL so the act limitation does not block
    an otherwise valid push. Every other nonzero exit still blocks.

    A stage timeout keeps blocking, but the detail gains a cause line from
    :func:`_with_timeout_hint` instead of a bare ``TimeoutExpired``.
    """
    env = _act_env(repo_root)
    warnings: list[str] = []
    for wf in files:
        event = _select_act_event(repo_root / wf)
        jobs = _workflow_jobs(repo_root / wf)
        job_args = [["-j", job] for job in jobs] if len(jobs) > 1 else [[]]
        for job_arg in job_args:
            cmd = [*base_cmd]
            if event is not None:
                cmd.append(event)
            cmd += [*job_arg, "-W", wf]
            rc, out, err = _run(cmd, timeout=timeout, cwd=repo_root, env=env)
            combined = (out + err).strip()
            if (
                rc != 0
                and _ACT_TIMEOUT_MARKER not in combined
                and _is_act_contention_failure(combined)
            ):
                retry_rc, retry_out, retry_err = _run(cmd, timeout=timeout, cwd=repo_root, env=env)
                retry_combined = (retry_out + retry_err).strip()
                if retry_rc == 0:
                    label = f"{wf} job {job_arg[1]}" if job_arg else wf
                    warnings.append(f"[WARN] {label}: retried once after act contention.")
                    continue
                combined = (
                    f"{combined}\nRetry after act contention also failed:\n{retry_combined}"
                ).strip()
                rc = retry_rc
            if rc == 0:
                continue
            # A timeout never downgrades. Since ``_run`` started returning the
            # partial output, a limitation signature can appear in a run that was
            # then killed mid-flight, and the workflow past that point was never
            # validated. Fail closed on the timeout instead of passing the stage
            # on a signature the run never got to finish disproving.
            if _ACT_TIMEOUT_MARKER not in combined:
                hint = _act_limitation_hint(combined, event)
                if hint is not None:
                    warnings.append(f"[WARN] {wf}: {hint} Set {_BYPASS_ENV}=true to silence.")
                    continue
            return StageResult(stage, False, f"{wf}:\n{_with_timeout_hint(combined)}")
    return StageResult(stage, True, "\n".join(warnings))


def _act_dryrun_stage(files: Sequence[str], repo_root: Path) -> StageResult:
    return _run_act_stage("gh act -n", ["gh", "act", "-n"], _ACT_DRYRUN_TIMEOUT, files, repo_root)


def _act_full_stage(files: Sequence[str], repo_root: Path) -> StageResult:
    return _run_act_stage("gh act (full)", ["gh", "act"], _ACT_FULL_TIMEOUT, files, repo_root)


# --- Orchestration -------------------------------------------------------


def _tool_gap_report(report: Report, note: str) -> Report:
    """Resolve a missing-tool gap into a blocking or degraded Report.

    A tool gap is a missing actionlint, ``gh``, ``gh act`` extension, or Docker
    daemon: the local run cannot proceed, but the workflow itself is not proven
    broken. Where the environment cannot provision the tool (see
    :func:`_tool_gap_is_environmental`) the gap is an environment limitation,
    not a code defect, so the gate degrades to a logged warning (exit 0,
    ``degraded=True``) and the push proceeds. Everywhere
    else (a dev laptop, or CI where the tools are provisioned) the gap stays a
    blocking tool-unavailable failure (exit 3). The install hint in ``note`` is
    preserved either way.

    Issue #2548 item 3 introduced this degrade for the ``gh``/``gh act`` gap;
    Issue #3064 makes it the single DRY degrade path for every tool gap
    (actionlint and Docker included), so a container that cannot provision
    Docker or actionlint can still push a workflow edit while CI keeps the hard
    exit 3.
    """
    if _tool_gap_is_environmental():
        report.exit_code = 0
        report.degraded = True
        report.note = (
            f"{note} Managed environment detected; the missing tool cannot be "
            "provisioned here, so this gate is downgraded to a warning. CI "
            "still runs the full workflow check."
        )
        return report
    report.exit_code = 3
    report.note = note
    return report


def run_local_test(
    workflow_files: Sequence[str],
    repo_root: Path,
    *,
    full: bool = True,
) -> Report:
    """Run the ordered stages over ``workflow_files`` and return a Report.

    Short-circuits on the first failing stage. Reports a tool/environment gap
    as exit 3 so the caller can decide how loudly to block. A clean run over
    zero files is exit 0.
    """
    if os.environ.get(_BYPASS_ENV, "").strip().lower() in _TRUTHY:
        return Report(
            exit_code=0,
            bypassed=True,
            note=f"{_BYPASS_ENV} set; local workflow run skipped (logged).",
        )

    # Precondition: repo_root must exist. A direct caller (the tests, the
    # pre-PR runner) that passes a missing root is a configuration error
    # (exit 2), not a stage failure (exit 1). main() checks this too; the
    # check lives here so every caller of run_local_test gets the contract.
    if not repo_root.is_dir():
        return Report(exit_code=2, note=f"repo root not found: {repo_root}")

    files, path_error = _select_workflow_files(workflow_files, repo_root)
    if path_error is not None:
        return Report(exit_code=2, note=path_error)
    if not files:
        return Report(exit_code=0, note="no workflow files to test")

    # A changed workflow that references a secret absent from this environment
    # cannot run under act; act has nothing to supply. Rather than force a
    # manual bypass (the friction of Issue #2841), detect the gap and report it
    # as a distinct, audible skip (exit 4, "auth" per ADR-035: authentication
    # material is absent). A secret is available when it is in the process
    # environment or the act default secret file (repo-root .secrets).
    available = {
        name.upper() for name, value in os.environ.items() if _has_secret_value(value)
    } | _act_secret_file_keys(repo_root)
    available |= _ACT_BUILTIN_SECRETS
    runnable: list[str] = []
    secret_blocked: list[tuple[str, list[str]]] = []
    for rel in files:
        missing = _missing_secrets(repo_root / rel, available)
        if missing:
            secret_blocked.append((rel, missing))
        else:
            runnable.append(rel)

    if not runnable and not secret_blocked:
        # Defensive: partition covered every file, so this only trips if files
        # was empty (already handled by the earlier guard).
        return Report(exit_code=0)

    report = Report(exit_code=0)

    # Stage 1: actionlint runs on ALL changed workflows, including
    # secret-blocked ones. It is pure static analysis (syntax, expressions,
    # action refs) and needs no secrets or Docker, so a secret-blocked workflow
    # with a real syntax error must still be caught here; linting only the
    # runnable subset would let that error bypass the gate (Issue #2841 review).
    if not _have("actionlint"):
        return _tool_gap_report(
            report,
            "actionlint not installed. Install it "
            "(https://github.com/rhysd/actionlint) or set "
            f"{_BYPASS_ENV}=true to bypass for an unrunnable workflow.",
        )
    s1 = _actionlint_stage(files, repo_root)
    report.stages.append(s1)
    if not s1.ok:
        report.exit_code = 1
        return report

    if not runnable:
        # Every changed workflow needs a locally-absent secret: nothing can run
        # under act. actionlint already validated syntax above; skip only the
        # act run, audibly, instead of blocking on a manual bypass.
        report.exit_code = 4
        report.secret_skipped = True
        report.note = (
            "unrunnable-locally: changed workflow(s) reference secrets absent "
            "from this environment. actionlint passed; skipped the local act run. "
            "Provide them via a repo-root .secrets file or the environment."
        )
        return report

    inside_act = os.environ.get("ACT", "").strip().lower() == "true"
    if inside_act and runnable != [_PYTEST_WORKFLOW]:
        report.exit_code = 3
        report.note = (
            "unrunnable-locally: nested act execution supports only the pytest workflow"
        )
        return report

    local_pytest = runnable == [_PYTEST_WORKFLOW]
    if local_pytest:
        if full:
            local_stage = _local_pytest_stage(runnable, repo_root)
            report.stages.append(local_stage)
            if not local_stage.ok:
                report.exit_code = 1
                return report
        if secret_blocked:
            report.secret_skipped = True
            report.note = (
                "skipped workflows with secrets absent locally. "
                "CI runs them with the real secrets."
            )
        return report

    # Stage 2 (dry-run) needs gh act but not a running Docker daemon: act -n
    # only plans the run.
    if not _have("gh"):
        return _tool_gap_report(
            report,
            f"gh CLI not installed. Install it or set {_BYPASS_ENV}=true.",
        )
    if not _gh_act_available():
        return _tool_gap_report(
            report,
            "gh act extension not installed. Install it via "
            f"'gh extension install nektos/gh-act' or set {_BYPASS_ENV}=true.",
        )

    worktree_error = _unsupported_worktree_gitdir_error(repo_root)
    if worktree_error is not None:
        report.exit_code = 3
        report.note = worktree_error
        return report

    s2 = _act_dryrun_stage(runnable, repo_root)
    report.stages.append(s2)
    if not s2.ok:
        report.exit_code = 1
        return report

    # Stage 3 (full run) executes in Docker, so it needs a live daemon.
    if full:
        if not _docker_ready():
            if not _have("docker"):
                cause = "Docker is not installed"
            else:
                cause = "the Docker daemon is not running"
            note = (
                f"{cause}; the full gh act run cannot execute. Install/start "
                f"Docker or set {_BYPASS_ENV}=true to bypass an unrunnable "
                "workflow (or pass --no-full for the lint+dry-run tier)."
            )
            return _tool_gap_report(report, note)
        s3 = _act_full_stage(runnable, repo_root)
        report.stages.append(s3)
        if not s3.ok:
            report.exit_code = 1
            return report

    # Mixed batch: some workflows ran, others were skipped for absent secrets.
    # The runnable ones passed (exit 0 preserved); surface the skips in the note
    # so the developer sees which files CI will still exercise with real secrets.
    if secret_blocked:
        report.secret_skipped = True
        skip_note = (
            "skipped workflows with secrets absent locally. "
            "CI runs them with the real secrets."
        )
        report.note = f"{report.note} {skip_note}".strip() if report.note else skip_note

    return report


# --- Output --------------------------------------------------------------


def _format_text(report: Report) -> str:
    if report.bypassed:
        return f"workflow-local-test: BYPASSED ({report.note})"
    if report.degraded:
        return f"workflow-local-test: DEGRADED\n  {report.note}"
    if report.exit_code == 2:
        return f"workflow-local-test: CONFIG ERROR\n  {report.note}"
    if report.exit_code == 3:
        return f"workflow-local-test: TOOL UNAVAILABLE\n  {report.note}"
    if report.exit_code == 4:
        return f"workflow-local-test: SKIPPED (secrets absent locally)\n  {report.note}"
    if report.exit_code == 0:
        passed = ", ".join(s.stage for s in report.stages) or report.note
        lines = [f"workflow-local-test: OK ({passed})"]
        for s in report.stages:
            if s.ok and s.detail:
                for line in s.detail.splitlines()[:10]:
                    lines.append(f"  {line}")
        # A mixed batch (some workflows ran, some skipped for absent secrets)
        # sets note while stages exist; surface it so the skip is visible and
        # the hook can flag it rather than reporting a silent clean pass.
        if report.stages and report.note:
            lines.append(f"  note: {report.note}")
        return "\n".join(lines)
    lines = ["workflow-local-test: FAIL"]
    for s in report.stages:
        mark = "ok" if s.ok else "FAIL"
        lines.append(f"  [{mark}] {s.stage}")
        if not s.ok and s.detail:
            for line in s.detail.splitlines()[:40]:
                lines.append(f"      {line}")
    return "\n".join(lines)


def _format_json(report: Report) -> str:
    return json.dumps(
        {
            "exit_code": report.exit_code,
            "bypassed": report.bypassed,
            "degraded": report.degraded,
            "secret_skipped": report.secret_skipped,
            "note": report.note,
            "stages": [{"stage": s.stage, "ok": s.ok, "detail": s.detail} for s in report.stages],
        },
        indent=2,
        sort_keys=True,
    )


# --- CLI -----------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Run changed GitHub Actions workflows locally before push.",
    )
    p.add_argument(
        "--files",
        nargs="*",
        default=None,
        help="Workflow file paths to test (relative to repo root).",
    )
    p.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Override repo root (default: derived from script path).",
    )
    p.add_argument(
        "--no-full",
        action="store_true",
        help="Skip the full gh act execution stage (actionlint + dry-run only).",
    )
    p.add_argument("--format", choices=("text", "json"), default="text")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    repo_root = (args.repo_root or _REPO_ROOT).resolve()
    if not repo_root.is_dir():
        print(f"error: repo root not found: {repo_root}", file=sys.stderr)
        return 2

    files = args.files if args.files is not None else []
    report = run_local_test(files, repo_root, full=not args.no_full)

    if args.format == "json":
        print(_format_json(report))
    else:
        print(_format_text(report))
    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())
