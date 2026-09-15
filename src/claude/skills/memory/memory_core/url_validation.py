"""URL validation utilities for memory skill HTTP operations.

Provides scheme validation to prevent SSRF (CWE-918) and path traversal
(CWE-22) vulnerabilities when using urllib with user-controlled endpoints.
"""

from __future__ import annotations

from urllib.parse import urlparse

ALLOWED_URL_SCHEMES = frozenset({"http", "https"})


def validate_http_url(endpoint: str) -> str:
    """Reject non-HTTP(S) schemes before passing a URL to urllib.

    ``urllib.request.urlopen`` accepts ``file://``, ``ftp://``, and other
    schemes by default; an attacker who controls the endpoint argument
    could read arbitrary local files or reach unintended services.
    Restricting the scheme to http/https eliminates that class of bug
    (semgrep ``request-with-tainted-url-from-urllib``, CWE-918 SSRF,
    CWE-22 path traversal via file:// scheme).

    Args:
        endpoint: URL string to validate.

    Returns:
        The validated endpoint (unchanged).

    Raises:
        ValueError: If the URL scheme is not http or https.
    """
    parsed = urlparse(endpoint)
    if parsed.scheme not in ALLOWED_URL_SCHEMES:
        raise ValueError(
            f"endpoint scheme {parsed.scheme!r} not allowed; "
            f"only {sorted(ALLOWED_URL_SCHEMES)} accepted"
        )
    return endpoint
