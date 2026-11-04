"""Per-kind rollback verification for ``gate_verdict.rule_rollback``.

Each check takes the evidence ``rollback`` object and returns the reasons it
cannot be trusted. An empty list means the named recovery path is real:

- backup: both files exist, their sizes match, and their SHA-256 hashes match.
- snapshot: ``snapshot_path`` names a snapshot manifest file, or a directory
  holding ``snapshot.json``. The gate checks the manifest fields ``format``,
  ``version``, ``ref``, ``target``, ``payload``, and ``sha256``. The manifest
  ``ref`` must equal the rollback ``ref``, its ``target`` must equal the
  rollback ``snapshot_target``, and its payload must stay inside the snapshot
  and hash to ``sha256``.
- version: ``ref`` is a 40-hex commit id that ``git cat-file`` resolves. Any
  reachable commit passes; the check does not tie it to the destroyed data.

Split out of ``gate_verdict.py`` so the verdict rules stay free of file and
subprocess access. The version check is the only subprocess: a fixed
``git cat-file -e`` argv whose one variable part is a validated commit id.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections.abc import Callable
from pathlib import Path

_COMMIT_ID = re.compile(r"[0-9a-fA-F]{40}")
_SHA256 = re.compile(r"[0-9a-fA-F]{64}")
_GIT_TIMEOUT_SECONDS = 30
SNAPSHOT_FORMAT = "destructive-change-snapshot"
SNAPSHOT_VERSION = 1
SNAPSHOT_MANIFEST_NAME = "snapshot.json"


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


def _is_nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _locate_snapshot_manifest(path: Path) -> tuple[Path, Path, list[str]]:
    """Return the manifest and snapshot root, or the reason there is none."""
    if path.is_file():
        return path, path.parent, []
    if path.is_dir():
        manifest = path / SNAPSHOT_MANIFEST_NAME
        if manifest.is_file():
            return manifest, path, []
        try:
            if not any(path.iterdir()):
                return manifest, path, ["rollback snapshot_path does not exist or is empty"]
        except OSError as exc:
            return manifest, path, [f"rollback snapshot_path could not be read: {exc}"]
        return manifest, path, ["rollback snapshot directory has no snapshot.json manifest"]
    return path, path.parent, ["rollback snapshot_path does not exist or is empty"]


def _read_snapshot_manifest(manifest_path: Path) -> tuple[dict[str, object], list[str]]:
    """Read one manifest as a JSON object; malformed content fails closed."""
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except OSError as exc:
        return {}, [f"rollback snapshot manifest could not be read: {exc}"]
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}, ["rollback snapshot_path does not name a valid snapshot manifest"]
    if not isinstance(manifest, dict):
        return {}, ["rollback snapshot_path does not name a valid snapshot manifest"]
    return manifest, []


def _snapshot_identity_reasons(
    manifest: dict[str, object], rollback: dict[str, object]
) -> list[str]:
    """Check the format and the recovery point the manifest claims."""
    reasons = []
    if manifest.get("format") != SNAPSHOT_FORMAT:
        reasons.append(f"rollback snapshot manifest format must be {SNAPSHOT_FORMAT}")
    version = manifest.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version != SNAPSHOT_VERSION:
        reasons.append(f"rollback snapshot manifest version must be {SNAPSHOT_VERSION}")
    for rollback_key, manifest_key in (("ref", "ref"), ("snapshot_target", "target")):
        claimed = rollback.get(rollback_key)
        if not _is_nonempty_string(claimed):
            reasons.append(f"rollback kind snapshot needs a {rollback_key} to be verified")
        elif manifest.get(manifest_key) != claimed:
            reasons.append(
                f"rollback snapshot manifest {manifest_key} does not match {rollback_key}"
            )
    return reasons


def _snapshot_payload_reasons(
    manifest: dict[str, object], manifest_path: Path, root: Path
) -> list[str]:
    """Check that the payload named by the manifest is inside it and intact."""
    payload = manifest.get("payload")
    if not _is_nonempty_string(payload):
        return ["rollback snapshot manifest payload must name a snapshot file"]
    payload_path = Path(str(payload))
    if payload_path.is_absolute() or ".." in payload_path.parts:
        return ["rollback snapshot payload must be a relative path inside the snapshot"]
    try:
        root_resolved = root.resolve()
        payload_file = (root / payload_path).resolve()
        if not payload_file.is_relative_to(root_resolved):
            return ["rollback snapshot payload must be a relative path inside the snapshot"]
        if payload_file == manifest_path.resolve():
            return ["rollback snapshot payload must not be the snapshot manifest"]
        if not payload_file.is_file():
            return ["rollback snapshot payload does not exist"]
        digest = manifest.get("sha256")
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            return ["rollback snapshot manifest sha256 must be a 64-hex digest"]
        if sha256(payload_file).lower() != digest.lower():
            return ["rollback snapshot payload does not match the manifest sha256"]
    except OSError as exc:
        return [f"rollback snapshot payload could not be read: {exc}"]
    return []


def snapshot_reasons(rollback: dict[str, object]) -> list[str]:
    """A snapshot must match the version 1 manifest contract, not bare existence."""
    raw = rollback.get("snapshot_path")
    if not raw:
        return ["rollback kind snapshot needs a snapshot_path to be verified"]
    manifest_path, root, reasons = _locate_snapshot_manifest(Path(str(raw)))
    if reasons:
        return reasons
    manifest, reasons = _read_snapshot_manifest(manifest_path)
    if reasons:
        return reasons
    reasons = _snapshot_identity_reasons(manifest, rollback)
    if reasons:
        return reasons
    return _snapshot_payload_reasons(manifest, manifest_path, root)


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
