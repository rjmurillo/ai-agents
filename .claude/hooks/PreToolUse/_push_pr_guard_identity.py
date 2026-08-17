"""Trusted-file identity for the push-pr identity guard (issue #4764).

Owns every digest decision: hashing a candidate file, comparing two resolved
executables by content, resolving the runtime ``new_pr.py`` next to the guard,
and verifying the pinned bundle before the guard allows an invocation.

The pinned digests live here. They gate every push-pr invocation, so a stale
value wedges the command with no other signal; ``tests/hooks/
test_push_pr_guard_bundle.py`` recomputes them against the shipped files.
"""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path
from typing import BinaryIO

from _push_pr_guard_lex import GuardViolationError

_SCRIPT_RELATIVE_PATH = Path("skills/github/scripts/pr/new_pr.py")


_DIGEST_CHUNK_BYTES = 1 << 20


_TRUSTED_NEW_PR_SHA256 = "913a55ee2c0b748295e54f655f7ce42c9a25f6538ae41f3cac237be4954d6aff"


_TRUSTED_VALIDATE_PR_DESCRIPTION_SHA256 = (
    "82c6c36bea619c676c013581e51b92a832c1c171d890baf20e50d858276aed81"
)


_TRUSTED_PR_VALIDATIONS_SHA256 = "7cef9a148dc1ab64d316fa7c13f7026f77a66fd9c87cfb7d737e8d308fcacd90"
_TRUSTED_NEW_PR_VALIDATIONS_SHA256 = (
    "0ee9db4082831582babac175f1e529b53cc6ba200378a60e4eaca773445fc7d9"
)
_TRUSTED_PREPARE_PR_BODY_SHA256 = "7040677820b84968704534ea6673d62306abc21e0fa638fa49f687dc9b78bc56"


def _sha256_digest(stream: BinaryIO) -> hashlib._Hash:
    """Hash a binary stream without ``hashlib.file_digest``.

    ``hashlib.file_digest`` landed in Python 3.11, but the generated hook
    launchers accept any interpreter at 3.10 or newer:

        "$_c" -I -c "import sys;print(int(sys.version_info>=(3,10)))"

    Calling it on 3.10 raised ``AttributeError`` and the guard exited 1, which
    a PreToolUse host treats as a hook error rather than a block, so the
    identity gate silently stopped enforcing on that interpreter. Reproduced on
    cpython 3.10.20 against the canonical push-pr command (issue #4825).
    """
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(_DIGEST_CHUNK_BYTES), b""):
        digest.update(chunk)
    return digest


def _same_executable_content(left: Path, right: Path) -> bool:
    try:
        if left.samefile(right):
            return True
        if left.stat().st_size != right.stat().st_size:
            return False
        with left.open("rb") as left_stream, right.open("rb") as right_stream:
            return _sha256_digest(left_stream).digest() == _sha256_digest(right_stream).digest()
    except OSError:
        return False


def _matches_trusted_file(
    candidate: Path,
    runtime_script: Path,
    trusted: os.stat_result,
) -> bool:
    """Compare one operand against the trusted script with a single stat."""
    try:
        info = candidate.stat()
    except OSError:
        return False
    if not stat.S_ISREG(info.st_mode):
        return False
    if (info.st_dev, info.st_ino) == (trusted.st_dev, trusted.st_ino):
        return True
    if info.st_size != trusted.st_size:
        return False
    return _same_executable_content(candidate, runtime_script)


def _regular_resolved_file(path: Path) -> Path | None:
    if path.is_symlink() or not path.is_file():
        return None
    try:
        return path.resolve(strict=True)
    except OSError:
        return None


def _require_trusted_digest(path: Path, expected: str, label: str) -> None:
    try:
        with path.open("rb") as stream:
            actual = _sha256_digest(stream).hexdigest()
    except OSError as exc:
        raise GuardViolationError(f"{label} is unreadable") from exc
    if actual != expected:
        raise GuardViolationError(f"{label} does not match the trusted plugin copy")


def _validate_runtime_bundle(script: Path) -> None:
    """Verify every file new_pr.py executes or imports, as one unit.

    ``pr_validations.py`` joined the bundle in issue #4764 when new_pr.py was
    split for cohesion. It MUST be pinned here: new_pr.py loads it by absolute
    path at import time, so an unpinned sibling would be an unverified code
    path inside a script whose whole purpose here is to be verified. Pinning it
    keeps the split from widening the trusted surface.
    """
    _require_trusted_digest(script, _TRUSTED_NEW_PR_SHA256, "new_pr.py")
    for name, expected in (
        ("validate_pr_description.py", _TRUSTED_VALIDATE_PR_DESCRIPTION_SHA256),
        ("pr_validations.py", _TRUSTED_PR_VALIDATIONS_SHA256),
        ("new_pr_validations.py", _TRUSTED_NEW_PR_VALIDATIONS_SHA256),
        ("prepare_pr_body.py", _TRUSTED_PREPARE_PR_BODY_SHA256),
    ):
        helper = _regular_resolved_file(script.parent / name)
        if helper is None:
            raise GuardViolationError(f"{name} is missing, unreadable, or a symlink")
        _require_trusted_digest(helper, expected, name)


def _runtime_script() -> Path | None:
    runtime_root = Path(__file__).resolve().parents[2]
    return _regular_resolved_file(runtime_root / _SCRIPT_RELATIVE_PATH)
