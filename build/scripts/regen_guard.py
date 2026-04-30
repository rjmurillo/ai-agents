#!/usr/bin/env python3
"""NO-REGEN sentinel detection for build-pipeline generators (REQ-003-008).

A target file is "protected" when any of the following hold:

1. The file contains the literal token ``NO-REGEN`` inside a markdown HTML
   comment (``<!-- NO-REGEN -->``) anywhere in the first 4 KiB.
2. The file contains a Python/shell-style comment ``# NO-REGEN`` in the
   first 4 KiB.
3. A sidecar file with the same path plus ``.noregen`` exists next to it
   (e.g. ``foo.agent.md.noregen``). The sidecar's content is ignored;
   presence alone marks the target as protected.

Generators MUST consult :func:`is_protected` before overwriting or
deleting a file. When protected, generators emit a NOTICE to the audit
log and skip the operation.

Public API:
    is_protected(path) -> bool
    REASON_*  string constants used in audit messages

The detection scope is intentionally cheap (4 KiB head only). A protected
file that buries the marker past that boundary will be regenerated; the
sidecar form is the supported escape hatch when the marker cannot live in
the file head.
"""

from __future__ import annotations

from pathlib import Path

REASON_HTML_COMMENT = "html-comment"
REASON_HASH_COMMENT = "hash-comment"
REASON_SIDECAR = "sidecar"

_HEAD_BYTES = 4096
_HTML_TOKEN = b"<!-- NO-REGEN"
_HASH_TOKEN = b"# NO-REGEN"


def is_protected(path: Path) -> bool:
    """Return True when ``path`` carries a NO-REGEN sentinel.

    Missing files are not protected (nothing to preserve). Read errors
    fall through to "not protected" rather than blocking the build; a
    sidecar provides a deterministic escape hatch when content scanning
    is impractical.
    """
    return _detect_reason(path) is not None


def detect_reason(path: Path) -> str | None:
    """Return the reason string, or ``None`` when the file is unprotected.

    Useful for audit-log messaging where the exact sentinel that triggered
    the skip matters.
    """
    return _detect_reason(path)


def _detect_reason(path: Path) -> str | None:
    sidecar = path.with_suffix(path.suffix + ".noregen")
    if sidecar.exists():
        return REASON_SIDECAR
    if not path.is_file():
        return None
    try:
        with path.open("rb") as handle:
            head = handle.read(_HEAD_BYTES)
    except OSError:
        return None
    if _HTML_TOKEN in head:
        return REASON_HTML_COMMENT
    # Match `# NO-REGEN` only at start-of-line / after whitespace to avoid
    # accidental matches inside string literals like "x# NO-REGEN".
    for line in head.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(_HASH_TOKEN):
            return REASON_HASH_COMMENT
    return None
