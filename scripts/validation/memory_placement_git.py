"""Git and index reads for check_memory_placement.py.

Every function here talks to git or the filesystem; the classifier in
check_memory_placement.py stays pure. A git failure under ``--staged`` is a
``ConfigError`` (exit 2), never a silent fallback to working-tree content.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from checks_common import _git_subprocess_env, _run_subprocess  # noqa: E402

GIT_READ_TIMEOUT = 30


class ConfigError(Exception):
    """Raised for a usage or environment problem; ``main`` turns it into exit 2."""


def repo_root() -> Path | None:
    """Return the repository root for the current directory, or None."""
    code, out, _ = _run_subprocess(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=Path.cwd(),
        env=_git_subprocess_env(),
    )
    if code != 0:
        return None
    return Path(out.strip()).resolve()


def valid_ref(base: str) -> bool:
    """Reject a blank, control-character, or option-shaped (leading ``-``) ref."""
    return bool(base.strip()) and not base.startswith("-") and base.isprintable()


def base_tree_paths(repo_root: Path, base: str) -> set[str] | None:
    """Return every path git tracks at ``base``, or None if the ref is unusable."""
    if not valid_ref(base):
        return None
    code, out, _ = _run_subprocess(
        ["git", "ls-tree", "-r", "-z", "--name-only", base],
        cwd=repo_root,
        env=_git_subprocess_env(),
    )
    if code != 0:
        return None
    return {entry for entry in out.split("\0") if entry}


def index_paths(repo_root: Path) -> set[str]:
    """Return every path in the git index; a git failure is a config error."""
    code, out, err = _run_subprocess(
        ["git", "ls-files", "-z", "--cached"],
        timeout=GIT_READ_TIMEOUT,
        cwd=repo_root,
        env=_git_subprocess_env(),
    )
    if code != 0:
        raise ConfigError(f"git ls-files failed ({code}): {err.strip()}")
    return {entry for entry in out.split("\0") if entry}


def read_candidate(repo_root: Path, relpath: str, abspath: Path, index: set[str] | None) -> str:
    """Return the index blob when ``relpath`` is staged, else the tree file.

    Under ``--staged`` a git failure is an infrastructure error, never a
    silent fallback to working-tree content.
    """
    if index is None or relpath not in index:
        return abspath.read_text(encoding="utf-8", errors="replace")
    code, out, err = _run_subprocess(
        ["git", "show", f":{relpath}"],
        timeout=GIT_READ_TIMEOUT,
        cwd=repo_root,
        env=_git_subprocess_env(),
    )
    if code != 0:
        raise ConfigError(f"git show :{relpath} failed ({code}): {err.strip()}")
    return str(out)
