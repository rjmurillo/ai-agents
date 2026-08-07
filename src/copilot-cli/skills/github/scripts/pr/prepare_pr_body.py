"""Create and read private PR body files below consumer scratch space."""

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
_PRIVATE_MASK = 0o077
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
    agents_dir = root / ".agents"
    scratch_dir = agents_dir / "scratch"
    if not _HAS_DIRECTORY_FDS:
        if os.name == "nt":
            raise PreparePrBodyError(
                "secure PR body files are not supported on Windows"
            )
        _ensure_plain_directory(agents_dir, owner_only=False)
        _ensure_plain_directory(scratch_dir, owner_only=True)
        return scratch_dir, None

    agents_fd = _open_plain_directory(agents_dir, owner_only=False)
    try:
        try:
            os.mkdir("scratch", mode=stat.S_IRWXU, dir_fd=agents_fd)
        except FileExistsError:
            pass
        before = os.stat("scratch", dir_fd=agents_fd, follow_symlinks=False)
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISDIR(before.st_mode):
            raise PreparePrBodyError(
                f"path must be a plain directory: {scratch_dir}"
            )
        _require_owned(scratch_dir, before)
        flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
        scratch_fd = os.open("scratch", flags, dir_fd=agents_fd)
        opened = os.fstat(scratch_fd)
        if not stat.S_ISDIR(opened.st_mode) or not _same_object(before, opened):
            os.close(scratch_fd)
            raise PreparePrBodyError(
                f"directory changed before open: {scratch_dir}"
            )
        os.fchmod(scratch_fd, stat.S_IRWXU)
        return scratch_dir, scratch_fd
    finally:
        os.close(agents_fd)


def _new_body_name() -> str:
    return f"pr-body-{secrets.token_hex(16)}.md"


def prepare_pr_body(repo_root: Path) -> Path:
    """Return a newly created private file below ``.agents/scratch``."""
    root = repo_root.resolve()
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
                body_file.write(_BODY_PLACEHOLDER)
                path = Path(body_file.name)
        else:
            while True:
                name = _new_body_name()
                try:
                    descriptor = os.open(
                        name,
                        os.O_WRONLY
                        | os.O_CREAT
                        | os.O_EXCL
                        | getattr(os, "O_NOFOLLOW", 0),
                        0o600,
                        dir_fd=scratch_fd,
                    )
                    break
                except FileExistsError:
                    continue
            with os.fdopen(descriptor, "w", encoding="utf-8") as body_file:
                body_file.write(_BODY_PLACEHOLDER)
            path = scratch_dir / name
    finally:
        if scratch_fd is not None:
            os.close(scratch_fd)
    return path.relative_to(root)


def _validate_body_path(relative_path: str) -> Path:
    path = Path(relative_path)
    if (
        path.is_absolute()
        or path.parts[:2] != (".agents", "scratch")
        or len(path.parts) != 3
        or not _BODY_NAME_RE.fullmatch(path.name)
    ):
        raise PreparePrBodyError(
            "body file must match .agents/scratch/pr-body-*.md"
        )
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
        raise PreparePrBodyError(f"body file must be owner-only: {relative_path}")
    if not _same_object(before, opened) or (
        before.st_ctime_ns,
        before.st_size,
    ) != (
        opened.st_ctime_ns,
        opened.st_size,
    ):
        raise PreparePrBodyError(f"body file changed before read: {relative_path}")


def read_prepared_pr_body(repo_root: Path, relative_path: str) -> str:
    """Read one allocated body without following links or leaving scratch."""
    path = _validate_body_path(relative_path)
    scratch_dir, scratch_fd = _open_scratch(repo_root)
    descriptor = -1
    try:
        if scratch_fd is None:
            body_path = scratch_dir / path.name
            before = body_path.lstat()
            descriptor = os.open(
                body_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            )
        else:
            before = os.stat(path.name, dir_fd=scratch_fd, follow_symlinks=False)
            if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
                raise PreparePrBodyError(
                    f"body file must be a plain file: {relative_path}"
                )
            descriptor = os.open(
                path.name,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=scratch_fd,
            )
        opened = os.fstat(descriptor)
        _validate_body_metadata(relative_path, before, opened)
        with os.fdopen(descriptor, encoding="utf-8") as body_file:
            descriptor = -1
            content = body_file.read()
        if content == _BODY_PLACEHOLDER:
            raise PreparePrBodyError("body placeholder was not replaced")
        return content
    except FileNotFoundError as exc:
        raise PreparePrBodyError(f"body file not found: {relative_path}") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if scratch_fd is not None:
            os.close(scratch_fd)


def write_prepared_pr_body(
    repo_root: Path, relative_path: str, content: str
) -> None:
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
