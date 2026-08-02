"""Input validation: GitHub name validation, path traversal prevention."""

from __future__ import annotations

import os
import re
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
        return resolved_path == resolved_base or resolved_path.startswith(
            resolved_base + os.sep
        )
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


def assert_valid_body_file(body_file: str, allowed_base: str | None = None) -> None:
    """Validate a body file parameter for safe file access.

    Raises SystemExit if the file does not exist or escapes the allowed base.

    When allowed_base is None, accepts paths within either the repo root or
    any plausible system temp directory (TMPDIR, tempfile.gettempdir(), /tmp,
    or /private/tmp) or the repository git dir. The git-dir path supports
    transient reply bodies in linked worktrees where /tmp is unavailable and
    untracked files in the working tree are undesirable.

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

    if is_safe_file_path(body_file, None):
        return

    for temp_root in _candidate_temp_roots():
        if is_safe_file_path(body_file, temp_root):
            return

    for git_root in _candidate_git_dir_roots():
        if is_safe_file_path(body_file, git_root):
            return

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
