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

Tool gaps degrade instead of blocking inside a managed remote container: when
actionlint, ``gh``, the ``gh act`` extension, or the Docker daemon is
unavailable inside a Claude web container or a GitHub Codespace (detected by env
markers), the gate returns exit 0 with ``degraded=True`` and a logged warning.
Such an environment may not be able to provision those tools, so blocking every
workflow-touching push there is friction, not safety. A truthy ``CI`` marker
overrides the managed-container signal, so CI, where the tools are provisioned,
keeps the hard exit 3. On a dev laptop (no container marker) the gap also stays
exit 3, so the local-run requirement is unchanged there. Issue #2548 item 3
introduced this degrade for the ``gh``/``gh act`` gap; Issue #3064 extended it to
the actionlint and Docker gaps so a container without those tools can still push
a workflow edit.

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
3 - a required tool is unavailable (actionlint, gh act, or Docker). Inside a
    managed remote container this gap degrades to exit 0 (degraded=True)
    instead, because the tool cannot be provisioned there; CI and dev laptops
    keep the hard exit 3 (Issue #3064)
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
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

_BYPASS_ENV = "SKIP_WORKFLOW_LOCAL_TEST"

# Truthy values for the bypass env. Matches the repo convention for boolean
# env flags (see REVIEW_MARKER_ENFORCED in scripts/validation/checks_coverage.py,
# which accepts "1" and "true").
_TRUTHY = {"1", "true"}

# Env markers that identify managed remote containers where the developer may
# not be able to provision ``gh act``. Observed on Claude web containers, which
# set ``CLAUDECODE``, and GitHub Codespaces. In such environments a missing
# ``gh act`` is an environment gap, not a code defect, so the gate degrades to a
# logged warning instead of blocking the push (Issue #2548, item 3). The same
# gate keeps its hard failure in CI, where ``gh act`` is provisioned: the ``CI``
# marker (set to a truthy value by GitHub Actions) overrides the managed
# container signal in :func:`_is_remote_container`.
_REMOTE_CONTAINER_ENV_MARKERS = ("CLAUDECODE", "CODESPACES")
_CI_ENV = "CI"

# Only GitHub Actions workflow files can run under ``gh act``. Custom actions
# under ``.github/actions/`` and any other path are filtered out before the act
# stages so a caller that over-collects (the pre-push hook globs changed files)
# does not hand a non-runnable path to ``gh act``.
_WORKFLOW_PREFIX = ".github/workflows/"
_WORKFLOW_SUFFIXES = (".yml", ".yaml")

# Per-stage timeouts (seconds). The full act run pulls images and executes
# composite actions, so it gets the largest budget.
_ACTIONLINT_TIMEOUT = 60
_ACT_DRYRUN_TIMEOUT = 120
_ACT_FULL_TIMEOUT = 600

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
        f"{existing} {_SHELLCHECK_SEVERITY}".strip()
        if existing
        else _SHELLCHECK_SEVERITY
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
    missing_secret_names: dict[str, list[str]] = field(default_factory=dict)
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


def _is_remote_container() -> bool:
    """True in a remote/managed container that cannot provision ``gh act``.

    A truthy ``CI`` marker overrides every container signal: CI provisions
    ``gh act``, so a gap there is a real failure and must keep blocking. Outside
    CI, the managed remote-container env markers (``CLAUDECODE``, ``CODESPACES``)
    identify environments where the ``gh act`` gap is expected and the gate
    should degrade rather than block (Issue #2548, item 3).
    """
    if _env_truthy(_CI_ENV):
        return False
    return any(_env_truthy(marker) for marker in _REMOTE_CONTAINER_ENV_MARKERS)


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
    """
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except FileNotFoundError:
        return -1, "", f"command not found: {cmd[0]}"
    except (OSError, subprocess.SubprocessError) as exc:
        return -1, "", f"{type(exc).__name__}: {exc}"
    return proc.returncode, proc.stdout, proc.stderr


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
    return sorted(
        name for name in _referenced_secrets(path) if name not in available
    )


def _secret_gap_detail(secret_blocked: Sequence[tuple[str, Sequence[str]]]) -> str:
    """Return an operator-safe summary without logging secret names."""
    return "; ".join(
        f"{rel} needs {len(missing)} locally absent secret(s)"
        for rel, missing in secret_blocked
    )


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
    return StageResult("actionlint", False, (out + err).strip()[:4000])


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
_ACT_GIT_REV_PARSE_ANNOTATION = (
    "::error::The process 'git rev-parse --abbrev-ref HEAD' failed with exit code 128"
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
        lambda text: _ACT_GIT_REV_PARSE_ANNOTATION in text,
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
)

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


def _explained_act_limitation_labels(combined: str, event: str | None) -> set[str]:
    """Act log scope labels whose own output matches a known limitation."""
    labels: set[str] = set()
    for line in combined.splitlines():
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
    for line in combined.splitlines():
        if _ACT_ERROR_ANNOTATION not in line:
            continue
        if any(
            (scope is None or scope == event) and matches(line)
            for scope, matches, _ in _ACT_LIMITATION_RULES
        ):
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
    """
    env = _act_env(repo_root)
    warnings: list[str] = []
    for wf in files:
        event = _select_act_event(repo_root / wf)
        cmd = [*base_cmd]
        if event is not None:
            cmd.append(event)
        cmd += ["-W", wf]
        rc, out, err = _run(cmd, timeout=timeout, cwd=repo_root, env=env)
        if rc != 0:
            combined = (out + err).strip()
            hint = _act_limitation_hint(combined, event)
            if hint is not None:
                warnings.append(
                    f"[WARN] {wf}: {hint} Set {_BYPASS_ENV}=true to silence."
                )
                continue
            return StageResult(stage, False, f"{wf}:\n{combined[:4000]}")
    return StageResult(stage, True, "\n".join(warnings))


def _act_dryrun_stage(files: Sequence[str], repo_root: Path) -> StageResult:
    return _run_act_stage(
        "gh act -n", ["gh", "act", "-n"], _ACT_DRYRUN_TIMEOUT, files, repo_root
    )


def _act_full_stage(files: Sequence[str], repo_root: Path) -> StageResult:
    return _run_act_stage(
        "gh act (full)", ["gh", "act"], _ACT_FULL_TIMEOUT, files, repo_root
    )


# --- Orchestration -------------------------------------------------------


def _tool_gap_report(report: Report, note: str) -> Report:
    """Resolve a missing-tool gap into a blocking or degraded Report.

    A tool gap is a missing actionlint, ``gh``, ``gh act`` extension, or Docker
    daemon: the local run cannot proceed, but the workflow itself is not proven
    broken. In a remote container (see :func:`_is_remote_container`) the gap is
    an environment limitation, not a code defect, so the gate degrades to a
    logged warning (exit 0, ``degraded=True``) and the push proceeds. Everywhere
    else (a dev laptop, or CI where the tools are provisioned) the gap stays a
    blocking tool-unavailable failure (exit 3). The install hint in ``note`` is
    preserved either way.

    Issue #2548 item 3 introduced this degrade for the ``gh``/``gh act`` gap;
    Issue #3064 makes it the single DRY degrade path for every tool gap
    (actionlint and Docker included), so a container that cannot provision
    Docker or actionlint can still push a workflow edit while CI keeps the hard
    exit 3.
    """
    if _is_remote_container():
        report.exit_code = 0
        report.degraded = True
        report.note = (
            f"{note} Remote container detected; the missing tool cannot be "
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
    missing_secret_names: dict[str, list[str]] = {}
    for rel in files:
        missing = _missing_secrets(repo_root / rel, available)
        if missing:
            secret_blocked.append((rel, missing))
            missing_secret_names[rel] = missing
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
        detail = _secret_gap_detail(secret_blocked)
        report.exit_code = 4
        report.secret_skipped = True
        report.missing_secret_names = missing_secret_names
        report.note = (
            "unrunnable-locally: changed workflow(s) reference secrets absent "
            f"from this environment ({detail}). actionlint passed; skipped the "
            "local act run, which CI runs with the real secrets. Provide them "
            "via a repo-root .secrets file or the environment to run it locally."
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
        detail = _secret_gap_detail(secret_blocked)
        report.secret_skipped = True
        report.missing_secret_names = missing_secret_names
        skip_note = (
            f"skipped (secrets absent locally): {detail}. CI runs these with "
            "the real secrets."
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
            "missing_secret_names": report.missing_secret_names,
            "note": report.note,
            "stages": [
                {"stage": s.stage, "ok": s.ok, "detail": s.detail} for s in report.stages
            ],
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
