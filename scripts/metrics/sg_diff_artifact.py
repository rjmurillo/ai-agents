"""Content-addressed diff artifact store for the security-guidance prompt (#5856).

Evaluation model only. Not wired to any hook, skill, or runtime path. This
module owns the artifact store: ``write_artifact``, ``prune``, and ``resolve``.
``scripts/metrics/sg_diff_producer.py`` builds prompts and serves the
read-time tool on top of it. ``scripts/metrics/sg_diff_reference.py`` owns
prompt building and byte capping, and its docstring holds the citations this
evaluation mirrors from the plugin. The artifact reference itself is original
to this harness: the plugin has no such mechanism, so nothing upstream exists
for it to diverge from.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import re
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

# A repo_id or artifact sha256 is a hex sha256 digest, always exactly 64
# lowercase hex characters. Validating against this pattern before building
# any filesystem path from a reference field is the CWE-22 (path traversal)
# defense in `resolve`: no digit-and-a-to-f string can encode `../`.
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    """A content-addressed pointer to a capped diff artifact on disk."""

    sha256: str
    size: int
    repo_id: str
    head: str
    path_order_sha256: str
    truncated_bytes: int


@dataclass(frozen=True, slots=True)
class Resolution:
    """The result of resolving an :class:`ArtifactRef` against the store.

    ``reason`` is always one of: ``ok``, ``missing``, ``unreadable``,
    ``tampered``, ``cross_repo``, ``stale``, ``invalid_ref``.
    """

    ok: bool
    text: str | None
    reason: str


def _artifact_path(store_dir: str | Path, repo_id: str, sha256: str) -> Path:
    return Path(store_dir) / repo_id / f"{sha256}.diff"


def write_artifact(
    store_dir: str | Path,
    repo_id: str,
    head: str,
    diff_text: str,
    paths: Sequence[str],
    truncated_bytes: int,
) -> ArtifactRef:
    """Write ``diff_text`` content-addressed at ``store_dir/<repo_id>/<sha256>.diff``.

    Writing the same ``diff_text`` twice for the same ``repo_id`` produces the
    same sha256 and therefore the same path; the second write is an idempotent
    overwrite of identical bytes at the same content address, not a duplicate
    artifact. The repo directory is created at 0o700 and the artifact file at
    0o600. The write is atomic: content lands in a same-directory temp file
    first, then ``os.replace`` swaps it into place, so a reader never observes
    a partially written artifact.
    """
    diff_bytes = diff_text.encode()
    sha256 = hashlib.sha256(diff_bytes).hexdigest()
    size = len(diff_bytes)
    path_order_sha256 = hashlib.sha256("\n".join(paths).encode()).hexdigest()

    repo_dir_path = Path(store_dir) / repo_id
    repo_dir_path.mkdir(parents=True, exist_ok=True)
    os.chmod(repo_dir_path, 0o700)

    target = repo_dir_path / f"{sha256}.diff"
    fd, tmp_name = tempfile.mkstemp(dir=repo_dir_path, prefix=".tmp-", suffix=".diff")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(diff_bytes)
        os.chmod(tmp_name, 0o600)
        os.replace(tmp_name, target)
    except OSError:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise

    return ArtifactRef(
        sha256=sha256,
        size=size,
        repo_id=repo_id,
        head=head,
        path_order_sha256=path_order_sha256,
        truncated_bytes=truncated_bytes,
    )


def prune(store_dir: str | Path, max_age_s: float) -> int:
    """Delete artifacts under ``store_dir`` older than ``max_age_s``. Returns the count removed."""
    store_path = Path(store_dir)
    if not store_path.is_dir():
        return 0
    now = time.time()
    removed = 0
    for repo_entry in store_path.iterdir():
        if not repo_entry.is_dir():
            continue
        for artifact in repo_entry.glob("*.diff"):
            if artifact.is_symlink():
                continue
            try:
                age = now - artifact.stat().st_mtime
            except OSError:
                continue
            if age <= max_age_s:
                continue
            with contextlib.suppress(OSError):
                artifact.unlink()
                removed += 1
    return removed


def resolve(
    store_dir: str | Path,
    ref: ArtifactRef,
    expected_repo_id: str,
    expected_head: str,
) -> Resolution:
    """Verify and read back an :class:`ArtifactRef`.

    Checks run cheapest and most security-sensitive first: an ``invalid_ref``
    (malformed hex, the CWE-22 guard) is rejected before any path is built
    from the reference's fields, then ``cross_repo`` and ``stale`` are
    rejected from the reference's own fields alone, before any filesystem
    access. Only a reference that passes all three reaches disk.
    """
    if not _HEX64_RE.match(ref.sha256) or not _HEX64_RE.match(ref.repo_id):
        return Resolution(ok=False, text=None, reason="invalid_ref")
    if ref.repo_id != expected_repo_id:
        return Resolution(ok=False, text=None, reason="cross_repo")
    if ref.head != expected_head:
        return Resolution(ok=False, text=None, reason="stale")

    target = _artifact_path(store_dir, ref.repo_id, ref.sha256)
    if target.is_symlink():
        return Resolution(ok=False, text=None, reason="unreadable")
    if not target.exists():
        return Resolution(ok=False, text=None, reason="missing")
    try:
        raw = target.read_bytes()
    except OSError:
        return Resolution(ok=False, text=None, reason="unreadable")

    if len(raw) != ref.size or hashlib.sha256(raw).hexdigest() != ref.sha256:
        return Resolution(ok=False, text=None, reason="tampered")
    return Resolution(ok=True, text=raw.decode("utf-8", errors="replace"), reason="ok")
