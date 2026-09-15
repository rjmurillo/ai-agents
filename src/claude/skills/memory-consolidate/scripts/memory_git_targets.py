#!/usr/bin/env python3
"""Validate and restore memory-consolidation targets from a fixed git manifest."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import TypedDict, cast

EXIT_OK = 0
EXIT_LOGIC = 1
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3

MEMORIES_PREFIX = ".serena/memories"
COMMIT_RE = re.compile(r"\A(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
MANIFEST_NAME = "memory-consolidate-manifest.json"


class Manifest(TypedDict):
    startingCommit: str
    targets: list[str]


def _run_git(repo: Path | None, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=repo,
        shell=False,
    )


def _repo_root(cwd: Path | None = None) -> Path:
    """Return the repository root."""
    result = _run_git(cwd, "rev-parse", "--show-toplevel")
    if result.returncode != 0:
        raise RuntimeError("Not inside a git repository")
    root = Path(result.stdout.strip()).resolve()
    current = (cwd or Path.cwd()).resolve()
    if current != root and root not in current.parents:
        raise RuntimeError("Current directory is outside the reported repository root")
    return root


def _git_dir(cwd: Path | None = None) -> Path:
    """Return the repository's git directory."""
    result = _run_git(cwd, "rev-parse", "--git-dir")
    if result.returncode != 0:
        raise RuntimeError("Not inside a git repository")
    git_dir = Path(result.stdout.strip())
    if not git_dir.is_absolute():
        git_dir = (cwd or Path.cwd()) / git_dir
    return git_dir.resolve()


def _manifest_path(cwd: Path | None = None) -> Path:
    _repo_root(cwd)
    return _git_dir(cwd) / MANIFEST_NAME


def load_manifest(cwd: Path | None = None) -> object:
    """Load the manifest from its fixed location inside the git directory."""
    path = _manifest_path(cwd)
    if path.is_symlink():
        raise FileNotFoundError(f"Manifest must not be a symlink: {path}")
    if not path.is_file():
        raise FileNotFoundError(f"Manifest not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_target(target: str) -> str:
    return str(PurePosixPath(target.replace("\\", "/")))


def _target_error(target: str, index: int, repo_root: Path) -> str | None:
    normalized = target.replace("\\", "/")
    path = PurePosixPath(normalized)
    label = f"targets[{index}]"
    if "\0" in target:
        return f"{label}: null byte rejected"
    if "\\" in target:
        return f"{label}: backslash rejected"
    if path.is_absolute() or (len(normalized) >= 2 and normalized[1] == ":"):
        return f"{label}: absolute path rejected: {target}"
    if ".." in path.parts:
        return f"{label}: path traversal rejected: {target}"

    canonical = PurePosixPath(_normalize_target(normalized))
    memories = PurePosixPath(MEMORIES_PREFIX)
    if canonical == memories:
        return f"{label}: memory root is not a file target"
    if memories not in canonical.parents:
        return f"{label}: not under {MEMORIES_PREFIX}: {target}"

    candidate = repo_root.resolve()
    for part in canonical.parts:
        candidate /= part
        if candidate.is_symlink():
            return f"{label}: symlink rejected: {target}"

    memories_root = (repo_root.resolve() / MEMORIES_PREFIX).resolve()
    resolved = candidate.resolve(strict=False)
    if resolved != memories_root and memories_root not in resolved.parents:
        return f"{label}: path escapes {MEMORIES_PREFIX}: {target}"
    return None


def _commit_error(commit: object, repo_root: Path) -> str | None:
    if not isinstance(commit, str) or not COMMIT_RE.fullmatch(commit):
        return "'startingCommit' must be a 40-character lowercase hex SHA"
    result = _run_git(repo_root, "cat-file", "-e", f"{commit}^{{commit}}")
    if result.returncode != 0:
        return "'startingCommit' does not resolve to a commit"
    return None


def _blob_error(commit: str, target: str, repo_root: Path) -> str | None:
    result = _run_git(repo_root, "cat-file", "-t", f"{commit}:{target}")
    if result.returncode != 0 or result.stdout.strip() != "blob":
        return f"target is not a file in startingCommit: {target}"
    return None


def _validate_target(
    target: object,
    index: int,
    repo_root: Path,
    commit: str | None,
    seen: set[str],
) -> str | None:
    if not isinstance(target, str):
        return f"targets[{index}]: must be a string"
    normalized = _normalize_target(target)
    error = _target_error(target, index, repo_root)
    if error:
        return error
    if normalized in seen:
        return f"targets[{index}]: duplicate target: {target}"
    seen.add(normalized)
    tracked = _run_git(
        repo_root,
        "--literal-pathspecs",
        "ls-files",
        "--error-unmatch",
        "--",
        normalized,
    )
    if tracked.returncode != 0:
        return f"targets[{index}]: not tracked by git: {target}"
    if commit is None:
        return None
    blob_error = _blob_error(commit, normalized, repo_root)
    return f"targets[{index}]: {blob_error}" if blob_error else None


def validate_manifest(manifest: object, repo_root: Path) -> list[str]:
    """Return all manifest validation errors."""
    if not isinstance(manifest, dict):
        return ["manifest must be a JSON object"]
    errors: list[str] = []
    targets = manifest.get("targets")
    if not isinstance(targets, list):
        return ["'targets' must be a list"]
    if not targets:
        errors.append("'targets' must not be empty")

    commit_error = _commit_error(manifest.get("startingCommit"), repo_root)
    if commit_error:
        errors.append(commit_error)
    commit = None if commit_error else manifest["startingCommit"]

    seen: set[str] = set()
    for index, target in enumerate(targets):
        error = _validate_target(target, index, repo_root, commit, seen)
        if error:
            errors.append(error)
    return errors


def _load_valid_manifest(
    cwd: Path | None,
) -> tuple[Manifest | None, Path | None, int]:
    try:
        repo_root = _repo_root(cwd)
        manifest = load_manifest(cwd)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return None, None, EXIT_CONFIG
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return None, None, EXIT_CONFIG
    except json.JSONDecodeError as exc:
        print(f"ERROR: malformed JSON: {exc}", file=sys.stderr)
        return None, None, EXIT_LOGIC

    errors = validate_manifest(manifest, repo_root)
    for error in errors:
        print(f"VALIDATION: {error}", file=sys.stderr)
    if errors or not isinstance(manifest, dict):
        return None, repo_root, EXIT_LOGIC
    return cast(Manifest, manifest), repo_root, EXIT_OK


def check(cwd: Path | None = None) -> int:
    """Validate the manifest."""
    _, _, status = _load_valid_manifest(cwd)
    if status == EXIT_OK:
        print("OK: manifest valid", file=sys.stderr)
    return status


def restore(cwd: Path | None = None) -> int:
    """Restore all targets from the exact starting commit."""
    manifest, repo_root, status = _load_valid_manifest(cwd)
    if status != EXIT_OK or manifest is None or repo_root is None:
        return status

    targets = [_normalize_target(target) for target in manifest["targets"]]
    result = _run_git(
        repo_root,
        "--literal-pathspecs",
        "restore",
        f"--source={manifest['startingCommit']}",
        "--worktree",
        "--",
        *targets,
    )
    if result.returncode != 0:
        print(f"ERROR: git restore failed: {result.stderr.strip()}", file=sys.stderr)
        return EXIT_EXTERNAL
    print("OK: all targets restored", file=sys.stderr)
    return EXIT_OK


def cleanup(cwd: Path | None = None) -> int:
    """Remove the manifest."""
    try:
        path = _manifest_path(cwd)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_CONFIG

    if path.is_file():
        path.unlink()
        print("OK: manifest removed", file=sys.stderr)
    else:
        print("OK: no manifest to remove", file=sys.stderr)
    return EXIT_OK


def show_manifest_path(cwd: Path | None = None) -> int:
    """Print the fixed manifest path for a file-writing tool."""
    try:
        print(_manifest_path(cwd))
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    """Run a manifest command."""
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print(
            "Usage: memory_git_targets.py <path|check|restore|cleanup>",
            file=sys.stderr,
        )
        return EXIT_CONFIG

    commands = {
        "path": show_manifest_path,
        "check": check,
        "restore": restore,
        "cleanup": cleanup,
    }
    command = commands.get(args[0])
    if command is None:
        print(f"ERROR: unknown command: {args[0]}", file=sys.stderr)
        return EXIT_CONFIG
    return command()


if __name__ == "__main__":
    sys.exit(main())
