"""Create and fill private PR body files below consumer scratch space."""

from __future__ import annotations

import os
import re
import secrets
import stat
import sys
import tempfile
from pathlib import Path


class PreparePrBodyError(RuntimeError):
    """The scratch directory or body file is unsafe."""


_BODY_NAME_RE = re.compile(r"^pr-body-[A-Za-z0-9_-]+\.md$")
_BODY_PLACEHOLDER = "<!-- replace with PR body -->\n"
_TEMPLATE_PATH = Path(".github") / "PULL_REQUEST_TEMPLATE.md"
_TEMPLATE_MAX_BYTES = 64 * 1024
# One sentence, shared by the name check and the mode check, so a caller learns
# both rules from whichever one fails first (#5540).
_BODY_FILE_RULES = (
    "body file must match .project-toolkit/scratch/pr-body-*.md and be mode 600 "
    "(owner-only); create one with new_pr.py --prepare-body-file"
)
_PRIVATE_MASK = 0o077
# World-write only. Any account could rewrite a world-writable template and plant
# text in every body seeded from it (#6506). Group-write stays allowed: a umask
# of 002, common with per-user groups, gives every fresh checkout mode 664.
_TEMPLATE_WRITE_MASK = 0o002
_HAS_DIRECTORY_FDS = (
    hasattr(os, "O_DIRECTORY")
    and os.open in os.supports_dir_fd
    and os.mkdir in os.supports_dir_fd
    and os.stat in os.supports_dir_fd
)


def _same_object(left: os.stat_result, right: os.stat_result) -> bool:
    return (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)


def _require_owned(path: Path, metadata: os.stat_result) -> None:
    if hasattr(os, "getuid") and metadata.st_uid != os.getuid():
        raise PreparePrBodyError(f"path has another owner: {path}")


def _ensure_plain_directory(path: Path, *, owner_only: bool) -> None:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        path.mkdir(mode=stat.S_IRWXU)
        metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise PreparePrBodyError(f"path must be a plain directory: {path}")
    _require_owned(path, metadata)
    if owner_only and stat.S_IMODE(metadata.st_mode) & _PRIVATE_MASK:
        path.chmod(stat.S_IRWXU)


def _open_plain_directory(path: Path, *, owner_only: bool) -> int:
    """Open a directory without following a replacement symlink."""
    _ensure_plain_directory(path, owner_only=owner_only)
    before = path.lstat()
    flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    opened = os.fstat(descriptor)
    if not stat.S_ISDIR(opened.st_mode) or not _same_object(before, opened):
        os.close(descriptor)
        raise PreparePrBodyError(f"directory changed before open: {path}")
    if owner_only:
        os.fchmod(descriptor, stat.S_IRWXU)
    return descriptor


def _open_scratch(repo_root: Path) -> tuple[Path, int | None]:
    root = repo_root.resolve()
    toolkit_dir = root / ".project-toolkit"
    scratch_dir = toolkit_dir / "scratch"
    if not _HAS_DIRECTORY_FDS:
        if os.name == "nt":
            raise PreparePrBodyError("secure PR body files are not supported on Windows")
        _ensure_plain_directory(toolkit_dir, owner_only=False)
        _ensure_plain_directory(scratch_dir, owner_only=True)
        return scratch_dir, None

    toolkit_fd = _open_plain_directory(toolkit_dir, owner_only=False)
    try:
        try:
            os.mkdir("scratch", mode=stat.S_IRWXU, dir_fd=toolkit_fd)
        except FileExistsError:
            pass
        before = os.stat("scratch", dir_fd=toolkit_fd, follow_symlinks=False)
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISDIR(before.st_mode):
            raise PreparePrBodyError(f"path must be a plain directory: {scratch_dir}")
        _require_owned(scratch_dir, before)
        flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
        scratch_fd = os.open("scratch", flags, dir_fd=toolkit_fd)
        opened = os.fstat(scratch_fd)
        if not stat.S_ISDIR(opened.st_mode) or not _same_object(before, opened):
            os.close(scratch_fd)
            raise PreparePrBodyError(f"directory changed before open: {scratch_dir}")
        os.fchmod(scratch_fd, stat.S_IRWXU)
        return scratch_dir, scratch_fd
    finally:
        os.close(toolkit_fd)


def _new_body_name() -> str:
    return f"pr-body-{secrets.token_hex(16)}.md"


def _open_template_fd(root: Path) -> int:
    """Open the PR template without following a symlink at any component.

    ``.github`` is opened as a directory with O_NOFOLLOW, then the template is
    opened relative to that descriptor, so neither component can be swapped for
    a link that points outside the checkout.
    """
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | nofollow
    root_fd = os.open(root, directory_flags)
    try:
        github_fd = os.open(_TEMPLATE_PATH.parent, directory_flags, dir_fd=root_fd)
    finally:
        os.close(root_fd)
    try:
        # O_NONBLOCK keeps a FIFO planted at the template path from hanging.
        return os.open(
            _TEMPLATE_PATH.name,
            os.O_RDONLY | nofollow | getattr(os, "O_NONBLOCK", 0),
            dir_fd=github_fd,
        )
    finally:
        os.close(github_fd)


def _read_template_fd(descriptor: int) -> str:
    """Read an owned, single-link regular file of bounded size from ``descriptor``."""
    metadata = os.fstat(descriptor)
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise PreparePrBodyError("PR template is not a plain file")
    if hasattr(os, "getuid") and metadata.st_uid != os.getuid():
        raise PreparePrBodyError("PR template has another owner")
    if stat.S_IMODE(metadata.st_mode) & _TEMPLATE_WRITE_MASK:
        raise PreparePrBodyError("PR template is world-writable")
    with os.fdopen(descriptor, "rb", closefd=False) as template_file:
        data = template_file.read(_TEMPLATE_MAX_BYTES + 1)
    if len(data) > _TEMPLATE_MAX_BYTES:
        raise PreparePrBodyError("PR template is too large")
    return data.decode("utf-8")


def _seed_content(root: Path) -> str:
    """Return the placeholder line followed by the repository PR template.

    A repository without a safe template gets the placeholder alone. Safe means
    a regular file, one link, owned by the caller, not world-writable,
    at most 64 KiB, reached without crossing a symlink.
    """
    if not _HAS_DIRECTORY_FDS:
        return _BODY_PLACEHOLDER
    try:
        descriptor = _open_template_fd(root)
    except OSError:
        return _BODY_PLACEHOLDER
    try:
        return _BODY_PLACEHOLDER + "\n" + _read_template_fd(descriptor)
    except (OSError, UnicodeError, PreparePrBodyError):
        return _BODY_PLACEHOLDER
    finally:
        os.close(descriptor)


def prepare_pr_body(repo_root: Path) -> Path:
    """Return a newly created private file below ``.project-toolkit/scratch``.

    The file holds the placeholder line and the repository PR template. Delete
    the placeholder line once the template sections are filled in.
    """
    root = repo_root.resolve()
    seed = _seed_content(root)
    scratch_dir, scratch_fd = _open_scratch(root)
    try:
        if scratch_fd is None:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                prefix="pr-body-",
                suffix=".md",
                dir=scratch_dir,
                delete=False,
            ) as body_file:
                body_file.write(seed)
                path = Path(body_file.name)
        else:
            while True:
                name = _new_body_name()
                try:
                    descriptor = os.open(
                        name,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                        0o600,
                        dir_fd=scratch_fd,
                    )
                    break
                except FileExistsError:
                    continue
            with os.fdopen(descriptor, "w", encoding="utf-8") as body_file:
                body_file.write(seed)
            path = scratch_dir / name
    finally:
        if scratch_fd is not None:
            os.close(scratch_fd)
    return path.relative_to(root)


def _validate_body_path(relative_path: str) -> Path:
    path = Path(relative_path)
    if (
        path.is_absolute()
        or path.parts[:2] != (".project-toolkit", "scratch")
        or len(path.parts) != 3
        or not _BODY_NAME_RE.fullmatch(path.name)
    ):
        raise PreparePrBodyError(_BODY_FILE_RULES)
    return path


def _validate_body_metadata(
    relative_path: str, before: os.stat_result, opened: os.stat_result
) -> None:
    if (
        stat.S_ISLNK(before.st_mode)
        or not stat.S_ISREG(before.st_mode)
        or not stat.S_ISREG(opened.st_mode)
        or before.st_nlink != 1
        or opened.st_nlink != 1
    ):
        raise PreparePrBodyError(f"body file must be plain: {relative_path}")
    _require_owned(Path(relative_path), before)
    if stat.S_IMODE(before.st_mode) & _PRIVATE_MASK:
        raise PreparePrBodyError(f"{_BODY_FILE_RULES}: {relative_path}")
    if not _same_object(before, opened) or (
        before.st_ctime_ns,
        before.st_size,
    ) != (
        opened.st_ctime_ns,
        opened.st_size,
    ):
        raise PreparePrBodyError(f"body file changed before read: {relative_path}")


def reject_unreplaced_placeholder(content: str) -> None:
    """Raise when a whole line of ``content`` is the line ``prepare_pr_body`` seeds.

    A body that quotes the marker inside prose or a code span is not a seed
    and passes.
    """
    marker = _BODY_PLACEHOLDER.strip()
    if any(line.strip() == marker for line in content.splitlines()):
        raise PreparePrBodyError("body placeholder was not replaced")


def write_prepared_pr_body(repo_root: Path, relative_path: str, content: str) -> None:
    """Replace one allocated placeholder without following path substitutions."""
    path = _validate_body_path(relative_path)
    scratch_dir, scratch_fd = _open_scratch(repo_root)
    descriptor = -1
    try:
        if scratch_fd is None:
            body_path = scratch_dir / path.name
            before = body_path.lstat()
            descriptor = os.open(
                body_path,
                os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
            )
        else:
            before = os.stat(path.name, dir_fd=scratch_fd, follow_symlinks=False)
            descriptor = os.open(
                path.name,
                os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=scratch_fd,
            )
        opened = os.fstat(descriptor)
        _validate_body_metadata(relative_path, before, opened)
        os.ftruncate(descriptor, 0)
        with os.fdopen(descriptor, "w", encoding="utf-8") as body_file:
            descriptor = -1
            body_file.write(content)
    except FileNotFoundError as exc:
        raise PreparePrBodyError(f"body file not found: {relative_path}") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if scratch_fd is not None:
            os.close(scratch_fd)


def main() -> int:
    try:
        body_path = prepare_pr_body(Path.cwd())
    except (OSError, PreparePrBodyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(body_path.as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
