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
3 - a required tool is unavailable (actionlint, gh act, or Docker)
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

_BYPASS_ENV = "SKIP_WORKFLOW_LOCAL_TEST"

# Truthy values for the bypass env. Matches the repo convention for boolean
# env flags (see BUNDLE_CHECK_ENFORCED in scripts/validation/pre_pr.py, which
# accepts "1" and "true").
_TRUTHY = {"1", "true"}

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


def _run(
    cmd: list[str],
    *,
    timeout: int,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    """Run a command. Returns (exit_code, stdout, stderr); -1 on spawn error."""
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


def _act_env(repo_root: Path) -> dict[str, str]:
    """Build the subprocess env for gh act, GIT_DIR-aware for linked worktrees."""
    env = dict(os.environ)
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


# --- Stages --------------------------------------------------------------


def _actionlint_stage(files: Sequence[str], repo_root: Path) -> StageResult:
    rc, out, err = _run(["actionlint", *files], timeout=_ACTIONLINT_TIMEOUT, cwd=repo_root)
    if rc == 0:
        return StageResult("actionlint", True)
    return StageResult("actionlint", False, (out + err).strip()[:4000])


def _act_dryrun_stage(files: Sequence[str], repo_root: Path) -> StageResult:
    env = _act_env(repo_root)
    for wf in files:
        rc, out, err = _run(
            ["gh", "act", "-n", "-W", wf],
            timeout=_ACT_DRYRUN_TIMEOUT,
            cwd=repo_root,
            env=env,
        )
        if rc != 0:
            return StageResult(
                "gh act -n", False, f"{wf}:\n{(out + err).strip()[:4000]}"
            )
    return StageResult("gh act -n", True)


def _act_full_stage(files: Sequence[str], repo_root: Path) -> StageResult:
    env = _act_env(repo_root)
    for wf in files:
        rc, out, err = _run(
            ["gh", "act", "-W", wf],
            timeout=_ACT_FULL_TIMEOUT,
            cwd=repo_root,
            env=env,
        )
        if rc != 0:
            return StageResult(
                "gh act (full)", False, f"{wf}:\n{(out + err).strip()[:4000]}"
            )
    return StageResult("gh act (full)", True)


# --- Orchestration -------------------------------------------------------


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

    report = Report(exit_code=0)

    # Stage 1: actionlint.
    if not _have("actionlint"):
        report.exit_code = 3
        report.note = (
            "actionlint not installed. Install it "
            "(https://github.com/rhysd/actionlint) or set "
            f"{_BYPASS_ENV}=true to bypass for an unrunnable workflow."
        )
        return report
    s1 = _actionlint_stage(files, repo_root)
    report.stages.append(s1)
    if not s1.ok:
        report.exit_code = 1
        return report

    # Stage 2 (dry-run) needs gh act but not a running Docker daemon: act -n
    # only plans the run.
    if not _have("gh"):
        report.exit_code = 3
        report.note = f"gh CLI not installed. Install it or set {_BYPASS_ENV}=true."
        return report
    if not _gh_act_available():
        report.exit_code = 3
        report.note = (
            "gh act extension not installed. Install it via "
            f"'gh extension install nektos/gh-act' or set {_BYPASS_ENV}=true."
        )
        return report

    s2 = _act_dryrun_stage(files, repo_root)
    report.stages.append(s2)
    if not s2.ok:
        report.exit_code = 1
        return report

    # Stage 3 (full run) executes in Docker, so it needs a live daemon.
    if full:
        if not _docker_ready():
            report.exit_code = 3
            if not _have("docker"):
                cause = "Docker is not installed"
            else:
                cause = "the Docker daemon is not running"
            report.note = (
                f"{cause}; the full gh act run cannot execute. Install/start "
                f"Docker or set {_BYPASS_ENV}=true to bypass an unrunnable "
                "workflow (or pass --no-full for the lint+dry-run tier)."
            )
            return report
        s3 = _act_full_stage(files, repo_root)
        report.stages.append(s3)
        if not s3.ok:
            report.exit_code = 1
            return report

    return report


# --- Output --------------------------------------------------------------


def _format_text(report: Report) -> str:
    if report.bypassed:
        return f"workflow-local-test: BYPASSED ({report.note})"
    if report.exit_code == 2:
        return f"workflow-local-test: CONFIG ERROR\n  {report.note}"
    if report.exit_code == 3:
        return f"workflow-local-test: TOOL UNAVAILABLE\n  {report.note}"
    if report.exit_code == 0:
        passed = ", ".join(s.stage for s in report.stages) or report.note
        return f"workflow-local-test: OK ({passed})"
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
