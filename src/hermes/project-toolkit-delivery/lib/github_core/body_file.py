"""The strict body-file reader every body-file script shares (issue #6667).

``github_core.validation.read_body_file_text`` delegates here. The root probes
are read through the ``validation`` module at call time, so a test that stubs
``validation._candidate_temp_roots`` or ``_candidate_git_dir_roots`` reaches
this reader too.
"""

from __future__ import annotations

import errno
import os
import re
import stat
import sys
from pathlib import Path

from . import validation

# A file new_pr.py --prepare-body-file allocates. It must stay mode 600.
_PREPARED_BODY_NAME = re.compile(r"^pr-body-[A-Za-z0-9_-]+\.md$")
# The one dot directory a body may live in below the repo root: the scratch
# directory that --prepare-body-file and the worktree scratch rule use.
_TRUSTED_DOT_PREFIX = (".project-toolkit", "scratch")
_GIT_CONFIG_NAMES = frozenset({"config", "config.worktree"})
_WORLD_WRITE = 0o002
_GROUP_WRITE = 0o020
_GROUP_OR_WORLD_WRITE = 0o022
_GROUP_OR_WORLD_SEARCH = 0o011
_GROUP_OR_WORLD_ANY = 0o077
# Mode bits and owners mean nothing on Windows, so those checks run on POSIX.
_POSIX_PERMISSIONS = os.name != "nt" and hasattr(os, "getuid")
_HAS_DIR_FD = hasattr(os, "O_DIRECTORY") and os.open in os.supports_dir_fd
# Errors an O_NOFOLLOW open returns when a path component is a symlink:
# ELOOP on Linux and macOS, EMLINK on FreeBSD, ENOTDIR for a non-directory.
_LINK_ERRNOS = frozenset({errno.ELOOP, errno.EMLINK, errno.ENOTDIR})
_IS_WINDOWS = os.name == "nt"
# NTFS reaches one file under several names: an 8.3 short name (GIT~1), a
# trailing dot or space (config.), or a stream (notes.md:evil). Any of them
# would slip past a name check, so a component that looks like one is refused
# on every platform.
_NTFS_SHORT_NAME = re.compile(r"~\d")
_FILE_ATTRIBUTE_REPARSE_POINT = 0x400


def _is_within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _working_root() -> Path | None:
    """Return the repo root, the working directory when git finds no repo, else None.

    This mirrors the base :func:`is_safe_file_path` uses when it gets none.
    """
    from .repo import REPO_ROOT_NOT_A_REPO, resolve_repo_root

    repo_root, reason = resolve_repo_root()
    if repo_root is not None:
        return Path(repo_root).resolve()
    if reason == REPO_ROOT_NOT_A_REPO:
        return Path.cwd().resolve()
    return None


def _common_git_dir(git_dir: Path) -> Path | None:
    """Return the common dir a linked worktree's git dir names, else None.

    It is read from the ``commondir`` file, so no extra git process runs.
    """
    try:
        common = (git_dir / "commondir").read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return None
    return (git_dir / common).resolve() if common else None


def _linked_worktree_git_dirs() -> list[Path]:
    """Return the git dir only when it belongs to a linked worktree.

    The git-dir reply flow is for linked worktrees, whose git dir is the
    worktree-specific ``.git/worktrees/<name>/``. In a primary clone the git dir
    is the common dir that holds ``config``, so it never qualifies.
    """
    found: list[Path] = []
    for raw in validation._candidate_git_dir_roots():
        git_dir = Path(raw)
        common = _common_git_dir(git_dir)
        if common is not None and common != git_dir:
            found.append(git_dir)
    return found


def _git_dirs_to_refuse(work_root: Path | None) -> list[Path]:
    """Return the git dir, its common dir, and ``<repo>/.git`` when it is a directory."""
    found: list[Path] = []
    for raw in validation._candidate_git_dir_roots():
        git_dir = Path(raw)
        found.append(git_dir)
        common = _common_git_dir(git_dir)
        if common is not None:
            found.append(common)
    if work_root is not None and (work_root / ".git").is_dir():
        found.append((work_root / ".git").resolve())
    return found


def _is_private_directory(metadata: os.stat_result) -> bool:
    """Return True for a directory the caller owns that no one else can write."""
    return metadata.st_uid == os.getuid() and not metadata.st_mode & _GROUP_OR_WORLD_WRITE


def _open_without_links(
    start: Path, resolved: Path
) -> tuple[int, list[tuple[Path, os.stat_result]]]:
    """Open ``resolved`` from the filesystem root without following a link.

    ``resolved`` holds no symlink once its parent is resolved, so each
    directory, from the anchor down, is opened relative to its parent's
    descriptor with ``O_NOFOLLOW``, and the file relative to the last one. A
    component swapped for a link after the resolve fails the open, even one
    above ``start``. The checks then run on the opened objects. Returns the
    file descriptor and the ``(path, stat)`` of ``start`` and every directory
    below it.
    """
    if not resolved.relative_to(start).parts:
        raise ValueError(f"body file must be a regular file, not a root: {resolved}")
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    file_flags = os.O_RDONLY | nofollow | getattr(os, "O_NONBLOCK", 0)
    anchor = Path(resolved.anchor)
    parts = resolved.relative_to(anchor).parts

    if not _HAS_DIR_FD:
        return _open_by_path(start, resolved, file_flags)

    directories: list[tuple[Path, os.stat_result]] = []
    current = anchor
    current_fd = os.open(anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        if current == start:
            directories.append((current, os.fstat(current_fd)))
        for part in parts[:-1]:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | nofollow, dir_fd=current_fd)
            os.close(current_fd)
            current_fd = next_fd
            current = current / part
            if _is_within(current, start):
                directories.append((current, os.fstat(current_fd)))
        return os.open(parts[-1], file_flags, dir_fd=current_fd), directories
    finally:
        os.close(current_fd)


def _open_by_path(
    start: Path, resolved: Path, file_flags: int
) -> tuple[int, list[tuple[Path, os.stat_result]]]:
    """Open without ``dir_fd`` (Windows): lstat each step, then recheck after the open.

    A path open cannot pin its parents, so every directory from the anchor and
    the file are lstat-ed before and after the open and must be the same
    objects, with no symlink or junction among them. A swap and swap-back
    between the two passes is not caught; owner and mode checks do not run on
    Windows either.
    """

    def _is_link(metadata: os.stat_result) -> bool:
        attributes = getattr(metadata, "st_file_attributes", 0)
        return stat.S_ISLNK(metadata.st_mode) or bool(attributes & _FILE_ATTRIBUTE_REPARSE_POINT)

    def _walk() -> list[tuple[Path, os.stat_result]]:
        # From the anchor, so a junction above start is caught too.
        anchor = Path(resolved.anchor)
        found = [(anchor, anchor.lstat())]
        current = anchor
        for part in resolved.relative_to(anchor).parts[:-1]:
            current = current / part
            metadata = current.lstat()
            if _is_link(metadata) or not stat.S_ISDIR(metadata.st_mode):
                raise ValueError(f"body file path crosses a link or non-directory: {current}")
            found.append((current, metadata))
        before = resolved.lstat()
        if _is_link(before):
            raise ValueError(f"body file must not be a symlink: {resolved}")
        found.append((resolved, before))
        return found

    def _identity(entries: list[tuple[Path, os.stat_result]]) -> list[tuple[int, int]]:
        return [(metadata.st_dev, metadata.st_ino) for _path, metadata in entries]

    checked = _walk()
    descriptor = os.open(resolved, file_flags)
    try:
        opened = os.fstat(descriptor)
        if _identity(checked) != _identity(_walk()) or _identity(checked[-1:]) != [
            (opened.st_dev, opened.st_ino)
        ]:
            raise ValueError(f"body file path changed while it was opened: {resolved}")
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor, [entry for entry in checked[:-1] if _is_within(entry[0], start)]


def _check_opened_body(
    display: str,
    name: str,
    metadata: os.stat_result,
    directories: list[tuple[Path, os.stat_result]],
    temp_root: Path | None,
) -> None:
    """Refuse a body file another local user could have written or swapped."""
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"body file must be a regular file: {display}")
    if metadata.st_nlink != 1:
        raise ValueError(f"body file must have exactly one hard link: {display}")
    if not _POSIX_PERMISSIONS:
        return
    if metadata.st_uid != os.getuid():
        raise ValueError(f"body file is owned by another user: {display}")
    mode = stat.S_IMODE(metadata.st_mode)
    if mode & _WORLD_WRITE:
        raise ValueError(f"body file must not be world-writable: {display}")
    if _PREPARED_BODY_NAME.fullmatch(name) and mode & _GROUP_OR_WORLD_ANY:
        raise ValueError(f"prepared body file must be mode 600: {display}")

    # Below a shared temp root, every directory down to the file must belong
    # to the caller and refuse other writers. The broadest matching root is
    # the start, so a TMPDIR nested in /tmp is checked as a directory too.
    if temp_root is not None:
        for directory, directory_metadata in directories:
            # The temp root itself may be shared, like /tmp, only with the
            # sticky bit, which stops other users renaming entries in it.
            # The sticky bit does not bind the directory's owner, so a shared
            # root must also belong to root or the caller.
            shared = directory_metadata.st_mode & _GROUP_OR_WORLD_WRITE
            if directory == temp_root and shared:
                if not directory_metadata.st_mode & stat.S_ISVTX:
                    raise ValueError(f"shared temp directory lacks the sticky bit: {directory}")
                if directory_metadata.st_uid not in (0, os.getuid()):
                    raise ValueError(f"shared temp directory has another owner: {directory}")
            if temp_root in directory.parents and not _is_private_directory(directory_metadata):
                raise ValueError(f"body file directory is not private to the caller: {directory}")

    # Outside a temp root (the repo root or the git dir and below), another
    # user who owns a directory, or anyone at all when it is world-writable
    # without the sticky bit, could rename or swap its entries. Group write is
    # allowed there: under umask 002 every repo directory is mode 775.
    for directory, directory_metadata in directories:
        if temp_root is not None and _is_within(directory, temp_root):
            continue
        if directory_metadata.st_uid not in (0, os.getuid()):
            raise ValueError(f"body file directory has another owner: {directory}")
        world_writable = directory_metadata.st_mode & _WORLD_WRITE
        if world_writable and not directory_metadata.st_mode & stat.S_ISVTX:
            raise ValueError(
                f"body file directory is world-writable without the sticky bit: {directory}"
            )

    # A group-writable file (umask 002) is safe only when no one else can reach
    # it: walking up from the file, every directory is private until one that
    # denies group and other search. Without that directory, a group member
    # could write the content through the group bit.
    if mode & _GROUP_WRITE:
        for _directory, directory_metadata in reversed(directories):
            if not _is_private_directory(directory_metadata):
                break
            if not directory_metadata.st_mode & _GROUP_OR_WORLD_SEARCH:
                return
        raise ValueError(
            f"body file is group-writable outside an owner-only directory: {display}. "
            "Run chmod 600 on it or keep it in a directory only you can enter."
        )


def _refuse_hidden_component(resolved: Path, start: Path, linked: list[Path], display: str) -> None:
    """Refuse a dot-named file or directory anywhere below the broadest root.

    ``.env``, ``service/.env`` and ``vendor/.git/config`` are refused alike.
    Two places are exempt: a ``.project-toolkit/scratch`` directory, the
    scratch convention that ``--prepare-body-file`` and worktrees use, and the
    path down to a linked worktree's own git dir for the issue scripts.
    """
    exempt: set[Path] = set()
    for directory in resolved.parents:
        if (directory.parent.name, directory.name) == _TRUSTED_DOT_PREFIX:
            exempt.update({directory.parent, directory})
    for git_dir in linked:
        exempt.update(directory for directory in (git_dir, *git_dir.parents))
    for component in (resolved, *resolved.parents):
        if component == start or start not in component.parents:
            break
        if component.name.startswith(".") and component not in exempt:
            raise ValueError(f"body file must not be a dotfile or in a dot directory: {display}")


def _refuse_alias_component(resolved: Path, start: Path, display: str) -> None:
    """Refuse a component below ``start`` that could be an NTFS alias of another name."""
    for component in (resolved, *resolved.parents):
        if component == start or start not in component.parents:
            break
        name = component.name
        if ":" in name or _NTFS_SHORT_NAME.search(name) or name.endswith((".", " ")):
            raise ValueError(
                f"body file path has a component that can alias another name "
                f"(':', '~<digit>', or a trailing dot or space): {display}"
            )


def _check_location(
    resolved: Path, start: Path, linked: list[Path], refused_git_dirs: list[Path], display: str
) -> None:
    """Run the name-based location checks on one spelling of the path."""
    _refuse_alias_component(resolved, start, display)
    if linked and resolved.name.casefold() in _GIT_CONFIG_NAMES:
        raise ValueError(f"body file must not be a git config file: {display}")
    _refuse_hidden_component(resolved, start, linked, display)
    for git_dir in refused_git_dirs:
        if _is_within(resolved, git_dir) and not linked:
            raise ValueError(f"body file must not be inside the git dir: {display}")


def _final_path(descriptor: int) -> Path | None:
    """Return the name Windows gives the opened file, or None when it cannot say.

    ``GetFinalPathNameByHandleW`` expands 8.3 short names and drops trailing
    dots, so the location checks can run again on the real name. The
    platform check also lets type checkers skip the Windows-only APIs.
    """
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        import msvcrt
        from ctypes import wintypes

        handle = msvcrt.get_osfhandle(descriptor)
        # A local prototype, so the shared kernel32 function object is untouched.
        prototype = ctypes.WINFUNCTYPE(
            wintypes.DWORD, wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD
        )
        get_final = prototype(("GetFinalPathNameByHandleW", ctypes.windll.kernel32))
        buffer = ctypes.create_unicode_buffer(32768)
        length = get_final(handle, buffer, len(buffer), 0)
    except (ImportError, AttributeError, OSError):
        return None
    if not length or length >= len(buffer):
        return None
    final = buffer.value
    if final.startswith("\\\\?\\UNC\\"):
        final = "\\\\" + final[8:]
    elif final.startswith("\\\\?\\"):
        final = final[4:]
    return Path(final)


def _check_canonical_location(
    descriptor: int, start: Path, linked: list[Path], refused_git_dirs: list[Path], display: str
) -> None:
    """On Windows, rerun the location checks on the opened file's real name."""
    final = _final_path(descriptor)
    if final is None:
        raise ValueError(f"cannot read the real name of the opened body file: {display}")

    def canonical(path: Path) -> Path:
        return Path(os.path.realpath(path))

    canonical_start = canonical(start)
    if not _is_within(final, canonical_start) or final == canonical_start:
        raise ValueError(f"body file real name is outside the approved root: {display}")
    _check_location(
        final,
        canonical_start,
        [canonical(root) for root in linked],
        [canonical(root) for root in refused_git_dirs],
        display,
    )


def read_body_file_text(
    path: str,
    base: str | Path | None = None,
    *,
    allow_git_dir: bool = False,
) -> str:
    """Read a UTF-8 body file after the containment, location, and open checks.

    The one reader for every script that sends a file body to GitHub:
    ``new_pr.py``, ``edit_pr_body.py``, ``close_issue.py``,
    ``reopen_issue.py`` and ``post_issue_comment.py`` (issue #6667). A
    relative ``path`` resolves against ``base`` when given, else the working
    directory.

    The parent directory is resolved once. The final component is not, so a
    symlinked file is refused. The checks, in order:

    1. The path sits under the repo root (the working directory outside a
       repo), a temp root, or, only when ``allow_git_dir``, the git dir.
    2. No component below the broadest matching root starts with a dot,
       except a ``.project-toolkit/scratch`` directory, or looks like an
       NTFS alias (``:``, ``~<digit>``, a trailing dot or space). It is not
       in the git dir or the common git dir, except a linked worktree's own
       git dir when ``allow_git_dir``. On Windows these checks run again on
       the opened file's real name.
    3. The file is opened from the filesystem root with ``O_NOFOLLOW`` on
       every component and ``O_NONBLOCK`` on the file, so a symlink or a
       swapped parent fails the open and a FIFO cannot block.
    4. On the opened objects: a regular file, one hard link, owned by the
       caller, not world-writable; ``pr-body-*.md`` is mode 600. Below a temp
       root every directory is owned by the caller with no group or other
       write. Below the repo root or the git dir every directory belongs to
       the caller or root and is not world-writable without the sticky bit.
       A group-writable file needs an owner-only directory above it.

    Args:
        path: The body file path.
        base: Directory a relative ``path`` resolves against.
        allow_git_dir: Accept a file in a linked worktree's own git dir,
            except its config files. The issue scripts keep this documented
            reply flow; PR scripts do not. A primary clone's ``.git`` never
            qualifies.

    Returns:
        The file text.

    Raises:
        ValueError: A check refused the file. ``UnicodeError`` (a subclass)
            reports a file that is not UTF-8.
        OSError: The file is missing or unreadable.
    """
    candidate = Path(path)
    if base is not None and not candidate.is_absolute():
        candidate = Path(base) / candidate
    if validation._TRAVERSAL_PATTERN.search(str(candidate)):
        raise ValueError(f"body file path contains a parent-directory segment: {path}")
    absolute = Path(os.path.abspath(candidate))
    resolved = absolute.parent.resolve() / absolute.name

    work_root = _working_root()
    temp_roots = [Path(root) for root in validation._candidate_temp_roots()]
    git_roots = _linked_worktree_git_dirs() if allow_git_dir else []
    containing = [
        root
        for root in [work_root, *temp_roots, *git_roots]
        if root is not None and _is_within(resolved, root)
    ]
    if not containing:
        where = "the repo root, a temp directory, or the git dir"
        if not allow_git_dir:
            where = "the repo root or a temp directory"
        raise ValueError(f"body file must be under {where}: {path}")

    start = min(containing, key=lambda root: len(root.parts))
    linked = [root for root in git_roots if _is_within(resolved, root)]
    refused_git_dirs = _git_dirs_to_refuse(work_root)
    _check_location(resolved, start, linked, refused_git_dirs, path)

    matching_temp = [root for root in temp_roots if _is_within(resolved, root)]
    temp_root = min(matching_temp, key=lambda root: len(root.parts)) if matching_temp else None
    # For a body in a linked worktree's git dir, the directories from the
    # common git dir down to it are walked too, so ``.git/worktrees`` gets
    # the owner and mode checks as well.
    walk_root = start
    if start in linked:
        common = _common_git_dir(start)
        if common is not None and common in start.parents:
            walk_root = common
    try:
        descriptor, directories = _open_without_links(walk_root, resolved)
    except OSError as exc:
        if exc.errno in _LINK_ERRNOS:
            raise ValueError(
                f"body file path must not contain a symlink or non-directory: {path}"
            ) from exc
        raise
    try:
        if _IS_WINDOWS:
            _check_canonical_location(descriptor, start, linked, refused_git_dirs, path)
        _check_opened_body(path, resolved.name, os.fstat(descriptor), directories, temp_root)
        with os.fdopen(descriptor, encoding="utf-8") as body_file:
            descriptor = -1
            return body_file.read()
    finally:
        if descriptor >= 0:
            os.close(descriptor)
