"""Where the ADR command line may write, and the create-only write itself.

Standard library only. No upstream source: align-cli wrote its ADR where it was told and
replaced any file there. ``scan --out`` must resolve outside every work tree of the scanned
repository. ``draft --out`` must be a located ADR folder of the work tree around it, or a
folder outside any work tree. Every file is created with mode ``x``, so none is replaced.
"""

from __future__ import annotations

import os
from pathlib import Path

from adr_locate import is_draft_target, locate_folders
from adr_scan import ConfigError, git_bytes, git_text, refusal, stderr_text

__all__ = [
    "create_new",
    "enclosing_tree",
    "encode",
    "gate_target",
    "out_outside_repo",
    "refuse_ignored",
    "same_file",
    "work_trees",
]


def same_file(first: Path, second: Path) -> bool:
    """Do two paths name one file or folder? True for links and for case variants."""
    try:
        return os.path.samefile(first, second)
    except OSError:
        return False


def _git_path(directory: Path, flag: str) -> Path | None:
    proc = git_bytes(directory, "rev-parse", "--path-format=absolute", flag)
    text = proc.stdout.decode("utf-8", "replace").strip()
    return Path(text).resolve() if proc.returncode == 0 and text else None


def enclosing_tree(path: Path) -> Path | None:
    """The git work tree that holds ``path`` or its nearest existing ancestor, else None.

    None means no work tree encloses it. Any other git failure (the ``.git`` folder, a bare
    repository, a dubious-ownership refusal) is an error and never a scratch folder.
    """
    ancestor = next(item for item in (path, *path.parents) if item.is_dir())
    proc = git_bytes(ancestor, "rev-parse", "--path-format=absolute", "--show-toplevel")
    top = proc.stdout.decode("utf-8", "replace").strip()
    if proc.returncode == 0 and top:
        return Path(top).resolve()
    if "not a git repository" in stderr_text(proc):
        return None
    raise refusal(proc, f"git reports no work tree for {ancestor}")


def _same_repo(first: Path, second: Path) -> bool:
    """Do two work trees belong to one repository? A linked worktree shares its common dir."""
    one, two = _git_path(first, "--git-common-dir"), _git_path(second, "--git-common-dir")
    return one is not None and two is not None and same_file(one, two)


def work_trees(root: Path) -> list[Path]:
    """Every work tree of the repository at ``root``, main and linked, resolved.

    A linked work tree can hold another repository, such as a submodule. git names that one
    as the tree around a path inside it, so the common-dir check alone would miss it.
    """
    out = git_text(root, "worktree", "list", "--porcelain", "-z").stdout
    return [Path(item[9:]).resolve() for item in out.split("\0") if item.startswith("worktree ")]


def gate_target(out_dir: Path) -> tuple[Path | None, Path]:
    """``(work tree or None, folder)`` for ``draft --out``.

    The work tree that git finds around ``out_dir`` decides, whatever repository the scan
    file names. Inside a work tree, ``out_dir`` must be one of its located ADR folders that
    take drafts, and ``folder`` is that folder spelled as the work tree has it. A path with
    no work tree around it is a scratch folder.
    """
    try:
        tree = enclosing_tree(out_dir)
    except ConfigError as exc:
        raise ConfigError(f"{out_dir} is not an ADR folder that takes drafts: {exc}") from exc
    if tree is None:
        return None, out_dir
    for rel, _source in locate_folders(tree)[0]:
        folder = (tree / rel).resolve()
        if is_draft_target(rel) and same_file(folder, out_dir):
            return tree, folder
    raise ConfigError(
        f"{out_dir} is inside the repository {tree} and is not an ADR folder that takes drafts"
    )


def refuse_ignored(tree: Path, target: Path) -> None:
    # ``./`` keeps a name that starts with ``:`` from being read as pathspec magic. git refuses
    # ``--literal-pathspecs`` for check-ignore ("pathspec magic not supported by this command").
    pathspec = "./" + target.relative_to(tree).as_posix()
    proc = git_text(tree, "check-ignore", "-q", "--", pathspec, ok=(0, 1))
    if proc.returncode == 0:
        raise ConfigError(f"{target} is ignored by git; the ADR would not be committed")


def encode(text: str, target: Path) -> bytes:
    """UTF-8 bytes of ``text``. A lone surrogate fails here, before any file or folder exists."""
    try:
        return text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ConfigError(f"text for {target} cannot be written as UTF-8: {exc.reason}") from exc


def create_new(target: Path, data: bytes) -> None:
    """Create ``target`` with mode ``x``, and its folder if needed. FileExistsError if it exists.

    A failed write or close removes the file it created, so a retry never meets a partial one.
    The open stays outside the ``try``: a file that was already there is never removed.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    handle = open(target, "xb")
    try:
        with handle:
            handle.write(data)
    except BaseException:
        target.unlink(missing_ok=True)
        raise


def out_outside_repo(root: Path, out: str) -> Path:
    """Resolve ``--out`` once and refuse a path inside any work tree of the scanned repository,
    a directory, or an existing file."""
    target = Path(out).resolve()
    inside = any(tree == target or tree in target.parents for tree in (root, *work_trees(root)))
    if not inside:
        try:
            tree = enclosing_tree(target)
        except ConfigError as exc:
            raise ConfigError(f"--out {target}: {exc}") from exc
        inside = tree is not None and _same_repo(root, tree)
    if inside:
        raise ConfigError(f"--out {target} is inside the repository {root}; write it elsewhere")
    if target.is_dir():
        raise ConfigError(f"--out {target} is a directory")
    if target.exists():
        raise ConfigError(f"--out {target} already exists; it is never overwritten")
    return target
