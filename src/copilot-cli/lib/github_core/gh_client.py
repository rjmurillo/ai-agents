"""Canonical: scripts/github_core/gh_client.py. Sync via scripts/sync_plugin_lib.py."""

from __future__ import annotations

import json
import logging
import subprocess
from typing import Any

logger = logging.getLogger(__name__)

_TIMEOUT = 30


class GhCliClient:
    """GitHubClient implementation that delegates to ``gh`` CLI subprocess calls.

    Follows the same error-handling and timeout conventions as
    :pymod:`scripts.github_core.api`.
    """

    def rest_get(self, endpoint: str) -> dict[str, Any]:
        """GET a single GitHub REST endpoint and return parsed JSON."""
        result = subprocess.run(
            ["gh", "api", endpoint],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"gh api GET {endpoint} failed: {result.stderr.strip()}"
            )
        response: dict[str, Any] = json.loads(result.stdout)
        return response

    def rest_post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST to a GitHub REST endpoint and return parsed JSON."""
        result = subprocess.run(
            ["gh", "api", endpoint, "-X", "POST", "--input", "-"],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"gh api POST {endpoint} failed: {result.stderr.strip()}"
            )
        response: dict[str, Any] = json.loads(result.stdout)
        return response

    def rest_patch(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        """PATCH a GitHub REST endpoint and return parsed JSON."""
        result = subprocess.run(
            ["gh", "api", endpoint, "-X", "PATCH", "--input", "-"],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
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

        result = subprocess.run(
            gh_args,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
        )
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
        """Return True if ``gh auth status`` exits 0."""
        try:
            result = subprocess.run(
                ["gh", "auth", "status"],
                capture_output=True,
                text=True,
                timeout=_TIMEOUT,
            )
            return result.returncode == 0
        except FileNotFoundError:
            logger.debug("GitHub CLI (gh) not found on PATH")
            return False
        except subprocess.TimeoutExpired:
            logger.debug("gh auth status timed out")
            return False
