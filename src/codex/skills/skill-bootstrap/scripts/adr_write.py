"""Where the ADR command line may write, and the create-only write itself.

Standard library only. No upstream source: align-cli wrote its ADR where it was told and
replaced any file there. ``scan --out`` must resolve outside every work tree of the scanned
repository. ``draft --out`` must be a located ADR folder of the work tree around it, or a
folder outside any work tree. Every file is published create-only, so none is replaced.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from adr_locate import is_draft_target, locate_folders
from adr_scan import ConfigError, GitError, git_bytes, git_text, refusal, stderr_text

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
    # fsdecode keeps bytes that are not UTF-8, so the next git call gets the same folder. Only
    # the newline git adds is removed: a path may end in a space.
    text = os.fsdecode(proc.stdout.removesuffix(b"\n"))
    return Path(text).resolve() if proc.returncode == 0 and text else None


def enclosing_tree(path: Path) -> Path | None:
    """The git work tree that holds ``path`` or its nearest existing ancestor, else None.

    None means no work tree encloses it. Any other git failure (the ``.git`` folder, a bare
    repository, a dubious-ownership refusal) is an error and never a scratch folder.
    """
    ancestor = next(item for item in (path, *path.parents) if item.is_dir())
    proc = git_bytes(ancestor, "rev-parse", "--path-format=absolute", "--show-toplevel")
    top = os.fsdecode(proc.stdout.removesuffix(b"\n"))
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
    proc = git_bytes(root, "worktree", "list", "--porcelain", "-z")
    if proc.returncode == 129:  # git before 2.36 has no -z
        return _admin_trees(root)
    if proc.returncode != 0:
        raise GitError(f"git worktree list --porcelain -z failed: {stderr_text(proc)}")
    items = proc.stdout.split(b"\0")
    return [
        Path(os.fsdecode(item[9:])).resolve() for item in items if item.startswith(b"worktree ")
    ]


def _admin_trees(root: Path) -> list[Path]:
    """The work trees from the files git keeps, for a git with no ``worktree list -z``.

    Without ``-z`` git prints a path literally, so a path holding a newline would cut a record
    and lose the real root. The main tree comes from ``_main_tree``. Each linked tree comes from
    ``worktrees/<id>/gitdir`` in the common dir, which holds the absolute path of that tree's
    ``.git`` file (gitrepository-layout).
    """
    common = _git_path(root, "--git-common-dir")
    if common is None:
        raise ConfigError(f"git reports no common dir for {root}; cannot list its work trees")
    trees = [_main_tree(root, common)]
    try:
        for record in sorted((common / "worktrees").glob("*/gitdir")):
            trees.append(
                Path(os.fsdecode(record.read_bytes().removesuffix(b"\n"))).parent.resolve()
            )
    except OSError as exc:
        raise ConfigError(f"cannot read the work trees of {root}: {exc}") from exc
    return trees


def _main_tree(root: Path, common: Path) -> Path:
    """The main work tree: the parent of a ``.git`` common dir, ``root`` when its own git dir is
    the common dir (``--separate-git-dir``), or the common dir of a bare repository. Else
    ConfigError: no file in the common dir names the main tree of a separate git dir."""
    if common.name == ".git":
        return common.parent
    git_dir = _git_path(root, "--git-dir")
    if git_dir is not None and same_file(git_dir, common):
        return root
    if git_text(common, "rev-parse", "--is-bare-repository").stdout.strip() == "true":
        return common
    raise ConfigError(
        f"cannot find the main work tree of {root} (its git dir {common} is kept apart);"
        " scan from the main work tree"
    )


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


def create_new(target: Path, data: bytes) -> Path | None:
    """Publish ``data`` at ``target``, never over a file that exists. Return None, or the
    temporary file that stayed behind after ``target`` was published.

    The bytes go to a hidden temporary file in the same folder, which a hard link then names
    ``target``. ``os.link`` refuses an existing name with FileExistsError, so this path is atomic
    and create-only. Where the file system has no hard links, ``target`` is created with mode
    ``x`` and written in place, so a reader can see it empty or partial; a failed write or close
    removes it. The temporary name is short, so a target name near the 255-byte limit fits.
    Removing the temporary file is a separate outcome: its failure never raises once ``target``
    exists, and never replaces an error that stopped publication.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=target.parent, prefix=".adr-", suffix=".tmp")
    try:
        _publish(fd, temp, target, data)
    except BaseException:
        _discard(temp)
        raise
    return None if _discard(temp) else Path(temp)


def _publish(fd: int, temp: str, target: Path, data: bytes) -> None:
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
    umask = os.umask(0)
    os.umask(umask)
    os.chmod(temp, 0o666 & ~umask)  # the mode ``open`` would give, not mkstemp's 0600
    try:
        os.link(temp, target)
    except FileExistsError:
        raise
    except OSError:  # no hard links on this file system (FAT, some network shares)
        _write_in_place(target, data)


def _discard(path: str) -> bool:
    """Remove ``path``; True when it is gone. A failure is returned, never raised."""
    try:
        os.unlink(path)
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return True


def _write_in_place(target: Path, data: bytes) -> None:
    """Create ``target`` with mode ``x``; a failed write or close removes it, and a failed
    removal never hides that error. The open stays outside the ``try``, so a file that was
    already there is never removed."""
    handle = open(target, "xb")
    try:
        with handle:
            handle.write(data)
    except BaseException:
        _discard(str(target))
        raise


def out_outside_repo(root: Path, out: str) -> Path:
    """Resolve ``--out`` and return it, or refuse a path inside any work tree of the scanned
    repository, a directory, or an existing file."""
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
