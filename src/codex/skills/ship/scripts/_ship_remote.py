"""Parse and classify a git remote URL for the ship scripts (ADR-127 decision 3 item 4).

Stdlib only, Python 3.10 floor. ``_ship_common`` loads this file by path and
re-exports ``remote_host`` and ``classify_host``.
"""

from __future__ import annotations

import re

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
