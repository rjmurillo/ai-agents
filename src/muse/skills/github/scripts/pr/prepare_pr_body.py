"""Create and fill private PR body files below consumer scratch space."""

from __future__ import annotations

import argparse
import os
import re
import secrets
import stat
import subprocess
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
# The template is read from the base ref, not the working tree, so a PR cannot
# edit it to seed its own body text (#6506). Git tree modes for a regular file.
_REGULAR_BLOB_MODES = frozenset({"100644", "100755"})
_FALLBACK_BASE_REF = "origin/main"
_GIT_TIMEOUT_SECONDS = 30
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


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            check=False,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise PreparePrBodyError(f"cannot run git to read the PR template: {exc}") from exc


def _default_base_ref(root: Path) -> str:
    """Return ``origin/<default branch>``, falling back to ``origin/main``."""
    result = _git(root, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD")
    name = result.stdout.decode("utf-8", "replace").strip()
    if result.returncode == 0 and name:
        return name
    return _FALLBACK_BASE_REF


def _require_base_ref(root: Path, base_ref: str) -> None:
    """Fail closed when ``base_ref`` is not a commit in this clone.

    Reading the checked-out branch instead would let a PR that edits the
    template seed its own body text (#6506), so an unfetched base is an error.
    """
    if base_ref.startswith("-") or not base_ref.strip():
        raise PreparePrBodyError(f"invalid base ref for the PR template: {base_ref!r}")
    result = _git(root, "rev-parse", "--verify", "--quiet", f"{base_ref}^{{commit}}")
    if result.returncode != 0:
        remote, _, branch = base_ref.partition("/")
        hint = f"git fetch {remote} {branch}" if branch else f"git fetch origin {base_ref}"
        raise PreparePrBodyError(
            f"base ref {base_ref!r} is not available locally, so the PR template cannot "
            f"be read from it; run `{hint}` or pass --base <ref>"
        )


def _read_base_template(root: Path, base_ref: str) -> str | None:
    """Return the template text at ``base_ref``, or None when it is not usable.

    Usable means a regular-file blob (not a symlink or submodule), at most
    64 KiB, valid UTF-8. A template that is absent at the base is not an error.
    """
    listing = _git(
        root, "ls-tree", "--full-tree", "--long", "-z", base_ref, "--", _TEMPLATE_PATH.as_posix()
    )
    if listing.returncode != 0:
        detail = listing.stderr.decode("utf-8", "replace").strip()
        raise PreparePrBodyError(f"cannot list {base_ref!r} to read the PR template: {detail}")
    entry = listing.stdout.split(b"\0", 1)[0].decode("utf-8", "replace")
    if not entry:
        return None
    meta, _, _name = entry.partition("\t")
    fields = meta.split()
    if len(fields) != 4:
        return None
    mode, kind, sha, size = fields
    if kind != "blob" or mode not in _REGULAR_BLOB_MODES:
        return None
    if not size.isdigit() or int(size) > _TEMPLATE_MAX_BYTES:
        return None
    blob = _git(root, "cat-file", "blob", sha)
    if blob.returncode != 0:
        raise PreparePrBodyError(f"cannot read the PR template blob at {base_ref!r}")
    try:
        return blob.stdout.decode("utf-8")
    except UnicodeError:
        return None


def _seed_content(root: Path, base_ref: str | None = None) -> str:
    """Return the placeholder line followed by the PR template at the base ref.

    The template comes from the base ref, never the checked-out branch. An
    unfetched base ref raises. A base without a usable template gets the
    placeholder alone.
    """
    ref = base_ref if base_ref is not None else _default_base_ref(root)
    _require_base_ref(root, ref)
    template = _read_base_template(root, ref)
    if template is None:
        return _BODY_PLACEHOLDER
    return _BODY_PLACEHOLDER + "\n" + template


def prepare_pr_body(
    repo_root: Path, base_ref: str | None = None, *, seed_template: bool = True
) -> Path:
    """Return a newly created private file below ``.project-toolkit/scratch``.

    The file holds the placeholder line and the PR template as it exists at
    ``base_ref`` (default ``origin/<default branch>``). Raises when that ref is
    not fetched. Delete the placeholder line once the template sections are
    filled in. A caller that overwrites the whole file at once passes
    ``seed_template=False`` to get the placeholder alone and skip git.
    """
    root = repo_root.resolve()
    seed = _seed_content(root, base_ref) if seed_template else _BODY_PLACEHOLDER
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


_HELP_EPILOG = """\
examples:
  %(prog)s
  %(prog)s --base origin/main

exit codes:
  0  success
"""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="prepare_pr_body.py",
        description=(
            "Create a mode-600 PR body file under .project-toolkit/scratch/ in "
            "the current repository, seeded with the PR template read from the "
            "base ref, and print its path on stdout. Fill the file, then pass "
            "it to new_pr.py with --body-file."
        ),
        epilog=_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--base",
        dest="base_ref",
        metavar="REF",
        default=None,
        help="ref to read the PR template from (default: the repository default base)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        base_ref = _build_parser().parse_args(argv).base_ref
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    try:
        body_path = prepare_pr_body(Path.cwd(), base_ref)
    except (OSError, PreparePrBodyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(body_path.as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
