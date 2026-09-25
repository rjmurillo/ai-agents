"""Prompt producer and read-time tool for the diff artifact model (#5856).

Evaluation model only. Not wired to any hook, skill, or runtime path. This
module sits on top of ``scripts/metrics/sg_diff_artifact.py`` (the artifact
store): ``build_referenced_prompt`` is the reference-mode prompt shape,
``produce_prompt`` writes and re-resolves an artifact before it hands out a
reference, and ``serve_artifact_tool`` re-verifies at read time. Every failure
path returns the exact inline prompt or inline diff text.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from scripts.metrics.sg_diff_artifact import ArtifactRef, resolve, write_artifact
from scripts.metrics.sg_diff_reference import (
    DEFAULT_PER_FILE_BYTES,
    DEFAULT_TOTAL_BYTES,
    assemble_prompt,
    capped_diff_text,
)


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
    reference failure at review time. The write itself can also fail: a full
    disk or a permission error raises ``OSError`` from ``write_artifact``'s
    ``os.replace``/``mkdir``, and a malformed ``repo_id`` raises ``ValueError``
    from its ``_HEX64_RE`` guard. Both fall back to the same exact inline
    prompt, with ``fallback_reason="write_failed"``, so every failure path
    (write or resolve) returns the exact inline prompt as the module
    docstring promises; nothing here ever propagates a write failure to the
    caller.
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

    try:
        ref = write_artifact(
            store_dir, repo_id, head, diff_text, list(touched_paths), truncated_bytes
        )
    except (OSError, ValueError):
        return inline_prompt, ProducerOutcome(
            mode_used="inline", fallback_reason="write_failed", ref=None
        )
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
