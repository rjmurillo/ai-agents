"""Throwaway repository that runs the real lefthook hook entrypoints.

Issue #6734 acceptance criterion 3 asks for tests that drive the real hooks, not
the policy functions behind them. This builds a repository whose
``.git/hooks/pre-commit`` and ``.git/hooks/pre-push`` are the shims
``lefthook install`` writes, with the job bodies copied from the repository's
own ``lefthook.yml``. A test then runs plain ``git commit`` and ``git push``, so
git, the shim, lefthook, and the policy scripts all run as they do for a
contributor.

Only the job list is narrowed. Heavy jobs (pytest, mypy, semgrep, markdown
lint) would need the whole tree and the network, so the fixture keeps the
cheap policy jobs and drops the rest. Each kept job keeps its real ``glob``,
``stage_fixed``, ``use_stdin``, ``skip`` and ``run`` fields, apart from the
``uv run`` prefix, which becomes the running interpreter.

Two differences from a contributor checkout. The ``lefthook:`` runner key is
dropped and ``LEFTHOOK_BIN`` names the pinned binary, so the runner's own
fallback order stays with ``tests/test_lefthook_runner.py``. The
``placeholder-identity`` job is omitted because it skips any repository under
pytest's ``tmp_path`` by design.
"""

from __future__ import annotations

import copy
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from tests.support.lefthook_binary import resolve_lefthook

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LEFTHOOK = resolve_lefthook()
# lefthook runs `run:` strings through sh, where a native Windows path loses its
# backslashes. as_posix() is a no-op on POSIX (refs #3289).
PYTHON_POSIX = Path(sys.executable).as_posix()

PRE_COMMIT_JOBS = (
    "repo-health",
    "repair-packed-refs",
    "branch-policy",
    "root-hygiene-policy",
    "staged-dash-policy",
    "conflict-marker-policy",
    "security-suppressions-staged",
    "python-autofix",
    "python-check",
)
PRE_PUSH_JOBS = (
    "repo-health",
    "repair-packed-refs",
    "push-ref-policy",
    "security-suppression-policy",
    "python-lint-advisory",
)

# Every file a kept job imports. A missing sibling fails here with
# ModuleNotFoundError, which is the roster doing its job.
SUPPORT_FILES = (
    ".claude/skills/security-detection/detect_infrastructure.py",
    "build/scripts/__init__.py",
    "build/scripts/validate_plugin_version_bump.py",
    "scripts/__init__.py",
    "scripts/ci/diff_line_scope.py",
    "scripts/ci/report_advisory_result.py",
    "scripts/ci/run_pytest_non_tmp.py",
    "scripts/ci/run_pytest_partition.py",
    "scripts/hook_utilities/__init__.py",
    "scripts/hook_utilities/guards.py",
    "scripts/hook_utilities/utilities.py",
    "scripts/maintenance/__init__.py",
    "scripts/maintenance/repair_packed_refs.py",
    "scripts/validation/__init__.py",
    "scripts/validation/check_repo_health.py",
    "scripts/validation/check_repo_health_report.py",
    "scripts/validation/cli_smoke_paths.py",
    "scripts/validation/evidence.py",
    "scripts/validation/git_hook_policy.py",
    "scripts/validation/host_headroom.py",
    "scripts/validation/models.py",
    "scripts/validation/object_id.py",
    "scripts/validation/push_ref_staleness.py",
    "scripts/validation/pytest_deferral.py",
    "scripts/validation/pytest_lanes.py",
    "scripts/validation/run_workflow_local_test.py",
    "scripts/validation/session_scope.py",
    "scripts/validation/sha_pinning.py",
    "scripts/validation/testmon_lane_db.py",
    "scripts/validation/testmon_seed.py",
    "scripts/validation/testmon_seed_archive.py",
    "scripts/validation/testmon_seed_gh.py",
    "scripts/validation/testmon_seed_runs.py",
    "scripts/validation/testmon_seed_trust.py",
    "scripts/validation/validate_review_marker.py",
)

_ENV_KEEP = ("PATH", "PATHEXT", "COMSPEC", "SYSTEMROOT", "TEMP", "TMP", "TMPDIR", "VIRTUAL_ENV")


def _keep_jobs(items: list[dict[str, Any]], names: tuple[str, ...]) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    for item in items:
        if "group" in item:
            group = copy.deepcopy(item)
            group["group"]["jobs"] = _keep_jobs(group["group"]["jobs"], names)
            if group["group"]["jobs"]:
                kept.append(group)
        elif item["name"] in names:
            kept.append(copy.deepcopy(item))
    return kept


def _rewrite_runner(item: dict[str, Any]) -> None:
    if "group" in item:
        for job in item["group"]["jobs"]:
            _rewrite_runner(job)
        return
    run = item.get("run")
    if isinstance(run, str):
        for prefix in ("uv run --frozen --extra dev", "uv run --frozen"):
            run = run.replace(f"{prefix} python", f'"{PYTHON_POSIX}"')
            run = run.replace(f"{prefix} ruff", f'"{PYTHON_POSIX}" -m ruff')
        item["run"] = run


def runtime_config() -> dict[str, Any]:
    """Return the repository's lefthook config narrowed to the cheap jobs."""
    config = yaml.safe_load((PROJECT_ROOT / "lefthook.yml").read_text(encoding="utf-8"))
    narrowed: dict[str, Any] = {
        "min_version": config["min_version"],
        "no_auto_install": True,
        "glob_matcher": config["glob_matcher"],
        "output": False,
    }
    for hook, names in (("pre-commit", PRE_COMMIT_JOBS), ("pre-push", PRE_PUSH_JOBS)):
        narrowed[hook] = {
            "piped": config[hook].get("piped", False),
            "jobs": _keep_jobs(config[hook]["jobs"], names),
        }
    for item in (*narrowed["pre-commit"]["jobs"], *narrowed["pre-push"]["jobs"]):
        _rewrite_runner(item)
    return narrowed


@dataclass(frozen=True)
class Snapshot:
    """What a failed hook must leave as it found it: refs, index, stash, file bytes and modes."""

    head: str
    refs: str
    index: str
    stash: str
    worktree: dict[str, tuple[bytes, int]]

    def checkout_state(self) -> tuple[str, str, str, dict[str, tuple[bytes, int]]]:
        """Everything except refs, which a successful push legitimately moves."""
        return (self.head, self.index, self.stash, self.worktree)


@dataclass
class HookRepo:
    """A clone with installed hooks and a bare ``origin`` beside it."""

    repo: Path
    origin: Path
    env: dict[str, str]

    def git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return self.run_git(self.repo, *args, check=check)

    def run_git(
        self, cwd: Path, *args: str, check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            env=self.env,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=check,
            timeout=120,
        )

    def out(self, *args: str) -> str:
        return self.git(*args).stdout.strip()

    def remote_ref(self, ref: str) -> str:
        """Return the sha ``origin`` holds for ``ref``, or an empty string."""
        result = self.run_git(self.origin, "rev-parse", "--verify", "-q", ref, check=False)
        return result.stdout.strip()

    def write(self, relative_path: str, content: str) -> Path:
        path = self.repo / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode("utf-8"))
        return path

    def stage(self, *paths: str) -> None:
        self.git("add", "--", *paths)

    def commit_all(self, message: str) -> str:
        """Commit through the installed hooks, which must pass."""
        self.git("add", "-A")
        result = self.git("commit", "-q", "-m", message, check=False)
        assert result.returncode == 0, result.stdout + result.stderr
        return self.out("rev-parse", "HEAD")

    def snapshot(self) -> Snapshot:
        worktree = {
            path.relative_to(self.repo).as_posix(): (path.read_bytes(), path.stat().st_mode)
            for path in sorted(self.repo.rglob("*"))
            if path.is_file() and ".git" not in path.relative_to(self.repo).parts
        }
        return Snapshot(
            head=self.out("rev-parse", "HEAD"),
            refs=self.out("for-each-ref", "--format=%(refname) %(objectname)"),
            index=self.out("ls-files", "--stage"),
            stash=self.out("stash", "list"),
            worktree=worktree,
        )


def hermetic_env(home: Path) -> dict[str, str]:
    """An environment with no ambient git config, credentials, or GIT_* state."""
    env = {key: value for key, value in os.environ.items() if key in _ENV_KEEP}
    env.update(
        {
            "HOME": str(home),
            "USERPROFILE": str(home),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_EDITOR": "true",
            "LC_ALL": "C",
            "LEFTHOOK_BIN": str(LEFTHOOK),
            "PYTHONDONTWRITEBYTECODE": "1",
            "RUFF_NO_CACHE": "true",
        }
    )
    return env


def build_hook_repo(tmp_path: Path, branch: str = "feature/work") -> HookRepo:
    """Create ``origin.git`` and a clone with the hooks installed.

    ``main`` holds the support scripts and ``lefthook.yml``. The clone starts on
    ``branch``, which has no commits of its own yet.
    """
    assert LEFTHOOK is not None
    home = tmp_path / "home"
    home.mkdir()
    env = hermetic_env(home)
    origin = tmp_path / "origin.git"
    repo = tmp_path / "work tree"
    subprocess.run(
        ["git", "init", "-q", "--bare", "-b", "main", str(origin)],
        env=env,
        check=True,
        timeout=60,
    )
    repo.mkdir()
    fixture = HookRepo(repo=repo, origin=origin, env=env)
    fixture.git("init", "-q", "-b", "main")
    fixture.git("config", "user.name", "Test User")
    fixture.git("config", "user.email", "user@example.com")
    fixture.git("config", "commit.gpgsign", "false")
    fixture.git("remote", "add", "origin", str(origin))
    (repo / "lefthook.yml").write_text(
        yaml.safe_dump(runtime_config(), sort_keys=False), encoding="utf-8", newline="\n"
    )
    for relative_path in SUPPORT_FILES:
        destination = repo / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PROJECT_ROOT / relative_path, destination)
    fixture.write("README.md", "# Fixture\n")
    fixture.write("app.py", "VALUE = 1\n")
    fixture.write(".gitignore", "__pycache__/\n")
    fixture.git("add", "-A")
    fixture.git("commit", "-q", "-m", "chore: seed fixture")
    fixture.git("push", "-q", "origin", "main")
    fixture.git("fetch", "-q", "origin")
    fixture.git("checkout", "-q", "-b", branch)
    result = subprocess.run(
        [LEFTHOOK, "install", "--reset-hooks-path"],
        cwd=repo,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return fixture


def commit_without_hooks(fixture: HookRepo, relative_path: str, content: str, message: str) -> str:
    """Record a commit with git plumbing, which never runs a hook.

    Stands in for a commit made where the pre-commit hook was absent or broken.
    The pre-push hook is then the only gate left between that commit and the
    remote, which is the case its tests need.
    """
    fixture.write(relative_path, content)
    fixture.stage(relative_path)
    tree = fixture.out("write-tree")
    sha = fixture.out("commit-tree", tree, "-p", "HEAD", "-m", message)
    fixture.git("update-ref", "HEAD", sha)
    return sha
