"""GET-only gh transport and fail-loud paging for the code-scanning reader.

Used by ``get_pr_code_scanning_alerts.py``. The rules this module enforces come
from the ADR-041 amendment 2026-11-09
(``.project-toolkit/analysis/adr-041-review-caller-rules.md``) and
``lossless-queue-reads.md``:

* Every request is ``gh api --method GET``.
* A list is read until the response has no ``rel="next"`` link. A failed page, an
  unusable or repeated next link, a non-list page, or more than ``MAX_PAGES``
  pages raises ``SkipError``. A partial list is never returned.
* ``SkipError.reason`` is a fixed string. Text from GitHub never reaches it.

Stricter/looser/different than canonical
========================================
Not ``github_core.api.gh_api_paginated``: that helper stops on ``len(items) <
page_size`` and, on a failure after page 1, warns and returns the partial list.
Both break the rules above. This module keeps the same ``gh api`` transport and
the same ``classify_gh_failure_text`` classifier.

GitHub words the next link with the repository id (``/repositories/{id}/...``),
not the ``/repos/{owner}/{repo}/...`` path that was requested; observed on
2026-11-09 against rjmurillo/ai-agents.

Exit codes (ADR-035) carried on ``SkipError.exit_code``:
    3  request failed, paging incomplete, or response unusable
    4  authorization or not-found refusal, or gh unavailable
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

from github_core.api import GhAuthStatus, classify_gh_failure_text

EXIT_EXTERNAL = 3
EXIT_AUTH = 4
MAX_PAGES = 50
_GH_TIMEOUT_SECONDS = 30
_HTTP_STATUS = re.compile(r"\bHTTP\s+(\d{3})\b")
_NEXT_LINK = re.compile(r'<([^>]*)>\s*;[^,]*\brel="?next"?')
_HEADER_BREAK = re.compile(r"\r?\n\r?\n")
_REFUSED_STATUSES = frozenset({401, 403, 404})

#: gh transport: ``run(endpoint, accept)`` returns ``(headers, body)``.
Transport = Callable[[str, str | None], tuple[dict[str, str], str]]


class SkipError(Exception):
    """The read cannot complete. ``reason`` is a fixed string, never remote text."""

    def __init__(self, reason: str, exit_code: int = EXIT_EXTERNAL) -> None:
        super().__init__(reason)
        self.reason = reason
        self.exit_code = exit_code


def _failure_to_skip(text: str) -> SkipError:
    """Classify gh failure text into a SKIPPED reason with a fixed string."""
    match = _HTTP_STATUS.search(text)
    status = int(match.group(1)) if match else None
    gh_status = classify_gh_failure_text(text)
    if gh_status in (GhAuthStatus.RATE_LIMITED, GhAuthStatus.SECONDARY_RATE_LIMITED):
        return SkipError("GitHub rate limit refused the request", EXIT_EXTERNAL)
    if status in _REFUSED_STATUSES:
        return SkipError(f"authorization or not-found error (HTTP {status})", EXIT_AUTH)
    if status is not None:
        return SkipError(f"GitHub request failed (HTTP {status})", EXIT_EXTERNAL)
    return SkipError("GitHub request failed", EXIT_EXTERNAL)


def _split_response(stdout: str) -> tuple[dict[str, str], str]:
    """Split ``gh api --include`` output into lower-cased headers and the body."""
    parts = _HEADER_BREAK.split(stdout, maxsplit=1)
    if len(parts) != 2:
        raise SkipError("GitHub response had no header block")
    headers: dict[str, str] = {}
    for line in parts[0].splitlines()[1:]:
        name, sep, value = line.partition(":")
        if sep:
            headers[name.strip().lower()] = value.strip()
    return headers, parts[1]


def gh_get(endpoint: str, accept: str | None = None) -> tuple[dict[str, str], str]:
    """GET one endpoint through ``gh api`` and return ``(headers, body)``.

    Raises:
        SkipError: gh could not run, timed out, or answered with a failure.
    """
    command = ["gh", "api", "--include", "--method", "GET"]
    if accept:
        command += ["-H", f"Accept: {accept}"]
    command.append(endpoint)
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=_GH_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise SkipError("GitHub request timed out") from exc
    except OSError as exc:
        raise SkipError("gh could not be run", EXIT_AUTH) from exc
    if result.returncode != 0:
        raise _failure_to_skip(f"{result.stderr}\n{result.stdout}")
    return _split_response(result.stdout)


def parse_json(body: str) -> Any:
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise SkipError("GitHub response was not JSON") from exc


def _next_endpoint(link_header: str | None, request_path: str) -> str | None:
    """Return the endpoint named by ``rel="next"``, None when there is none.

    GitHub words the next link with the repository id, for example
    ``/repositories/1116049814/code-scanning/analyses?...&page=2``, not the
    ``/repos/{owner}/{repo}/...`` path that was requested (observed on
    2026-11-09). So the link is checked on its last two path segments
    (``code-scanning/analyses``) and then followed as given, with a
    ``/api/v3`` prefix removed because ``gh api`` adds it on GitHub Enterprise.

    Raises:
        SkipError: a next link exists but cannot be followed. That is a paging
            failure, not the end of the list.
    """
    if not link_header:
        return None
    match = _NEXT_LINK.search(link_header)
    if match is None:
        return None
    parts = urlsplit(match.group(1))
    tail = "/" + "/".join(request_path.strip("/").split("/")[-2:])
    if not parts.path.endswith(tail) or not parts.query:
        raise SkipError("paging failed: unusable next link")
    path = parts.path.lstrip("/").removeprefix("api/v3/")
    return f"{path}?{parts.query}"


def get_all_pages(transport: Transport, endpoint: str) -> list[Any]:
    """Read a list endpoint until the API reports no next page.

    Raises:
        SkipError: any page fails, a next link is unusable or repeats, a page is
            not a JSON list, or more than ``MAX_PAGES`` pages are returned.
    """
    request_path = "/" + endpoint.split("?", 1)[0]
    items: list[Any] = []
    seen = {endpoint}
    current = endpoint
    for _ in range(MAX_PAGES):
        headers, body = transport(current, None)
        page = parse_json(body)
        if not isinstance(page, list):
            raise SkipError("GitHub list response had an unexpected shape")
        items.extend(page)
        following = _next_endpoint(headers.get("link"), request_path)
        if following is None:
            return items
        if following in seen:
            raise SkipError("paging failed: next link repeats")
        seen.add(following)
        current = following
    raise SkipError(f"paging exceeded {MAX_PAGES} pages")


def get_object(transport: Transport, endpoint: str, accept: str | None = None) -> dict[str, Any]:
    """Read one JSON object endpoint."""
    _, body = transport(endpoint, accept)
    parsed = parse_json(body)
    if not isinstance(parsed, dict):
        raise SkipError("GitHub response had an unexpected shape")
    return parsed
