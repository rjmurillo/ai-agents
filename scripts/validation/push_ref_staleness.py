"""Pre-push ref staleness gate (issue #3862).

Reads git pre-push stdin (lines of ``local_ref local_sha remote_ref
remote_sha``) and verifies that each remote ref still points to the same
commit it did when the hook started.  If the remote moved during the gate
suite the push would fail anyway, but this script surfaces the reason in a
clear message and exits early instead of letting git emit a cryptic
"rejected" error after 6+ minutes of gate work.

Exit codes:
  0 -- all remote refs unchanged; safe to push
  2 -- malformed stdin or unexpected argument
  3 -- at least one remote ref advanced (race detected)
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass

from scripts.validation.object_id import ZERO_SHA_LENGTHS, is_full_object_id

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _PushRef:
    local_ref: str
    local_sha: str
    remote_ref: str
    remote_sha: str


def _is_zero_sha(sha: str) -> bool:
    return len(sha) in ZERO_SHA_LENGTHS and not sha.strip("0")


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _parse_stdin(lines: list[str]) -> list[_PushRef]:
    refs: list[_PushRef] = []
    for i, line in enumerate(lines, start=1):
        parts = line.split()
        if len(parts) != 4:
            print(
                f"push_ref_staleness: malformed line {i}: expected 4 fields, got {len(parts)}",
                file=sys.stderr,
            )
            sys.exit(2)
        local_ref, local_sha, remote_ref, remote_sha = parts
        if not is_full_object_id(local_sha) or not is_full_object_id(remote_sha):
            print(
                f"push_ref_staleness: line {i}: non-hex or short SHA",
                file=sys.stderr,
            )
            sys.exit(2)
        refs.append(_PushRef(local_ref, local_sha, remote_ref, remote_sha))
    return refs


# ---------------------------------------------------------------------------
# Remote ref resolution
# ---------------------------------------------------------------------------


def _current_remote_sha(remote_name: str, remote_ref: str) -> str | None:
    """Return the current commit SHA for ``remote_ref`` on ``remote_name``.

    Returns ``None`` when the ref does not exist on the remote.
    Raises ``RuntimeError`` when ``git ls-remote`` fails unexpectedly.
    """
    result = subprocess.run(
        ["git", "ls-remote", remote_name, remote_ref],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git ls-remote {remote_name} {remote_ref} failed: {result.stderr.strip()}"
        )
    line = result.stdout.strip()
    if not line:
        return None
    return line.split()[0]


# ---------------------------------------------------------------------------
# Main gate
# ---------------------------------------------------------------------------


def check_refs(
    refs: list[_PushRef],
    remote_name: str = "origin",
) -> bool:
    """Check each ref for staleness.  Return True when all pass, False otherwise."""
    stale: list[tuple[str, str, str]] = []
    for ref in refs:
        if _is_zero_sha(ref.local_sha):
            continue
        if _is_zero_sha(ref.remote_sha):
            continue
        try:
            current = _current_remote_sha(remote_name, ref.remote_ref)
        except RuntimeError as exc:
            print(f"push_ref_staleness: WARNING: {exc}", file=sys.stderr)
            sys.exit(3)

        if current is None:
            continue
        if current != ref.remote_sha:
            stale.append((ref.remote_ref, ref.remote_sha, current))

    if stale:
        for rref, expected, actual in stale:
            print(
                f"push_ref_staleness: STALE: {rref} advanced during hook run "
                f"(expected {expected[:12]}, got {actual[:12]}). "
                "Fetch and rebase before retrying.",
                file=sys.stderr,
            )
        return False
    return True


def main() -> None:
    if len(sys.argv) > 1:
        print(f"push_ref_staleness: unexpected arguments: {sys.argv[1:]}", file=sys.stderr)
        sys.exit(2)

    raw = sys.stdin.read().splitlines()
    refs = _parse_stdin(raw)
    if not refs:
        return

    if not check_refs(refs):
        sys.exit(3)


if __name__ == "__main__":
    main()
