#!/usr/bin/env python3
"""Compute and verify the SHA-256 digest of the npm tarball a promotion binds to.

ADR-113 decision 4. Quoted from
``.project-toolkit/architecture/ADR-113-promotion-gate-evidence-and-exceptions.md``:

    "The tarball is built once, in a single job, before the gate runs. The
    publish job downloads that exact file, recomputes its digest, and compares
    it with the manifest immediately before `npm publish`, so nothing can change
    between the check and the publish."

``compute`` prints the digest and, with ``--github-output``, appends
``digest=<hex>`` for the build job. ``verify`` recomputes it and compares it with
the digest the gate bound, and exits 1 on any difference. The file is read in
chunks through a no-follow descriptor, so a symlink is refused.

Stdlib only: the jobs run it with bare ``python3`` (``ci-scripts.md`` MUST 18).

Exit codes (ADR-035): 0 ok, 1 the digests differ, 2 invalid arguments or a file
that is not a regular file, 3 the file cannot be read.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import stat
import sys
from collections.abc import Sequence
from pathlib import Path

EXIT_OK, EXIT_MISMATCH, EXIT_CONFIG, EXIT_EXTERNAL = 0, 1, 2, 3
CHUNK = 1 << 20
_DIGEST_RE = re.compile(r"[0-9a-f]{64}")


def file_digest(path: Path) -> str:
    """Return the SHA-256 of a regular file, refusing a symlink or another file type.

    Raises ``OSError`` for a symlink, a non-regular file, or a read failure.
    """
    if path.is_symlink():
        raise OSError("a symlink is not accepted")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    descriptor = os.open(path, flags)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise OSError("not a regular file")
        digest = hashlib.sha256()
        while chunk := os.read(descriptor, CHUNK):
            digest.update(chunk)
    finally:
        os.close(descriptor)
    return digest.hexdigest()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    compute = commands.add_parser("compute", help="print the digest of --file")
    compute.add_argument("--file", type=Path, required=True)
    compute.add_argument("--github-output", type=Path, default=None)
    verify = commands.add_parser("verify", help="compare the digest of --file with --expected")
    verify.add_argument("--file", type=Path, required=True)
    verify.add_argument("--expected", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. Returns an ADR-035 exit code."""
    args = _parser().parse_args(argv)
    if args.command == "verify" and not _DIGEST_RE.fullmatch(args.expected):
        print(
            "[FAIL] tarball digest: --expected must be 64 lowercase hex characters", file=sys.stderr
        )
        return EXIT_CONFIG
    try:
        actual = file_digest(args.file)
    except FileNotFoundError:
        print("[BLOCKED] tarball digest: the file does not exist", file=sys.stderr)
        return EXIT_EXTERNAL
    except OSError as exc:
        print(f"[FAIL] tarball digest: {type(exc).__name__}", file=sys.stderr)
        return EXIT_CONFIG
    if args.command == "verify":
        if actual != args.expected:
            print(f"[FAIL] tarball digest: {actual} does not match the bound {args.expected}")
            return EXIT_MISMATCH
        print(f"[PASS] tarball digest: {actual} matches the bound digest")
        return EXIT_OK
    print(f"tarball digest: {actual}")
    if args.github_output is not None:
        with args.github_output.open("a", encoding="utf-8") as handle:
            handle.write(f"digest={actual}\n")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
