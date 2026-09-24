"""Content-addressed diff artifact store for the security-guidance prompt (#5856).

Evaluation model only. Not wired to any hook, skill, or runtime path. Split
out of ``scripts/metrics/sg_diff_reference.py`` (the prompt-building and
byte-capping module) under the taste-lints file-size gate: this module owns
the artifact store itself (write, prune, resolve) and the two callers that sit
on top of it (``produce_prompt``, ``serve_artifact_tool``), plus
``build_referenced_prompt``, the reference-mode prompt shape. See that
module's docstring for the canonical-source citations this evaluation as a
whole mirrors (``review_api.cap_diff_for_prompt``, ``llm.py``'s inline
``user_prompt``); nothing in this module independently mirrors plugin code,
it reuses ``sg_diff_reference.assemble_prompt`` and
``sg_diff_reference.capped_diff_text`` so both prompt shapes share one
header/footer implementation. The content-addressed artifact reference itself
(``ArtifactRef``, the on-disk store, re-verify-then-serve) is original to this
evaluation harness: the plugin has no such mechanism today, so there is
nothing upstream for it to diverge from.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import re
import sys
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from scripts.metrics.sg_diff_reference import (
    DEFAULT_PER_FILE_BYTES,
    DEFAULT_TOTAL_BYTES,
    assemble_prompt,
    capped_diff_text,
)

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


def build_referenced_prompt(
    touched_paths: Sequence[str],
    ref: ArtifactRef,
    context_note: str = "",
) -> str:
    """The reference-mode prompt: same shape as ``sg_diff_reference.build_inline_prompt``,
    with the diff body replaced by a pointer block naming the artifact and instructing
    the model to fetch it via the ``read_diff_artifact`` tool before reviewing.
    The authoritative-diff ``context_note`` is preserved verbatim, at the same
    position, so REQ-7 (checkout-mismatch warning survives) holds for both modes.
    """
    pointer_block = (
        "=== DIFF ARTIFACT (fetch before reviewing) ===\n"
        f"sha256: {ref.sha256}\n"
        f"size_bytes: {ref.size}\n"
        "paths:\n"
        + "\n".join(f"  - {p}" for p in touched_paths)
        + "\n\nCall the read_diff_artifact tool with sha256="
        f'"{ref.sha256}" to fetch the exact capped diff before reviewing. '
        "Do not guess its contents; the tool returns the authoritative text."
    )
    return assemble_prompt(touched_paths, pointer_block, context_note)


@dataclass(frozen=True, slots=True)
class ProducerOutcome:
    """What :func:`produce_prompt` actually did.

    ``mode_used`` is ``"inline"`` or ``"referenced"``. ``fallback_reason`` is
    ``None`` when ``mode_used == "referenced"`` (or when the caller asked for
    ``"inline"`` outright), and is the :class:`Resolution` reason otherwise.
    """

    mode_used: str
    fallback_reason: str | None
    ref: ArtifactRef | None


def produce_prompt(
    mode: str,
    store_dir: str | Path,
    repo_id: str,
    head: str,
    touched_paths: Sequence[str],
    diff_files: Sequence[tuple[str, str]],
    context_note: str = "",
    *,
    per_file_bytes: int = DEFAULT_PER_FILE_BYTES,
    total_bytes: int = DEFAULT_TOTAL_BYTES,
) -> tuple[str, ProducerOutcome]:
    """Produce a review prompt in ``mode`` ("inline" or "referenced").

    "referenced" writes the artifact, then immediately re-resolves it under
    the same expectations a later reader would apply. Any resolution failure
    (REQ-5: missing, unreadable, stale, cross-repository, tampered) falls back
    to the EXACT inline prompt, so a caller never has to special-case a
    reference failure at review time.
    """
    if mode not in ("inline", "referenced"):
        raise ValueError(
            f"produce_prompt: unknown mode {mode!r}; expected 'inline' or 'referenced'"
        )

    diff_text, truncated_bytes = capped_diff_text(
        diff_files, per_file_bytes=per_file_bytes, total_bytes=total_bytes
    )
    inline_prompt = assemble_prompt(touched_paths, diff_text, context_note)
    if mode == "inline":
        return inline_prompt, ProducerOutcome(mode_used="inline", fallback_reason=None, ref=None)

    ref = write_artifact(store_dir, repo_id, head, diff_text, list(touched_paths), truncated_bytes)
    resolution = resolve(store_dir, ref, repo_id, head)
    if not resolution.ok:
        return inline_prompt, ProducerOutcome(
            mode_used="inline", fallback_reason=resolution.reason, ref=ref
        )
    referenced_prompt = build_referenced_prompt(touched_paths, ref, context_note)
    return referenced_prompt, ProducerOutcome(mode_used="referenced", fallback_reason=None, ref=ref)


def serve_artifact_tool(
    store_dir: str | Path,
    ref: ArtifactRef,
    expected_repo_id: str,
    expected_head: str,
    inline_diff_text: str,
) -> str:
    """The ``read_diff_artifact`` tool handler: re-verify, then serve.

    Re-verification happens at read time rather than trusting the write-time
    :class:`ArtifactRef`, because time has passed since the prompt was built
    (retention pruning, a concurrent tamper, a stale reference reused across
    sessions). On any resolution failure this returns ``inline_diff_text``
    unchanged (fail-safe: the reviewer always gets a diff, never an error),
    and reports which outcome occurred on stderr so a caller inspecting
    output can tell "ok" from a named fallback reason without parsing the
    returned text.
    """
    resolution = resolve(store_dir, ref, expected_repo_id, expected_head)
    if resolution.ok and resolution.text is not None:
        print(f"sg_diff_artifact: read_diff_artifact ok sha256={ref.sha256}", file=sys.stderr)
        return resolution.text
    print(
        f"sg_diff_artifact: read_diff_artifact fallback reason={resolution.reason} "
        f"sha256={ref.sha256}",
        file=sys.stderr,
    )
    return inline_diff_text
