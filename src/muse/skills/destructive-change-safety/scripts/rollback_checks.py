"""Per-kind rollback verification for ``gate_verdict.rule_rollback``.

Each check takes the evidence ``rollback`` object and returns the reasons it
cannot be trusted. An empty list means the named recovery path is real:

- backup: both files exist, their sizes match, and their SHA-256 hashes match.
- snapshot: ``snapshot_path`` is an existing file or a non-empty directory.
  This proves the path exists. It does not prove the path holds a valid
  snapshot of the data at risk; the evidence author owns that claim.
- version: ``ref`` is a 40-hex commit id that ``git cat-file`` resolves. Any
  reachable commit passes; the check does not tie it to the destroyed data.

Split out of ``gate_verdict.py`` so the verdict rules stay free of file and
subprocess access. The version check is the only subprocess: a fixed
``git cat-file -e`` argv whose one variable part is a validated commit id.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from collections.abc import Callable
from pathlib import Path

_COMMIT_ID = re.compile(r"[0-9a-fA-F]{40}")
_GIT_TIMEOUT_SECONDS = 30


def sha256(path: Path) -> str:
    """Hash the file in chunks, so a large backup is never held in memory."""
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def _same_content(backup_file: Path, source_file: Path) -> bool:
    """Compare sizes first, then hashes; a size mismatch skips both reads."""
    if backup_file.stat().st_size != source_file.stat().st_size:
        return False
    return sha256(backup_file) == sha256(source_file)


def backup_reasons(rollback: dict[str, object]) -> list[str]:
    """A backup needs both paths, both files must exist, and their hashes must match."""
    backup, source = rollback.get("backup_path"), rollback.get("source_path")
    if not (backup and source):
        return ["rollback kind backup needs both backup_path and source_path to be verified"]
    backup_file, source_file = Path(str(backup)), Path(str(source))
    if not backup_file.is_file() or not source_file.is_file():
        return ["rollback backup or source file does not exist"]
    try:
        same = _same_content(backup_file, source_file)
    except OSError as exc:
        return [f"rollback backup or source file could not be read: {exc}"]
    if not same:
        return ["rollback backup does not match the source file"]
    return []


def snapshot_reasons(rollback: dict[str, object]) -> list[str]:
    """A snapshot must point at an existing file or a non-empty directory."""
    raw = rollback.get("snapshot_path")
    if not raw:
        return ["rollback kind snapshot needs a snapshot_path to be verified"]
    path = Path(str(raw))
    if path.is_file():
        return []
    try:
        if path.is_dir() and any(path.iterdir()):
            return []
    except OSError as exc:
        return [f"rollback snapshot_path could not be read: {exc}"]
    return ["rollback snapshot_path does not exist or is empty"]


def version_reasons(rollback: dict[str, object]) -> list[str]:
    """A version ref must be a full commit id that git resolves in the current repository.

    git runs in the current working directory, so run the gate from the
    repository root. Outside a repository every ref blocks, which fails closed.
    """
    ref = str(rollback.get("ref") or "")
    if not _COMMIT_ID.fullmatch(ref):
        return ["rollback kind version needs ref to be a 40-hex commit id"]
    try:
        result = subprocess.run(
            ["git", "cat-file", "-e", f"{ref}^{{commit}}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return [
            "rollback version ref could not be checked: "
            f"git did not finish within {_GIT_TIMEOUT_SECONDS}s"
        ]
    except OSError as exc:
        return [f"rollback version ref could not be checked: git did not run: {exc}"]
    if result.returncode == 0:
        return []
    # git exits 128 both for an unknown object and for "not a git repository",
    # so the exit code cannot name the cause. Its first stderr line can.
    detail = (result.stderr or "").strip().splitlines()[:1] or ["no stderr"]
    return [
        f"rollback version ref did not resolve to a commit (git exit {result.returncode}): "
        f"{detail[0]}"
    ]


KIND_CHECKS: dict[str, Callable[[dict[str, object]], list[str]]] = {
    "backup": backup_reasons,
    "snapshot": snapshot_reasons,
    "version": version_reasons,
}
