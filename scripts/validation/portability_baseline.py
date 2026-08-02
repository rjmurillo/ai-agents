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
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

Sections = dict[str, dict[str, int]]

COUNTED_SECTIONS = ("files", "marker_files")
"""Every baseline section that records a count somebody can regress.

`files` counts violations, where lower is better. `marker_files` counts
suppressed references, where the value must stay exact. Both are debt records,
so both need the same protection; guarding only the first leaves a writable
hole in the same artifact.
"""


def _run_git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[bytes] | None:
    env = {
        key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")
    }
    try:
        return subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            env=env,
            check=False,
        )
    except OSError:
        return None


def _was_recorded(repo_root: Path, path: Path) -> bool | None:
    """Report whether branch history has the baseline, None when git cannot answer."""
    try:
        rel = path.resolve().relative_to(repo_root.resolve())
    except (OSError, ValueError):
        return False

    proc = _run_git(repo_root, "log", "-1", "--format=%H", "HEAD", "--", str(rel))
    if proc is None:
        return None
    if proc.returncode == 0:
        return bool(proc.stdout.strip())

    refs = _run_git(repo_root, "show-ref", "--head")
    if refs is None:
        return None
    if refs.returncode == 1 and not refs.stdout:
        return False
    return None


def _coerce_counts(section: object, name: str) -> tuple[dict[str, int] | None, str | None]:
    """Convert one baseline section to counts, reporting why it is unusable."""
    if not isinstance(section, dict):
        return None, f"section {name!r} is not a JSON object"
    counts: dict[str, int] = {}
    for key, value in section.items():
        try:
            counts[str(key)] = int(value)
        except (TypeError, ValueError):
            return None, f"the count for {key!r} in {name!r} is not an integer"
    return counts, None


def read_previous_sections(
    repo_root: Path, path: Path
) -> tuple[Sections | None, str | None]:
    """Read every counted section of the baseline being replaced.

    Returns `(sections, problem)`. A problem is a reason to refuse the write.
    `(None, None)` means there is genuinely nothing to protect, which is true
    for exactly one case: a baseline that is neither on disk nor in git, so no
    debt has ever been recorded.

    Every other unreadable state fails closed. An absent-but-tracked baseline
    has been deleted, a corrupt one may be mid-merge, and an unreadable one is
    a mystery. Treating any of them as "no predecessor" would let the guard be
    disabled by damaging the very file it protects, which inverts it into a
    tool for laundering a wipe.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        recorded = _was_recorded(repo_root, path)
        if recorded is None:
            return None, "git could not determine whether branch history recorded the baseline"
        if recorded:
            return None, "git history records the baseline but it is absent from disk"
        return None, None
    except OSError as exc:
        return None, f"the baseline could not be read ({exc.strerror or exc})"

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, f"the baseline is not valid JSON ({exc.msg}, line {exc.lineno})"
    if not isinstance(data, dict):
        return None, "the baseline is not a JSON object"

    if "files" not in data:
        # The legacy flat schema is a bare path-to-count object. It is still
        # readable, so it is compared rather than refused; refusing would block
        # an honest contributor whose checkout predates the nested schema.
        counts, problem = _coerce_counts(data, "files")
        if problem:
            return None, problem
        return {"files": counts or {}}, None

    sections: Sections = {}
    for name in COUNTED_SECTIONS:
        if name not in data:
            continue
        counts, problem = _coerce_counts(data[name], name)
        if problem:
            return None, problem
        sections[name] = counts or {}
    return sections, None


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


def refuse_symlinked_baseline(baseline_path: Path) -> bool:
    """Refuse to write through a symlink at the baseline path.

    Following one writes outside the path git tracks. The target is not the
    ratchet's to overwrite, and a checkout that produced a symlink here is not
    a checkout whose scan can be trusted.
    """
    if not baseline_path.is_symlink():
        return False
    print(
        f"Refusing to write a baseline through a symlink: {baseline_path}. "
        "Following it would write outside the path git tracks, and the file it "
        "points at is not the ratchet's to overwrite.",
        file=sys.stderr,
    )
    return True


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
def _baseline_write_lock(lock_path: Path) -> Iterator[None]:
    """Serialize baseline writes with an fcntl advisory lock.

    The lock file is created (not truncated) with O_CREAT|O_RDWR so it
    survives a crash intact and flock() still acquires on the next run.
    A stale directory left by a SIGKILL is removed on entry so a single
    prior crash does not permanently wedge the lock path.
    """
    if lock_path.is_dir():
        # Stale directory left by a process that was killed before rmdir ran.
        # Remove it so the fcntl path can create the lock file.
        try:
            lock_path.rmdir()
        except OSError:
            pass

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        deadline = time.monotonic() + 10.0
        if sys.platform == "win32":
            import msvcrt

            while True:
                try:
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError(
                            f"timed out waiting for baseline lock {lock_path}"
                        ) from None
                    time.sleep(0.05)
            try:
                yield
            finally:
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError(
                            f"timed out waiting for baseline lock {lock_path}"
                        ) from None
                    time.sleep(0.05)
            try:
                yield
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
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
            if refuse_symlinked_baseline(baseline_path):
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
