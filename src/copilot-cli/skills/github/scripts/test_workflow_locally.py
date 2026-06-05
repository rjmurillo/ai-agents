#!/usr/bin/env python3
"""Test GitHub Actions workflows locally using nektos/act.

Validates prerequisites, constructs act commands, and provides helpful error messages.

Supports two runtimes interchangeably:
- Standalone ``act`` binary on PATH.
- GitHub CLI extension ``gh act`` (https://github.com/nektos/gh-act) when
  standalone ``act`` is not installed but ``gh`` is.

Supported workflows (no AI dependencies):
- pester-tests.yml        : Run Pester unit tests
- validate-paths.yml      : Validate path normalization

Exit codes follow ADR-035:
    0 - Success
    1 - Logic error (workflow not found, act execution failed)
    2 - Config error (prerequisites missing)
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def _check_command_exists(command: str) -> str | None:
    """Check if a command exists. Returns path if found, None otherwise."""
    return shutil.which(command)


def _get_repo_root() -> str:
    """Get the current worktree root directory.

    Uses git rev-parse --show-toplevel rather than counting parent
    directories from __file__. Path-counting is fragile to script relocation
    (it resolved under .claude/, not the repo root) and wrong in a LINKED
    worktree, where the script may be vendored at a different depth (#2377).
    --show-toplevel returns the current worktree root in every layout.
    Canonical reference: scripts/github_core/repo.py::get_repo_root.

    Falls back to the four-parents path when git cannot return a worktree root,
    so workflow-path resolution below still has a best-effort anchor.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            env=_git_env(),
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        result = None
    if result is not None and result.returncode == 0 and result.stdout.strip():
        return str(Path(result.stdout.strip()).resolve())
    return str(Path(__file__).resolve().parent.parent.parent.parent)


def _git_env() -> dict[str, str]:
    return {
        k: v
        for k, v in os.environ.items()
        if k not in {"GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE"}
    }


def _read_worktree_gitdir(repo_root: str) -> str | None:
    """Return the absolute GIT_DIR for a LINKED worktree, else None.

    In a linked worktree, ``<repo_root>/.git`` is a FILE containing a single
    line ``gitdir: <path>`` that points at the per-worktree admin directory
    under the main checkout's ``.git/worktrees/<name>``. ``act`` / ``gh act``
    run as a child process with ``cwd=repo_root`` and need ``GIT_DIR`` set to
    that path because they cannot follow the file pointer themselves (#2344).

    Returns the resolved absolute gitdir, or None when ``.git`` is a normal
    directory (no override needed) or the pointer is unreadable.
    """
    git_path = Path(repo_root) / ".git"
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
        gitdir = (Path(repo_root) / gitdir).resolve()
    else:
        gitdir = gitdir.resolve()
    return str(gitdir)


def _act_env(repo_root: str) -> dict[str, str]:
    """Build the subprocess env for act, GIT_DIR-aware for linked worktrees."""
    env = _git_env()
    gitdir = _read_worktree_gitdir(repo_root)
    if gitdir is not None:
        env["GIT_DIR"] = gitdir
    return env


def _unsupported_worktree_gitdir_error(repo_root: str) -> str | None:
    git_path = Path(repo_root) / ".git"
    if not git_path.is_file():
        return None
    gitdir = _read_worktree_gitdir(repo_root)
    if gitdir is None:
        return f"unsupported linked git worktree marker at {git_path}"
    if not Path(gitdir).is_dir():
        return f"linked git worktree gitdir is missing: {gitdir}"
    return None


def _resolve_act_runner() -> tuple[list[str], str] | None:
    """Resolve which act runtime is available.

    Returns ``(argv_prefix, display_name)`` where ``argv_prefix`` is the
    command list to invoke act (e.g. ``["act"]`` or ``["gh", "act"]``),
    and ``display_name`` is the human-readable name for logs.

    Returns ``None`` when no supported runtime is available.

    Resolution order:
        1. Standalone ``act`` on PATH.
        2. ``gh`` on PATH with the ``act`` extension installed
           (verified via ``gh act --version``).
    """
    if _check_command_exists("act"):
        return (["act"], "act")

    if _check_command_exists("gh"):
        probe = subprocess.run(
            ["gh", "act", "--version"],
            capture_output=True, text=True, check=False,
        )
        if probe.returncode == 0:
            return (["gh", "act"], "gh act")

    return None


def _redact_secret_arg(arg: str) -> str:
    if "=" not in arg:
        return "<redacted>"
    key, _value = arg.split("=", 1)
    return f"{key}=<redacted>"


def _redact_act_args_for_log(args: list[str]) -> list[str]:
    redacted: list[str] = []
    redact_next = False
    for arg in args:
        if redact_next:
            redacted.append(_redact_secret_arg(arg))
            redact_next = False
            continue
        if arg.startswith("-s=") or arg.startswith("--secret="):
            option, value = arg.split("=", 1)
            redacted.append(f"{option}={_redact_secret_arg(value)}")
            continue
        redacted.append(arg)
        if arg in {"-s", "--secret"}:
            redact_next = True
    return redacted


WORKFLOW_MAP = {
    "pester-tests": "pester-tests.yml",
    "validate-paths": "validate-paths.yml",
    "memory-validation": "memory-validation.yml",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Test GitHub Actions workflows locally with act.",
    )
    parser.add_argument(
        "--workflow",
        required=True,
        help='Workflow name (without .yml) or full path. E.g., "pester-tests"',
    )
    parser.add_argument(
        "--event",
        default="pull_request",
        help="GitHub event type to simulate (default: pull_request)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate workflow without execution",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output from act",
    )
    parser.add_argument(
        "--job",
        default="",
        help="Specific job name to run",
    )
    parser.add_argument(
        "--secrets",
        default="",
        help='JSON object of secrets, e.g. \'{"GITHUB_TOKEN":"ghp_..."}\'',
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    print("[INFO] Checking prerequisites...")

    # Resolve an act runtime (standalone act, or gh act extension).
    runner = _resolve_act_runner()
    if runner is None:
        print(
            "[ERROR] act not found. Install act (standalone) or the gh act "
            "extension to enable local workflow testing.",
        )
        print()
        print("Installation instructions:")
        print("  macOS:       brew install act")
        print("  Windows:     Download from https://github.com/nektos/act/releases")
        print("  Linux:       Download from https://github.com/nektos/act/releases")
        print("  GitHub CLI:  gh extension install https://github.com/nektos/gh-act")
        print()
        print("See: https://nektosact.com/installation/index.html")
        return 2

    act_argv, act_name = runner
    act_version = subprocess.run(
        [*act_argv, "--version"], capture_output=True, text=True, check=False,
    )
    print(f"[SUCCESS] {act_name} found: {act_version.stdout.strip()}")

    # Check for Docker
    docker_path = _check_command_exists("docker")
    if not docker_path:
        print("[ERROR] Docker not found. act requires Docker to run workflows.")
        print()
        print("Install Docker:")
        print("  macOS/Windows: https://www.docker.com/products/docker-desktop")
        print("  Linux:         https://docs.docker.com/engine/install/")
        return 2

    docker_result = subprocess.run(
        ["docker", "info"], capture_output=True, text=True, check=False,
    )
    if docker_result.returncode != 0:
        print("[ERROR] Docker daemon is not running. Start Docker and try again.")
        return 2
    print("[SUCCESS] Docker is running")

    # Resolve workflow path
    repo_root = _get_repo_root()
    worktree_error = _unsupported_worktree_gitdir_error(repo_root)
    if worktree_error is not None:
        print(f"[ERROR] {worktree_error}")
        print("Re-run from the main worktree or repair the linked worktree metadata.")
        return 2
    workflows_dir = os.path.join(repo_root, ".github", "workflows")

    workflow_path: str | None = None
    workflow = args.workflow

    if workflow.endswith(".yml") or workflow.endswith(".yaml"):
        if os.path.exists(workflow):
            workflow_path = workflow
        else:
            candidate = os.path.join(workflows_dir, workflow)
            if os.path.exists(candidate):
                workflow_path = candidate
    elif workflow in WORKFLOW_MAP:
        workflow_path = os.path.join(workflows_dir, WORKFLOW_MAP[workflow])
    else:
        workflow_path = os.path.join(workflows_dir, f"{workflow}.yml")

    if not workflow_path or not os.path.exists(workflow_path):
        print(f"[ERROR] Workflow file not found: {workflow}")
        print()
        print("Available workflows:")
        for key in sorted(WORKFLOW_MAP.keys()):
            print(f"  - {key}")
        print()
        print("Unsupported workflows (require AI infrastructure or Copilot CLI):")
        print("  - ai-session-protocol (requires Copilot CLI with BOT_PAT)")
        print("  - ai-pr-quality-gate (requires Copilot CLI with BOT_PAT)")
        print("  - ai-spec-validation (requires Copilot CLI with BOT_PAT)")
        return 1

    print(f"[INFO] Workflow: {workflow_path}")

    # Build act command
    act_args = [args.event, "-W", workflow_path]

    if args.job:
        act_args.extend(["-j", args.job])

    if args.dry_run:
        act_args.append("-n")
        print("[INFO] Dry-run mode: validating workflow without execution")

    if args.verbose:
        act_args.append("-v")

    # Parse secrets
    secrets: dict[str, str] = {}
    if args.secrets:
        try:
            secrets = json.loads(args.secrets)
        except json.JSONDecodeError:
            print("[ERROR] Invalid JSON for --secrets parameter", file=sys.stderr)
            return 1

    for key, value in secrets.items():
        act_args.extend(["-s", f"{key}={value}"])

    # Try to get GITHUB_TOKEN from gh CLI if not provided
    if "GITHUB_TOKEN" not in secrets:
        gh_path = _check_command_exists("gh")
        if gh_path:
            token_result = subprocess.run(
                ["gh", "auth", "token"],
                capture_output=True, text=True, check=False,
            )
            if token_result.returncode == 0 and token_result.stdout.strip():
                act_args.extend(["-s", f"GITHUB_TOKEN={token_result.stdout.strip()}"])
                print("[INFO] Using GITHUB_TOKEN from gh CLI")

    # Execute act
    logged_args = " ".join(_redact_act_args_for_log(act_args))
    print(f"[INFO] Running: {act_name} {logged_args}")
    print()

    result = subprocess.run(
        [*act_argv, *act_args],
        cwd=repo_root,
        env=_act_env(repo_root),
        check=False,
    )

    if result.returncode == 0:
        print()
        print("[SUCCESS] Workflow execution completed successfully")
        return 0

    print()
    print(f"[ERROR] Workflow execution failed with exit code {result.returncode}")
    print()
    print("Troubleshooting tips:")
    print("  1. Check Docker logs: docker ps -a | grep act-")
    print("  2. Run with --verbose for detailed output")
    print("  3. Use --dry-run to validate workflow syntax")
    print("  4. Ensure Docker has sufficient resources")
    print()
    print("Common issues:")
    print("  - Missing dependencies: Use catthehacker/ubuntu:act-latest image")
    print("  - Windows-specific code: act uses Linux containers")
    print("  - Secrets not available: Pass via --secrets parameter")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
