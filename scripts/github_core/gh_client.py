"""GhCliClient: concrete GitHubClient backed by the ``gh`` CLI."""

from __future__ import annotations

import json
import logging
import subprocess
from typing import Any

from scripts.github_core.api import is_gh_authenticated

logger = logging.getLogger(__name__)

_TIMEOUT = 30


def _run(args: list[str], *, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    """Run a ``gh`` command and capture its output as UTF-8 text.

    ``gh`` writes raw UTF-8, including in JSON string values, which are not
    escaped. Without an explicit ``encoding`` Python decodes with the locale's
    preferred codec, so a cp1252 or cp932 runner decodes the same bytes into
    different characters and ``json.loads`` accepts the result. That is silent
    corruption, and a caller that writes the value back to GitHub persists it.
    Decoding stays strict: a byte sequence that is not valid UTF-8 raises
    instead of being silently replaced, because a mangled identifier written
    back to GitHub is worse than a visible failure.
    """

    return subprocess.run(
        args,
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=_TIMEOUT,
    )


class GhCliClient:
    """GitHubClient implementation that delegates to ``gh`` CLI subprocess calls.

    Follows the same error-handling and timeout conventions as
    :pymod:`scripts.github_core.api`.
    """

    def rest_get(self, endpoint: str) -> dict[str, Any]:
        """GET a single GitHub REST endpoint and return parsed JSON."""
        result = _run(["gh", "api", endpoint])
        if result.returncode != 0:
            raise RuntimeError(
                f"gh api GET {endpoint} failed: {result.stderr.strip()}"
            )
        response: dict[str, Any] = json.loads(result.stdout)
        return response

    def rest_post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST to a GitHub REST endpoint and return parsed JSON."""
        result = _run(
            ["gh", "api", endpoint, "-X", "POST", "--input", "-"],
            stdin=json.dumps(payload),
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"gh api POST {endpoint} failed: {result.stderr.strip()}"
            )
        response: dict[str, Any] = json.loads(result.stdout)
        return response

    def rest_patch(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        """PATCH a GitHub REST endpoint and return parsed JSON."""
        result = _run(
            ["gh", "api", endpoint, "-X", "PATCH", "--input", "-"],
            stdin=json.dumps(payload),
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"gh api PATCH {endpoint} failed: {result.stderr.strip()}"
            )
        response: dict[str, Any] = json.loads(result.stdout)
        return response

    def graphql(
        self, query: str, variables: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Execute a GraphQL query via ``gh api graphql`` and return the data dict."""
        if variables is None:
            variables = {}

        gh_args = ["gh", "api", "graphql", "-f", f"query={query}"]
        for key, value in variables.items():
            if isinstance(value, (int, bool)):
                gh_args.extend(["-F", f"{key}={value}"])
            else:
                gh_args.extend(["-f", f"{key}={value}"])

        result = _run(gh_args)
        if result.returncode != 0:
            raise RuntimeError(
                f"GraphQL request failed: {result.stderr.strip()}"
            )

        parsed = json.loads(result.stdout)
        if parsed.get("errors"):
            messages = [e.get("message", str(e)) for e in parsed["errors"]]
            raise RuntimeError(f"GraphQL errors: {'; '.join(messages)}")

        data: dict[str, Any] = parsed.get("data", {})
        return data

    def is_authenticated(self) -> bool:
        """Return True if the token authenticates on any supported transport.

        Delegates to :func:`scripts.github_core.api.is_gh_authenticated` rather
        than reading ``gh auth status``'s exit code. That exit code is nonzero
        for a 5xx, a transport failure, and a quota refusal as well as for a bad
        token, so collapsing it to a bool reports a GitHub outage as an auth
        failure (issue #3139). One classifier, one answer.
        """
        return is_gh_authenticated()
