"""Save each live run's change next to its record (issue #5768).

A human who times a correction pass needs the change to correct. The live
drivers delete the run's workdir, so each run's change is written as a
unified diff under `<output-dir>/changes/<control>/<task_id>-r<repeat>.patch`.
`eval_human_minutes_join.py` then attaches the timed minutes to the records
after the run, once a human has looked at that patch.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path

CHANGES_DIR = "changes"
#: A file larger than this is named in the patch but not diffed.
MAX_FILE_BYTES = 1_000_000

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


def _safe(part: str) -> str:
    return _UNSAFE.sub("_", part) or "_"


def patch_relpath(control: str, task_id: str, repeat: int) -> str:
    """The patch's path under the output directory, with every name part made path-safe."""
    return f"{CHANGES_DIR}/{_safe(control)}/{_safe(task_id)}-r{repeat}.patch"


def write_patch(out_dir: Path, control: str, task_id: str, repeat: int, patch: str) -> str:
    """Write `patch` under `out_dir` and return its relative path."""
    relative = patch_relpath(control, task_id, repeat)
    target = out_dir / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(patch, encoding="utf-8")
    return relative


def symlink_on_path(root: Path, relative: str) -> bool:
    """True when `root/relative` or any directory between them is a symlink.

    A link in the way sends a read outside `root` just as a linked leaf does, and
    `is_symlink()` on the leaf alone cannot see it.
    """
    step = root
    for part in Path(relative).parts:
        step = step / part
        if step.is_symlink():
            return True
    return False


def escapes_root(root: Path, relative: str) -> bool:
    """True when `root/relative` resolves outside `root`, by `..`, an absolute path, or a link.

    `symlink_on_path` walks the components it is given, so a `..` or an absolute
    path walks past the root without meeting a link. The resolved path is the
    backstop: whatever the route, a path that lands outside `root` is not read.
    """
    try:
        (root / relative).resolve().relative_to(root.resolve())
    except ValueError:
        return True
    return False


def unreadable_path(root: Path, relative: str) -> bool:
    """True when `relative` has a link on its path or resolves outside `root`."""
    return symlink_on_path(root, relative) or escapes_root(root, relative)


def _lines(root: Path, relative: str) -> tuple[list[str] | None, str]:
    """The file's lines, or `None` and a reason when it must not be diffed.

    A symlink, leaf or directory, is never followed: an agent could point one at
    a file outside the workdir, and its target would land in the saved patch. A
    path that resolves outside the workdir is not read either.
    """
    if symlink_on_path(root, relative):
        return None, "symbolic link not followed"
    if escapes_root(root, relative):
        return None, "path outside the workdir not followed"
    path = root / relative
    if not path.is_file():
        return [], ""
    if path.stat().st_size > MAX_FILE_BYTES:
        return None, f"larger than {MAX_FILE_BYTES} bytes"
    data = path.read_bytes()
    if b"\0" in data:
        return None, "binary file"
    return data.decode("utf-8", errors="replace").splitlines(keepends=True), ""


def _with_eof_markers(diff: Iterable[str]) -> Iterator[str]:
    """Yield diff lines, marking each content line that lacks a trailing newline.

    `difflib` ends every header and hunk line with a newline, so a line without
    one is a file line cut short. It can sit mid-hunk (the old side) or last
    (the new side). Either way it needs the marker, or it runs into the next line.
    """
    for line in diff:
        yield line if line.endswith("\n") else line + "\n\\ No newline at end of file\n"


def _file_diff(relative: str, before_root: Path, after_root: Path) -> str:
    before, after = before_root / relative, after_root / relative
    old, old_why = _lines(before_root, relative)
    new, new_why = _lines(after_root, relative)
    if old is None or new is None:
        return f"--- a/{relative}\n+++ b/{relative}\n# not diffed: {old_why or new_why}\n"
    diff = difflib.unified_diff(
        old,
        new,
        fromfile=f"a/{relative}" if before.is_file() else "/dev/null",
        tofile=f"b/{relative}" if after.is_file() else "/dev/null",
    )
    return "".join(_with_eof_markers(diff))


def change_patch(initial_dir: Path, workdir: Path, changed: Sequence[str]) -> str:
    """A unified diff of `changed` paths, `initial_dir` (before) against `workdir` (after).

    An added path diffs from `/dev/null` and a deleted one to `/dev/null`.
    """
    return "".join(_file_diff(relative, initial_dir, workdir) for relative in sorted(changed))
