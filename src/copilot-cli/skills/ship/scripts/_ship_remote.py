"""Parse and classify a git remote URL for the ship scripts (ADR-127 decision 3 item 4).

Stdlib only, Python 3.10 floor. ``_ship_common`` loads this file by path and
re-exports ``remote_host`` and ``classify_host``; ``clean`` calls ``strip_userinfo``.
It also names the repository a remote URL or a PR URL points at (``RepoRef``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ADR-127 decision 3 item 4: a remote URL must match an allowed scheme list.
# git also accepts transports such as ext::, file://, and git://; none of
# them is a GitHub or Azure DevOps remote, so they are refused.
ALLOWED_URL_SCHEMES = frozenset({"https", "ssh"})
# The authority ends at the first /, ?, or # (RFC 3986), so an @ after it
# is path, query, or fragment, never userinfo.
_URL_HOST_RE = re.compile(r"^([A-Za-z][A-Za-z0-9+.-]*)://(?:[^/?#@]*@)?([^/?#:\s]+)")
_SCP_HOST_RE = re.compile(r"^(?:[^@/:\s]+@)?([^/:\s]+):(?![/:])\S")
# One or more DNS labels: letters, digits, inner dashes. No empty label,
# no trailing dot, no bracket literal, at least two characters in all.
_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
_PLAIN_HOST_RE = re.compile(rf"^(?=.{{2,253}}$){_LABEL}(?:\.{_LABEL})*$")
_ADO_HOSTS = frozenset({"dev.azure.com", "ssh.dev.azure.com"})


def remote_host(url: str) -> str | None:
    """Return the lowercase host of a git remote URL, or None when it is not allowed.

    Allowed forms: ``https://`` and ``ssh://`` URLs, and the scp-like
    ``[user@]host:path`` form. A local path, another scheme, and a transport
    such as ``ext::`` all return None.
    """
    url = url.strip()
    if "://" in url:
        match = _URL_HOST_RE.match(url)
        if match is None or match.group(1).lower() not in ALLOWED_URL_SCHEMES:
            return None
        return _plain_host(match.group(2).lower())
    if url.startswith(("/", ".", "~")):
        return None
    match = _SCP_HOST_RE.match(url)
    if match is None:
        return None
    return _plain_host(match.group(1).lower())


def _plain_host(host: str) -> str | None:
    """Return ``host`` when it is a plain DNS-style name, else None.

    A host is at least two characters, starts with a letter or digit, and
    holds only letters, digits, dots, and dashes. That refuses a Windows
    drive path (C:\\repo), an ssh option (-oX=y:z), and a bracket literal.
    """
    if _PLAIN_HOST_RE.fullmatch(host) is None:
        return None
    return host


def classify_host(host: str) -> str:
    """Map a parsed host to ``ado`` or ``github``. Matches the host, not a substring."""
    if host in _ADO_HOSTS or host.endswith(".visualstudio.com"):
        return "ado"
    return "github"


# A token ends only at ASCII whitespace. Unicode spaces and control
# characters stay inside it, so a password holding one is still cut.
_ASCII_SPACE = frozenset(" \t\n\r\v\f")


def strip_userinfo(text: str) -> str:
    """Drop everything between ``://`` and the last ``@`` of the same token.

    A token is the run of non-space characters after ``://``. Cutting to the
    last ``@`` removes a password that itself holds ``@`` or ``/``, at any
    length. A path segment holding ``@`` is over-redacted; that is the safe
    side. One pass over the text, so a long value stays linear.
    """
    out: list[str] = []
    start = 0
    while True:
        marker = text.find("://", start)
        if marker < 0:
            out.append(text[start:])
            return "".join(out)
        token_start = marker + 3
        token_end = token_start
        while token_end < len(text) and text[token_end] not in _ASCII_SPACE:
            token_end += 1
        token = text[token_start:token_end]
        out.append(text[start:token_start])
        out.append(token[token.rfind("@") + 1 :])
        start = token_end


# A GitHub PR URL: https://<host>/<owner>/<repo>/pull/<number>, as gh prints it.
_PR_URL_RE = re.compile(
    r"^https://(?P<host>[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?)"
    r"/(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+)/pull/(?P<number>[0-9]+)/?$"
)
_URL_PATH_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://[^/?#]*/([^?#\s]*)")
_SCP_PATH_RE = re.compile(r"^(?:[^@/:\s]+@)?[^/:\s]+:([^/\s]\S*)$")
_NAME_RE = re.compile(r"[A-Za-z0-9_.-]+")


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
    host = remote_host(url)
    match = (_URL_PATH_RE if "://" in url else _SCP_PATH_RE).match(url)
    if host is None or match is None:
        return None
    parts = match.group(1).strip("/").removesuffix(".git").split("/")
    if len(parts) < 2 or not all(_NAME_RE.fullmatch(part) for part in parts[-2:]):
        return None
    return RepoRef(host, parts[-2], parts[-1])
