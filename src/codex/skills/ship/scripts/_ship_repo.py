"""Map PR and remote URLs to the hosted repository they name, and find the local remote that tracks one.

Stdlib only, Python 3.10 floor. ``RepoRef`` names a repository on a host. ``pr_repo``
reads it from a PR URL and ``repo_ref`` from a git remote URL. ``upstream`` and
``remote_for`` use them to find the repository that owns a PR and the remote that
tracks it.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import _ship_common as common
    from ship_detect import Context
else:
    common = sys.modules["_ship_common"]

# A GitHub PR URL: https://<host>/<owner>/<repo>/pull/<number>, as gh prints it.
_PR_URL_RE = re.compile(
    r"^https://(?P<host>[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?)"
    r"/(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+)/pull/(?P<number>[0-9]+)/?$"
)
_URL_PATH_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://[^/?#]*/([^?#\s]*)")
_SCP_PATH_RE = re.compile(r"^(?:[^@/:\s]+@)?[^/:\s]+:([^/\s]\S*)$")
_NAME_RE = re.compile(r"[A-Za-z0-9_.-]+")
_REMOTE_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


@dataclass(frozen=True)
class RepoRef:
    """A repository on a host: from a PR URL, or from a git remote URL."""

    host: str
    owner: str
    repo: str

    @property
    def key(self) -> tuple[str, str, str]:
        """The identity to compare: host, owner, and repository names are case-insensitive."""
        return (self.host.lower(), self.owner.lower(), self.repo.lower())


def pr_repo(url: str, pr: int) -> RepoRef | None:
    """The repository that owns PR ``pr``, read from its URL; None when the URL is not that PR's."""
    match = _PR_URL_RE.match(url)
    if match is None or int(match["number"]) != pr:
        return None
    return RepoRef(match["host"].lower(), match["owner"], match["repo"])


def repo_ref(url: str) -> RepoRef | None:
    """The repository a remote URL names, or None when it is not an allowed ``owner/repo`` form.

    Reads ``https://``, ``ssh://``, and scp-like URLs, with or without ``.git``, a trailing
    slash, userinfo, or a port. The last two path parts are the owner and repository.
    """
    url = url.strip()
    host = common.remote_host(url)
    match = (_URL_PATH_RE if "://" in url else _SCP_PATH_RE).match(url)
    if host is None or match is None:
        return None
    parts = match.group(1).strip("/").removesuffix(".git").split("/")
    if len(parts) < 2 or not all(_NAME_RE.fullmatch(part) for part in parts[-2:]):
        return None
    return RepoRef(host, parts[-2], parts[-1])


def _remote_repo(ctx: Context, name: str) -> RepoRef | None:
    done = common.git(["remote", "get-url", name], cwd=ctx.root)
    return repo_ref(done.stdout) if done.returncode == 0 else None


def upstream(ctx: Context) -> RepoRef | None:
    """The repository that owns the open PR when origin is another one, else None.

    None also covers a PR URL that does not parse (Azure DevOps) and an origin
    URL that does not name an owner and repository: both keep ``origin``.
    """
    owner = None if ctx.pr is None else pr_repo(ctx.pr_url, ctx.pr)
    origin = _remote_repo(ctx, "origin") if owner is not None else None
    if owner is None or origin is None or owner.key == origin.key:
        return None
    return owner


def remote_for(ctx: Context, repo: RepoRef) -> str | None:
    """A git remote whose URL names ``repo``, or None."""
    names = common.git(["remote"], cwd=ctx.root).stdout.split()
    for name in names:
        found = _remote_repo(ctx, name) if _REMOTE_NAME_RE.fullmatch(name) else None
        if found is not None and found.key == repo.key:
            return name
    return None
