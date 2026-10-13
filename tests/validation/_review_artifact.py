"""Shared builders for review-marker commits that carry a review report (issue #6438).

A marker is an empty commit whose body holds the review report and whose
trailers name the reviewed tip and the report digest. These helpers write that
message with their own hashing, so the validators are not checked against the
code under test.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

BEGIN = "--- review report ---"
END = "--- end review report ---"


def report_lines(axes: str, sha: str, verdict: str = "PASS") -> list[str]:
    """Return the report rows for a comma-separated ``axes`` list."""
    return [f"Reviewed-SHA: {sha}", *(f"{axis}: {verdict}" for axis in axes.split(","))]


def digest_of(lines: list[str]) -> str:
    """Return ``sha256:<hex>`` over the lines, one per line, LF-ended."""
    payload = "".join(f"{line}\n" for line in lines).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def marker_message(
    axes: str,
    sha: str,
    *,
    report: list[str] | None = None,
    digest: str | None = None,
    trailer_sha: str | None = None,
) -> str:
    """Return a full marker commit message.

    ``report`` overrides the rows, ``digest`` overrides the digest trailer, and
    ``trailer_sha`` overrides the SHA in the ``Reviewed-By`` trailer.
    """
    rows = report if report is not None else report_lines(axes, sha)
    value = digest if digest is not None else digest_of(rows)
    return (
        "review: /review PASS marker\n\n"
        + "\n".join([BEGIN, *rows, END])
        + f"\n\nReviewed-By: /review@{axes} on {trailer_sha or sha}\n"
        + f"Review-Artifact: {value}\n"
    )


def commit_message(repo: Path, message: str) -> None:
    """Write an empty commit with ``message`` on ``repo`` HEAD."""
    subprocess.run(  # subprocess-encoding: strict-ok
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=Test User",
            "-c",
            "user.email=test@example.com",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-q",
            "--allow-empty",
            "-F",
            "-",
        ],
        input=message,
        text=True,
        encoding="utf-8",
        check=True,
        capture_output=True,
    )


def commit_marker(
    repo: Path,
    axes: str,
    sha: str,
    *,
    report: list[str] | None = None,
    digest: str | None = None,
    trailer_sha: str | None = None,
) -> None:
    """Write an empty marker commit on ``repo`` HEAD."""
    message = marker_message(axes, sha, report=report, digest=digest, trailer_sha=trailer_sha)
    commit_message(repo, message)
