"""Input validation: GitHub name validation, path traversal prevention."""

from __future__ import annotations

import errno
import os
import re
import stat
from pathlib import Path

# Owner: alphanumeric + hyphens, 1-39 chars, cannot start/end with hyphen
_OWNER_PATTERN = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9-]{0,37}[a-zA-Z0-9])?$")

# Repo: alphanumeric, hyphens, underscores, periods, 1-100 chars
_REPO_PATTERN = re.compile(r"^[a-zA-Z0-9._-]{1,100}$")

# `.` and `..` are the two names GitHub refuses outright, because both are
# directory aliases. Callers interpolate these values into URL paths, so a
# name that means "parent directory" must not reach that position. Longer
# dot runs such as `...` are legal repository names and stay allowed.
_DIRECTORY_ALIASES = frozenset({".", ".."})

_TRAVERSAL_PATTERN = re.compile(r"\.\.[/\\]")


def is_github_name_valid(name: str, name_type: str) -> bool:
    """Validate a GitHub owner or repository name.

    Prevents command injection (CWE-78) by enforcing GitHub naming rules.

    Args:
        name: The name to validate.
        name_type: Either "owner" or "repo" (case-insensitive).

    Returns:
        True if the name conforms to GitHub's rules.
    """
    if not name or not name.strip():
        return False

    if name in _DIRECTORY_ALIASES:
        return False

    normalized = name_type.lower()
    if normalized == "owner":
        return bool(_OWNER_PATTERN.match(name))
    if normalized == "repo":
        return bool(_REPO_PATTERN.match(name))

    return False


def is_safe_file_path(path: str, allowed_base: str | None = None) -> bool:
    """Validate that a file path does not traverse outside allowed boundaries.

    Prevents path traversal attacks (CWE-22).

    Args:
        path: The file path to validate.
        allowed_base: Base directory paths must stay within. When ``None``,
            the repository root is used, falling back to the working directory
            only when git confirms there is no repository.

    Returns:
        True if the resolved path stays within the allowed base. False when the
        containment base cannot be established, because a check that silently
        answers a different question is worse than one that refuses to answer.
    """
    if _TRAVERSAL_PATTERN.search(path):
        return False

    try:
        if allowed_base is None:
            from .repo import REPO_ROOT_NOT_A_REPO, resolve_repo_root

            repo_root, reason = resolve_repo_root()
            if repo_root is not None:
                allowed_base = str(repo_root)
            elif reason == REPO_ROOT_NOT_A_REPO:
                # Git answered: there is no repository. The working directory
                # is then the only boundary available, and it is a fact rather
                # than a guess.
                allowed_base = os.getcwd()
            else:
                # Git could not answer. The repo root is unknown, not known to
                # be absent, so there is no base to check containment against.
                return False
        resolved_path = str(Path(path).resolve())
        resolved_base = str(Path(allowed_base).resolve())
        return resolved_path == resolved_base or resolved_path.startswith(resolved_base + os.sep)
    except (OSError, ValueError):
        return False


def _candidate_temp_roots() -> list[str]:
    """Return all temp-directory roots a mktemp-style command may use.

    macOS resolves TMPDIR to a per-user /var/folders/.../T/ path. mktemp -t
    may place files under /tmp or /private/tmp depending on PATH and shell.
    Linux GNU mktemp obeys TMPDIR consistently. Collect every plausible
    base so reply staging works under all shells.
    """
    import tempfile

    roots: list[str] = []
    seen: set[str] = set()
    for candidate in (
        os.environ.get("TMPDIR"),
        tempfile.gettempdir(),
        "/tmp",
        "/private/tmp",
    ):
        if not candidate:
            continue
        try:
            resolved = str(Path(candidate).resolve())
        except (OSError, ValueError):
            continue
        if resolved not in seen and Path(resolved).exists():
            seen.add(resolved)
            roots.append(resolved)
    return roots


def _candidate_git_dir_roots() -> list[str]:
    """Return the git dir for the current working directory, if one exists.

    In a linked worktree ``git rev-parse --git-dir`` returns the worktree-
    specific path (e.g. ``.git/worktrees/wt-4055/``), which is a safe scratch
    location for transient reply bodies when ``/tmp`` is unavailable and the
    working tree must stay clean of untracked files.

    Returns an empty list when git is not available or the cwd is not inside
    a repository.
    """
    import subprocess

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
        )
        if result.returncode != 0:
            return []
        git_dir = result.stdout.strip()
        if not git_dir:
            return []
        resolved = str(Path(git_dir).resolve())
        if Path(resolved).is_dir():
            return [resolved]
    except (OSError, subprocess.TimeoutExpired):
        pass
    return []


def is_allowed_body_file_path(path: str) -> bool:
    """Return True when a body or comment file sits under an approved root.

    This is the one containment rule for every skill script that reads a body
    or comment file and sends it to GitHub (issue #6667). It never exits, so
    a caller that owns an output envelope can report the failure in its own
    shape. :func:`assert_valid_body_file` is the exiting wrapper.

    Approved roots, checked in this order: the repository root of the working
    directory, every temp root from :func:`_candidate_temp_roots`, the git dir
    from :func:`_candidate_git_dir_roots`. No caller adds roots, so every script
    accepts the same paths. A relative-path base such as ``GITHUB_WORKSPACE`` only
    resolves the path and never widens the roots. Paths are resolved before the
    prefix test, so a symlink under an approved root that points elsewhere is
    rejected. The caller owns the existence check.

    Five scripts read their body file through :func:`read_body_file_text`,
    which applies this rule and the stricter location and open checks (owner
    decision D14, 2026-10-24, issue #6667). ``new_pr.py`` and
    ``edit_pr_body.py`` refuse the git dir there; the issue scripts keep it.

    Args:
        path: The file path to check.

    Returns:
        True when the resolved path stays within an approved root.
    """
    if is_safe_file_path(path, None):
        return True

    for temp_root in _candidate_temp_roots():
        if is_safe_file_path(path, temp_root):
            return True

    for git_root in _candidate_git_dir_roots():
        if is_safe_file_path(path, git_root):
            return True

    return False


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
    for raw in _candidate_git_dir_roots():
        git_dir = Path(raw)
        common = _common_git_dir(git_dir)
        if common is not None and common != git_dir:
            found.append(git_dir)
    return found


def _git_dirs_to_refuse(work_root: Path | None) -> list[Path]:
    """Return the git dir, its common dir, and ``<repo>/.git`` when it is a directory."""
    found: list[Path] = []
    for raw in _candidate_git_dir_roots():
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
    """Open ``resolved`` by walking down from ``start`` without following a link.

    Each directory below ``start`` is opened relative to its parent's
    descriptor with ``O_NOFOLLOW``, and the file is opened relative to the last
    one. The checks then run on the objects that were opened, not on a path
    that could change in between. Returns the file descriptor and the
    ``(path, stat)`` of ``start`` and every directory below it.
    """
    parts = resolved.relative_to(start).parts
    if not parts:
        raise ValueError(f"body file must be a regular file, not a root: {resolved}")
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    file_flags = os.O_RDONLY | nofollow | getattr(os, "O_NONBLOCK", 0)

    if not _HAS_DIR_FD:
        # Windows has no dir_fd. Refuse a link at each step by lstat, then
        # confirm the opened file is the one that was checked.
        directories = [(start, start.stat())]
        current = start
        for part in parts[:-1]:
            current = current / part
            metadata = current.lstat()
            if not stat.S_ISDIR(metadata.st_mode):
                raise ValueError(f"body file path crosses a link or non-directory: {current}")
            directories.append((current, metadata))
        before = resolved.lstat()
        if stat.S_ISLNK(before.st_mode):
            raise ValueError(f"body file must not be a symlink: {resolved}")
        descriptor = os.open(resolved, file_flags)
        opened = os.fstat(descriptor)
        if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            os.close(descriptor)
            raise ValueError(f"body file changed while it was opened: {resolved}")
        return descriptor, directories

    current_fd = os.open(start, os.O_RDONLY | os.O_DIRECTORY)
    try:
        directories = [(start, os.fstat(current_fd))]
        current = start
        for part in parts[:-1]:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | nofollow, dir_fd=current_fd)
            os.close(current_fd)
            current_fd = next_fd
            current = current / part
            directories.append((current, os.fstat(current_fd)))
        return os.open(parts[-1], file_flags, dir_fd=current_fd), directories
    finally:
        os.close(current_fd)


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
            if temp_root in directory.parents and not _is_private_directory(directory_metadata):
                raise ValueError(f"body file directory is not private to the caller: {directory}")

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
    2. It is not a repo dotfile or in a top-level dot directory, except
       ``.project-toolkit/scratch``. Without ``allow_git_dir`` it is not in
       the git dir or the common git dir.
    3. The file is opened by walking from the broadest matching root with
       ``O_NOFOLLOW`` on every component and ``O_NONBLOCK`` on the file, so a
       symlink or a swapped parent fails the open and a FIFO cannot block.
    4. On the opened objects: a regular file, one hard link, owned by the
       caller, not world-writable; ``pr-body-*.md`` is mode 600. Below a temp
       root every directory is owned by the caller with no group or other
       write. A group-writable file needs an owner-only directory above it.

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
    if _TRAVERSAL_PATTERN.search(str(candidate)):
        raise ValueError(f"body file path contains a parent-directory segment: {path}")
    absolute = Path(os.path.abspath(candidate))
    resolved = absolute.parent.resolve() / absolute.name

    work_root = _working_root()
    temp_roots = [Path(root) for root in _candidate_temp_roots()]
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

    in_git_dir = any(_is_within(resolved, root) for root in git_roots)
    if in_git_dir and resolved.name in _GIT_CONFIG_NAMES:
        raise ValueError(f"body file must not be a git config file: {path}")
    if work_root is not None and work_root in resolved.parents and not in_git_dir:
        parts = resolved.relative_to(work_root).parts
        trusted = parts[:2] == _TRUSTED_DOT_PREFIX and len(parts) > 2
        if parts[0].startswith(".") and not trusted:
            raise ValueError(f"body file must not be a repo dotfile or in a dot directory: {path}")
    if not allow_git_dir:
        for git_dir in _git_dirs_to_refuse(work_root):
            if _is_within(resolved, git_dir):
                raise ValueError(f"body file must not be inside the git dir: {path}")

    start = min(containing, key=lambda root: len(root.parts))
    matching_temp = [root for root in temp_roots if _is_within(resolved, root)]
    temp_root = min(matching_temp, key=lambda root: len(root.parts)) if matching_temp else None
    try:
        descriptor, directories = _open_without_links(start, resolved)
    except OSError as exc:
        if exc.errno in _LINK_ERRNOS:
            raise ValueError(
                f"body file path must not contain a symlink or non-directory: {path}"
            ) from exc
        raise
    try:
        _check_opened_body(path, resolved.name, os.fstat(descriptor), directories, temp_root)
        with os.fdopen(descriptor, encoding="utf-8") as body_file:
            descriptor = -1
            return body_file.read()
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def assert_valid_body_file(body_file: str, allowed_base: str | None = None) -> None:
    """Validate a body file parameter for safe file access.

    Raises SystemExit if the file does not exist or escapes the allowed base.

    When allowed_base is None, accepts paths within either the repo root or
    any plausible system temp directory (TMPDIR, tempfile.gettempdir(), /tmp,
    or /private/tmp) or the repository git dir. The git-dir path supports
    transient reply bodies in linked worktrees where /tmp is unavailable and
    untracked files in the working tree are undesirable. The rule itself lives
    in :func:`is_allowed_body_file_path`.

    Args:
        body_file: The file path to validate.
        allowed_base: Optional base directory restriction.
    """
    from .api import error_and_exit  # lazy import to avoid cycle

    if not Path(body_file).exists():
        error_and_exit(f"Body file not found: {body_file}", 2)

    if allowed_base is not None:
        if not is_safe_file_path(body_file, allowed_base):
            error_and_exit(f"Body file path traversal not allowed: {body_file}", 2)
        return

    if not is_allowed_body_file_path(body_file):
        error_and_exit(f"Body file path traversal not allowed: {body_file}", 2)


def escaped_newline_body_error(body: str | None) -> str | None:
    """Detect a body whose line breaks arrived as literal backslash-n text.

    A caller that builds a Markdown body in a shell without escape
    interpretation, or in a language that passes the string through
    verbatim, sends the two characters backslash and n where a newline was
    meant. ``gh`` writes them literally and GitHub renders the whole body as
    one unbroken paragraph, losing every heading, list and table. Nothing
    errors, so the corruption is only visible to a human reading the
    rendered result later.

    The signal is the conjunction, not either half alone. A body may
    legitimately mention a backslash-n sequence inside a code fence while
    still carrying real line breaks, and that case must keep working. Only a
    body that has the sequence *and* no line break at all was, with near
    certainty, meant to have newlines.

    ``strip()`` guards the common single-line-plus-trailing-newline shape,
    which is what the two issues that prompted this check actually looked
    like.

    ``None`` is a live input, not just a test shape: edit_issue_body.py
    declares ``--body`` with ``default=None``, so the annotation has to
    admit it. mypy caught the narrower version on the diff-line ratchet.

    Args:
        body: The inline body text as received from the caller.

    Returns:
        An operator-facing message naming the remedy, or None when the body
        is fine.
    """
    if not body:
        return None
    count = body.count("\\n")
    if count == 0 or "\n" in body.strip():
        return None
    return (
        f"Body carries {count} literal backslash-n sequence(s) and no line "
        "break, so GitHub would render it as one unbroken paragraph and drop "
        "every heading, list and table. Write the body to a file and pass "
        "--body-file, which cannot express this error."
    )


def inline_body_error(body: str | None) -> str | None:
    """Return the first problem with an inline ``--body``, or None.

    Every skill script that accepts ``--body`` has to reject the same two
    shapes: a body that is empty or whitespace-only, and a body whose line
    breaks are literal backslash-n (see
    :func:`escaped_newline_body_error`). Keeping both checks here means a
    caller spends one branch instead of two, which matters because the
    ``main`` functions that host them are already past the complexity
    ceiling and carry a ``noqa: C901``.

    Args:
        body: The inline body text as received from the caller.

    Returns:
        An operator-facing message, or None when the body is usable.
    """
    if not body or not body.strip():
        return "Body cannot be empty."
    return escaped_newline_body_error(body)
