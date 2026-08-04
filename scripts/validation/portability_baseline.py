"""Baseline artifact lifecycle for the portability ratchets.

Tree coverage asks whether the scan saw everything it was supposed to see.
This module asks the other half of the question: whether the artifact about to
be destroyed agrees that its replacement is an improvement, and whether that
replacement lands without collateral damage.

The two halves are separate because they fail differently. Coverage reasons
about the world, which is unbounded, so it can always be lied to by a tree
nobody thought of. The artifact comparison reasons about one file whose
contents are already known, so its blind spots are enumerable. Keeping them
apart makes the second one auditable.

Reading the predecessor is its own concern and lives in `portability_floor`.
It is the half an attacker can reach, so it is worth auditing without the
write path in the way.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

# Select the platform-specific file-locking primitive at import time so a
# bare `import fcntl` never executes on Windows (where the module does not
# exist).  Both branches are real code paths; the Windows branch is exercised
# through the injected _lock_file / _unlock_file seam in tests.
if sys.platform == "win32":
    import msvcrt

    def _lock_file(fd: int) -> None:
        """Acquire an exclusive lock on an open file descriptor (Windows)."""
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)

    def _unlock_file(fd: int) -> None:
        """Release the lock on an open file descriptor (Windows)."""
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _lock_file(fd: int) -> None:
        """Acquire an exclusive lock on an open file descriptor (POSIX)."""
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock_file(fd: int) -> None:
        """Release the lock on an open file descriptor (POSIX)."""
        fcntl.flock(fd, fcntl.LOCK_UN)

from scripts.validation.portability_floor import (
    COUNTED_SECTIONS,
    Sections,
    read_previous_sections,
)
from scripts.validation.portability_git import run_git


def _run_git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[bytes] | None:
    """Private alias of run_git kept for internal use and test mocking."""
    return run_git(repo_root, *args)

__all__ = [
    "COUNTED_SECTIONS",
    "Sections",
    "read_previous_sections",
    "refuse_dropped_entries",
    "refuse_symlinked_baseline",
    "refuse_undiffable_baseline",
    "write_baseline_json",
]

# Variables that run_git strips from the environment before calling git.
# Their presence means run_git may have hidden a real repository from git.
# Refs #4258.
_GIT_POINTER_VARS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_COMMON_DIR",
)


def _regressions(previous: Mapping[str, int], current: Mapping[str, int]) -> list[str]:
    """List paths the replacement drops or under-counts, worst first."""
    losses: list[tuple[int, str]] = []
    for path, was in previous.items():
        now = current.get(path)
        if now is None:
            losses.append((was, f"{path} (dropped, was {was})"))
        elif now < was:
            losses.append((was - now, f"{path} ({was} -> {now})"))
    return [text for _, text in sorted(losses, key=lambda item: (-item[0], item[1]))]


def refuse_dropped_entries(
    previous: Sections | None,
    current: Mapping[str, Mapping[str, int]],
    unit: str,
    allow_shrink: bool,
    problem: str | None = None,
) -> bool:
    """Refuse a write that records less debt than the baseline it replaces.

    Every coverage probe reasons about the tree. This one reasons about the
    artifact being destroyed, which is the thing the hazard is measured in. A
    partial scan, an index arranged to agree with a truncated disk, a file
    replaced by a directory, and a root that was never enumerated all converge
    on one observable: the replacement records less than its predecessor.

    Less means either fewer paths or a smaller count for the same path. A
    symlink swap keeps the path and empties the count, so a key-set comparison
    alone would wave it through.

    A reduction is legitimate when a file is deliberately removed or its
    violations are fixed, so the escape exists. It has to be named, because a
    destructive default is what turned each earlier version of this guard into
    a wipe.
    """
    if problem:
        print(
            f"Refusing to write a baseline because the one it would replace cannot "
            f"be trusted: {problem}. The existing baseline is the only record of "
            "what is already forgiven, so overwriting it while it is unreadable "
            "would discard that record silently. Restore it from git, then rerun.",
            file=sys.stderr,
        )
        return True
    if previous is None or allow_shrink:
        return False

    for name in sorted(previous):
        losses = _regressions(previous[name], current.get(name, {}))
        if not losses:
            continue
        shown = ", ".join(losses[:5])
        more = f", and {len(losses) - 5} more" if len(losses) > 5 else ""
        scope = unit if name == "files" else f"suppression records in {name}"
        print(
            f"Refusing to write a baseline that reduces {len(losses)} of "
            f"{len(previous[name])} recorded {scope}: {shown}{more}. The baseline "
            "is the only record of those violations, so reducing an entry forgives "
            "it permanently. If the reduction is deliberate, rerun with "
            "--allow-baseline-shrink.",
            file=sys.stderr,
        )
        return True
    return False


def _resolved(path: Path) -> Path | None:
    """Resolve a path without raising, None when the filesystem will not say."""
    try:
        return path.resolve()
    except OSError:
        return None


def _linked_component(baseline_path: Path, repo_root: Path) -> Path | None:
    """Return the first symlink between the repository root and the baseline.

    Checking only the leaf misses the cheaper attack. A symlinked *directory*
    anywhere on the way down redirects the write just as effectively, and it
    leaves the leaf looking like an ordinary file.
    """
    root = _resolved(repo_root)
    current = baseline_path
    for _ in range(64):
        if current.is_symlink():
            return current
        parent = current.parent
        if parent == current:
            return None
        if root is not None and _resolved(parent) == root:
            # Arriving at the root ends the walk, but the component that got us
            # here has not been tested yet. A link named `scripts` pointing at
            # the root resolves to the root and would end the walk clean, while
            # still sending the write to a path git does not track under that
            # name. Test it before stopping.
            return parent if parent.is_symlink() else None
        current = parent
    return None


def _escaping_parent(baseline_path: Path, repo_root: Path) -> Path | None:
    """Return the resolved destination when it lands outside the repository.

    A path can leave the tree without a symlink anywhere on it, by climbing
    with `..`. The symlink walk cannot see that, so the destination is checked
    on its own terms as well.
    """
    root = _resolved(repo_root)
    target = _resolved(baseline_path.parent)
    if root is None or target is None:
        return None
    if target == root or root in target.parents:
        return None
    return target


def refuse_symlinked_baseline(repo_root: Path, baseline_path: Path) -> bool:
    """Refuse to use a baseline anywhere but the real path git tracks.

    Following a symlink writes outside the path git tracks. The target is not
    the ratchet's to overwrite, and a checkout that produced a symlink here is
    not a checkout whose scan can be trusted. The whole chain from the baseline
    up to the repository root is checked, not just the final component, and a
    destination that escapes the repository is refused even when nothing on the
    way to it is a link.

    Readers refuse for a second reason. Every other check runs against the
    pathname it is handed, while reading the file follows the link, so a link
    lets the vetted name and the consumed file be two different files. The
    wording below stays neutral because both callers reach it.
    """
    linked = _linked_component(baseline_path, repo_root)
    if linked is not None:
        print(
            f"Refusing a baseline reached through a symlink: {linked}. "
            "Following it leaves the path git tracks, so the file vetted here "
            "and the file used are not guaranteed to be the same one.",
            file=sys.stderr,
        )
        return True

    escaped = _escaping_parent(baseline_path, repo_root)
    if escaped is not None:
        print(
            f"Refusing to write a baseline outside the repository: {escaped}. "
            "The ratchet only owns the artifact git tracks, and a path that "
            "leaves the tree is not that artifact.",
            file=sys.stderr,
        )
        return True

    return False


def refuse_undiffable_baseline(repo_root: Path, baseline_path: Path) -> bool:
    """Refuse when git has been told not to produce a diff for the baseline.

    Everything else in this guard rests on one claim, written down in
    `portability_floor`: the committed copy cannot change without a commit, and
    a commit is reviewable. One line in `.gitattributes` retires the second
    half. `-diff`, or the `binary` macro that expands to it, makes git and the
    forges built on it render the file as binary. The bytes are untouched, so
    this checker still parses the lowered count and agrees with it, while review
    is shown `Binary files differ` and never sees the number move.

    That is worth refusing rather than trusting review to catch, because the
    attack is two commits and only the first one shows anything. The attribute
    lands once, worded as diff-noise housekeeping, and every later lowering is
    invisible with nothing further to notice.

    Only `unset` is refused. An absent attribute reports `unspecified`, an
    explicit one reports `set`, and a named driver reports its own name; all
    three still render a textual diff. Git failing to answer is refused too,
    because a guard that cannot read the attribute cannot promise the diff.

    Outside a git repository the answer is neither, and the honest verdict is
    to allow. The asset here is a diff somebody reviews; where there is no
    repository there is no diff to suppress and no branch to land a number on,
    so refusing would block vendored copies, unpacked tarballs, and fixtures
    while protecting nothing. Every path that can carry the attack, CI above
    all, runs inside a checkout where this resolves and the guard is live.
    """
    toplevel = run_git(repo_root, "rev-parse", "--show-toplevel")
    if toplevel is None or toplevel.returncode != 0:
        # Two distinct states collapse into a non-zero exit from run_git:
        #
        # 1. "Not a repository": git answered, the path is outside any checkout,
        #    and refusal would block vendored copies and unpacked tarballs.
        #
        # 2. "Prevented from answering": the caller's environment contained
        #    GIT_DIR (or a sibling pointer variable) and run_git's GIT_* scrub
        #    removed the only thing that made the worktree discoverable. Git
        #    then reports no repository, but the repository exists and the guard
        #    is not live. Refs #4258.
        #
        # Distinguish them by checking whether the scrub removed a pointer.
        # The variables are still readable in os.environ; they were just not
        # forwarded to git.
        #
        # Presence alone is not the test. An exported-but-empty GIT_DIR names no
        # repository, so the scrub cannot have hidden one. Measured on git 2.51:
        # with GIT_DIR set to the empty string, `rev-parse --show-toplevel` in a
        # non-repository exits 128 with `fatal: not a git repository: ''` and
        # resolves nothing, exactly as it does with the variable absent.
        # Refusing on it would block vendored copies and unpacked tarballs, the
        # case the allow branch exists for.
        if any(os.environ.get(v) for v in _GIT_POINTER_VARS):
            print(
                f"Refusing to trust the baseline {baseline_path}: "
                "the environment contains GIT_DIR or a sibling pointer variable "
                "that run_git strips before calling git. "
                "Git reported no repository, but the scrub hid the one the pointer named. "
                "The guard cannot confirm the baseline is diffable without that context. "
                "Refs #4258.",
                file=sys.stderr,
            )
            return True
        return False

    proc = run_git(repo_root, "check-attr", "-z", "diff", "--", str(baseline_path))
    if proc is None or proc.returncode != 0:
        print(
            f"Refusing to trust the baseline {baseline_path}: git could not report "
            "whether it is diffable. The ratchet's only guarantee is that a lowered "
            "count shows up in review, and that cannot be confirmed here.",
            file=sys.stderr,
        )
        return True

    # `-z` emits NUL-separated (path, attribute, value) triples, so a path
    # containing a colon cannot be misread as the separator the plain format
    # uses. The value is the third field.
    fields = proc.stdout.split(b"\0")
    if len(fields) < 3:
        print(
            f"Refusing to trust the baseline {baseline_path}: git reported no diff "
            "attribute for it, so whether a lowered count would appear in review "
            "cannot be confirmed.",
            file=sys.stderr,
        )
        return True

    if fields[2] == b"unset":
        print(
            f"Refusing to use a baseline git has been told not to diff: {baseline_path}. "
            "A `-diff` or `binary` attribute renders it as binary in review, so a "
            "lowered count would land unseen while this checker still reads it. "
            "Remove the attribute, or record the debt somewhere reviewable.",
            file=sys.stderr,
        )
        return True

    return False


def _diff_attribute(repo_root: Path, path: Path) -> str | None:
    """Return the git diff attribute for path, None if git cannot answer."""
    try:
        rel = str(path.resolve().relative_to(repo_root.resolve()))
    except (OSError, ValueError):
        return None
    proc = _run_git(repo_root, "check-attr", "diff", "--", rel)
    if proc is None or proc.returncode != 0:
        return None
    # Output: "<path>: diff: <value>" where value is set/unset/unspecified/<driver>
    parts = proc.stdout.decode(errors="replace").strip().split(": ", 2)
    return parts[2] if len(parts) == 3 else None


def refuse_diff_suppressed_baseline(repo_root: Path, baseline_path: Path) -> bool:
    """Refuse to write a baseline whose diff attribute is 'unset'.

    A single .gitattributes line such as:
        scripts/validation/*_portability_baseline.json -diff
    makes git treat the baseline as binary for diff purposes. GitHub honors
    the head-branch attributes when rendering a PR, so a count lowered from
    5 to 1 shows only "Binary files differ" and the change is invisible to
    reviewers. The content is unchanged so CI still parses the real number
    and passes. Refusing to write when diff is unset means the only way to
    suppress diffs is to also break every --update-baseline run, making the
    suppression observable before it can be exploited.
    """
    attr = _diff_attribute(repo_root, baseline_path)
    if attr is None:
        print(
            f"Refusing to write a baseline: git check-attr failed for {baseline_path}. "
            "Cannot confirm the baseline is visible in code review diffs.",
            file=sys.stderr,
        )
        return True
    if attr != "unset":
        return False
    print(
        f"Refusing to write a baseline whose diff attribute is 'unset': "
        f"{baseline_path}. A .gitattributes entry is hiding this file's changes "
        "from code review. Remove the -diff override for this path, then rerun.",
        file=sys.stderr,
    )
    return True


@contextmanager
def _baseline_write_lock(
    lock_path: Path,
    *,
    _lock: Callable[[int], None] | None = None,
    _unlock: Callable[[int], None] | None = None,
) -> Iterator[None]:
    """Serialize baseline writes with a file lock.

    Uses `fcntl.flock` on POSIX and `msvcrt.locking` on Windows, selected at
    import time so the wrong module is never imported.  The lock file survives
    a crash and is re-acquired on the next run; a stale directory left by a
    SIGKILL (from the previous mkdir-based lock) is removed on entry.

    The ``_lock`` / ``_unlock`` parameters are injection seams for tests.
    Pass callables with signature ``(fd: int) -> None`` to exercise a
    specific platform path on any host.  Normal callers must not pass them.
    """
    lock_fn = _lock if _lock is not None else _lock_file
    unlock_fn = _unlock if _unlock is not None else _unlock_file

    # Remove a stale directory from the old mkdir-based lock (Issue #4237).
    if lock_path.is_dir():
        try:
            lock_path.rmdir()
        except OSError:
            pass

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        deadline = time.monotonic() + 10.0
        while True:
            try:
                lock_fn(fd)
                break
            except (OSError, PermissionError):
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"timed out waiting for baseline lock {lock_path}"
                    ) from None
                time.sleep(0.05)
        try:
            yield
        finally:
            unlock_fn(fd)
    finally:
        os.close(fd)


def _replace_atomically(baseline_path: Path, text: str) -> None:
    fd: int | None = None
    tmp: Path | None = None
    try:
        fd, tmp_name = tempfile.mkstemp(
            dir=baseline_path.parent,
            prefix=f".{baseline_path.name}.",
            suffix=".tmp",
        )
        tmp = Path(tmp_name)
        handle = os.fdopen(fd, "w", encoding="utf-8")
        fd = None
        with handle:
            handle.write(text)
        os.replace(tmp, baseline_path)
    finally:
        if fd is not None:
            os.close(fd)
        if tmp is not None:
            tmp.unlink(missing_ok=True)


def write_baseline_json(
    repo_root: Path,
    baseline_path: Path,
    payload: Mapping[str, Any],
    counted: Mapping[str, Mapping[str, int]],
    unit: str,
    allow_shrink: bool,
) -> int:
    """Write the baseline atomically, re-checking the predecessor as it lands.

    The predecessor is read twice: once by the caller, for an early refusal
    with a clear message, and once here, immediately before the replacement.
    The second read is what makes a concurrent writer observable. Truncating
    the baseline mid-scan used to make it look like there was nothing to
    protect, which turned a race into a wipe.

    Writing through a sibling temporary file and one `os.replace` keeps the
    artifact whole for every reader, and replaces a symlink at the destination
    rather than following it out of the repository.
    """
    lock_path = baseline_path.with_name(f".{baseline_path.name}.write-lock")
    try:
        with _baseline_write_lock(lock_path):
            if refuse_symlinked_baseline(repo_root, baseline_path):
                return 2

            if refuse_diff_suppressed_baseline(repo_root, baseline_path):
                return 2

            previous, problem = read_previous_sections(repo_root, baseline_path)
            if refuse_dropped_entries(previous, counted, unit, allow_shrink, problem):
                return 2

            _replace_atomically(baseline_path, json.dumps(payload, indent=2) + "\n")
    except OSError as exc:
        print(f"Could not write baseline {baseline_path}: {exc}", file=sys.stderr)
        return 2
    return 0


# 10x the largest current baseline (skill_md_portability_baseline.json at ~18 KB).
# Stated as a constant so the ceiling is re-derivable from the population it guards.
_BASELINE_SIZE_CEILING = 200_000  # bytes


def refuse_oversized_baseline(baseline_path: Path) -> bool:
    """Refuse when the baseline file exceeds the reviewability ceiling.

    Padding a baseline past the forge's diff-rendering limit hides a lowered
    count as effectively as marking it -diff. The ceiling is 10x the largest
    current baseline in the population this module guards. A legitimate machine-
    generated baseline has no reason to approach that size; only padding does.

    Unlike the diff-attribute guard, this check does not need a git repository:
    the file size is measurable from disk and the protection is useful in every
    context.

    Returns True when the baseline is too large and the caller must refuse.
    """
    try:
        size = baseline_path.stat().st_size
    except OSError:
        return False  # missing file is handled by downstream loader
    if size > _BASELINE_SIZE_CEILING:
        print(
            f"Refusing baseline {baseline_path}: file is {size} bytes, "
            f"which exceeds the reviewability ceiling of {_BASELINE_SIZE_CEILING} bytes. "
            "A legitimate baseline should not approach this size. "
            "Remove padding or regenerate from scratch.",
            file=sys.stderr,
        )
        return True
    return False
