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
the digest the gate bound, exits 1 on any difference, and with ``--github-output``
appends ``file=<path>`` so the publish step publishes the file it just verified.
Either takes ``--file`` or ``--dir``: a directory must hold exactly one ``.tgz``,
because ``npm pack`` names the file after the package version. The file is read
in chunks through a no-follow descriptor, which refuses a symlink in the final
path component. The directory is on the runner and the build job writes it once,
so the check and the publish read the same bytes: ``verify`` runs in the publish
job, directly before ``npm publish``, on the downloaded artifact.

Stdlib only: the jobs run it with bare ``python3`` (``ci-scripts.md`` MUST 18).

Exit codes (ADR-035): 0 ok, 1 the digests differ, 2 invalid arguments, a symlink,
a file that is not a regular file, or a directory without exactly one ``.tgz``,
3 the file or directory is absent or cannot be read.
"""

from __future__ import annotations

import argparse
import errno
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
_TARBALL_NAME_RE = re.compile(r"[A-Za-z0-9._@-]+\.tgz")


class TarballError(Exception):
    """The path is not a single regular tarball. A refusal, not a read failure."""


def file_digest(path: Path) -> str:
    """Return the SHA-256 of a regular file, refusing a symlink or another file type.

    Raises ``TarballError`` for a symlink or a non-regular file and ``OSError`` for
    a read failure.
    """
    if not hasattr(os, "O_NOFOLLOW") and path.is_symlink():
        raise TarballError("a symlink is not accepted")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise TarballError("a symlink is not accepted") from exc
        raise
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise TarballError("not a regular file")
        digest = hashlib.sha256()
        while chunk := os.read(descriptor, CHUNK):
            digest.update(chunk)
    finally:
        os.close(descriptor)
    return digest.hexdigest()


def single_tarball(directory: Path) -> Path:
    """Return the one ``.tgz`` in ``directory``.

    Raises ``OSError`` for a missing or unreadable directory and ``TarballError``
    when it holds none or more than one, since a promotion binds to exactly one
    tarball.
    """
    found = sorted(p for p in directory.iterdir() if p.name.endswith(".tgz"))
    if len(found) != 1:
        raise TarballError(f"expected exactly one .tgz, found {len(found)}")
    if not _TARBALL_NAME_RE.fullmatch(found[0].name):
        raise TarballError("the tarball name holds a character npm pack does not produce")
    return found[0]


def _target(args: argparse.Namespace) -> Path:
    return single_tarball(args.dir) if args.dir else args.file


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    compute = commands.add_parser("compute", help="print the digest of --file")
    verify = commands.add_parser("verify", help="compare the digest with --expected")
    verify.add_argument("--expected", required=True)
    for command in (compute, verify):
        where = command.add_mutually_exclusive_group(required=True)
        where.add_argument("--file", type=Path)
        where.add_argument("--dir", type=Path)
        command.add_argument("--github-output", type=Path, default=None)
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
        target = _target(args)
        actual = file_digest(target)
    except TarballError as exc:
        print(f"[FAIL] tarball digest: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    except OSError as exc:
        print(f"[BLOCKED] tarball digest: cannot read, {type(exc).__name__}", file=sys.stderr)
        return EXIT_EXTERNAL
    if args.command == "verify":
        if actual != args.expected:
            print(
                f"[FAIL] tarball digest: {actual} does not match the bound {args.expected}",
                file=sys.stderr,
            )
            return EXIT_MISMATCH
        print(f"[PASS] tarball digest: {actual} matches the bound digest")
        return _write_output(args, f"file={target}")
    print(f"tarball digest: {actual}")
    return _write_output(args, f"digest={actual}")


def _write_output(args: argparse.Namespace, line: str) -> int:
    if args.github_output is not None:
        with args.github_output.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
