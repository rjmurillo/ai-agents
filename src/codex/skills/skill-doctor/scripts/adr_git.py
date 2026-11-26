"""The one git runner for adr_drift.py: argument lists, no shell, a timeout, no prompts.

python3, stdlib only, no network.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import unquote

GIT_TIMEOUT_SECONDS = 120
# The variables `git rev-parse --local-env-vars` lists, plus the namespace and discovery
# ceiling. Inherited, any of them points git at another repository whatever `-C` says.
# skill-bootstrap's adr_scan.py strips the same set; a test compares the two.
LOCAL_GIT_ENV = frozenset(
    "GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_CEILING_DIRECTORIES GIT_COMMON_DIR GIT_CONFIG "
    "GIT_CONFIG_COUNT GIT_CONFIG_PARAMETERS GIT_DIR "
    "GIT_GRAFT_FILE GIT_IMPLICIT_WORK_TREE GIT_INDEX_FILE GIT_NAMESPACE GIT_NO_REPLACE_OBJECTS "
    "GIT_OBJECT_DIRECTORY GIT_PREFIX GIT_REPLACE_REF_BASE GIT_SHALLOW_FILE GIT_WORK_TREE".split()
)


class GitError(Exception):
    """A git command failed, timed out, or could not run.

    `returncode` is git's exit status when it ran and failed, else None.
    `timed_out` is True when the command hit GIT_TIMEOUT_SECONDS.
    """

    def __init__(
        self, message: str, returncode: int | None = None, timed_out: bool = False
    ) -> None:
        super().__init__(message)
        self._returncode = returncode
        self._timed_out = timed_out

    @property
    def returncode(self) -> int | None:
        return self._returncode

    @property
    def timed_out(self) -> bool:
        return self._timed_out


def run_git(repo: Path, args: Sequence[str]) -> str:
    """Run `git -C repo ARGS` with an argument list and return stdout."""
    argv = ["git", "-C", str(repo), "-c", "core.quotepath=off", *args]
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=GIT_TIMEOUT_SECONDS,
            stdin=subprocess.DEVNULL,
            env=_git_env(),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise GitError(
            f"git {args[0] if args else ''} timed out after {GIT_TIMEOUT_SECONDS} s", timed_out=True
        ) from exc
    except OSError as exc:
        raise GitError(f"git {args[0] if args else ''} could not run: {exc}") from exc
    if proc.returncode != 0:
        tail = proc.stderr.strip().splitlines()[-1:] or ["no stderr"]
        raise GitError(
            f"git {args[0] if args else ''} exited {proc.returncode}: {tail[0]}", proc.returncode
        )
    return proc.stdout


def _git_env() -> dict[str, str]:
    """No repository redirection, no prompt, no lock writes, and no replacement objects."""
    env = {key: value for key, value in os.environ.items() if key not in LOCAL_GIT_ENV}
    env.update(GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0", GIT_NO_REPLACE_OBJECTS="1")
    # Defense in depth: history reads no blob today, and this stops any lazy fetch of a
    # missing object from a promisor remote if a later command would need one.
    env["GIT_NO_LAZY_FETCH"] = "1"
    return env


# GIT_NO_LAZY_FETCH came in git 2.45.1 and the May 2024 releases of 2.39 to 2.44. An older
# git ignores it, so a partial clone is refused there. Copied from skill-bootstrap's
# adr_scan.py; a test compares the two.
NO_LAZY_FETCH_GIT = (2, 45, 1)
NO_LAZY_FETCH_BACKPORTS = {(2, 39): 4, (2, 40): 2, (2, 41): 1, (2, 42): 2, (2, 43): 4, (2, 44): 1}
PROMISOR = re.compile(
    r"extensions\.partialclone \S|remote\..*\.partialclonefilter(?: |\Z)"
    r"|remote\..*\.promisor(?:\Z| (?!false|no|off|0\b)\S)"
)
GIT_VERSION = re.compile(r"git version ([0-9]+)\.([0-9]+)\.([0-9]+)", re.ASCII)


def partial_filters(repo: Path) -> list[str] | None:
    """The partial-clone filters of a repository (possibly empty), or None for a full clone."""
    keys = r"^(extensions\.partialclone|remote\..*\.(promisor|partialclonefilter))$"
    try:
        config = run_git(repo, ["config", "--get-regexp", keys]).lower()
    except GitError as exc:
        if exc.returncode != 1:  # 1 means no key matched
            raise
        return None
    lines = config.splitlines()
    if not any(PROMISOR.match(line) for line in lines):
        return None
    return [line.split(" ", 1)[1] for line in lines if ".partialclonefilter " in line]


def old_git_refusal(repo: Path) -> str | None:
    """Why a partial clone must not be scanned with this git, or None when git honors
    GIT_NO_LAZY_FETCH. An unparsed version is treated as too old."""
    line = run_git(repo, ["version"]).strip()
    found = GIT_VERSION.match(line)
    version = tuple(int(part) for part in found.groups()) if found else (0, 0, 0)
    floor = NO_LAZY_FETCH_BACKPORTS.get(version[:2])
    if version >= NO_LAZY_FETCH_GIT or (floor is not None and version[2] >= floor):
        return None
    return (
        f"this is a partial clone, and {line or 'this git'} lacks GIT_NO_LAZY_FETCH (it came in"
        " 2.45.1 and the May 2024 backports), so it may fetch from the remote;"
        " upgrade git or scan a full clone"
    )


def keeps_trees(spec: str) -> bool:
    """True when a filter spec omits only blobs: `blob:` and `sparse:` parts, also inside a
    `combine:` spec. Any other part (`tree:`, `object:type=`) can drop trees."""
    parts = spec.removeprefix("combine:").split("+") if spec.startswith("combine:") else [spec]
    return all(unquote(part).startswith(("blob:", "sparse:")) for part in parts)


def partial_clone_refusal(repo: Path) -> str | None:
    """Why a scan must not run here, or None. A clone that omits only blobs scans: history
    reads only trees. A filter that can drop trees is refused, and so is any partial clone
    on an old git, which might fetch."""
    filters = partial_filters(repo)
    if filters is None:
        return None
    dropping = [spec for spec in filters if not keeps_trees(spec)]
    if dropping:
        return (
            f"this partial clone's filter ({dropping[0]}) can omit the trees the history read"
            " needs; scan a full or blobless clone"
        )
    return old_git_refusal(repo)
