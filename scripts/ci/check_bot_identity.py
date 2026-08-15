"""Report which GitHub identity a CI credential actually resolves to.

ADR-026 Decision 5 configures ``BOT_PAT`` so automated actions run as the
``rjmurillo-bot`` service account (id 250269933) with its own API budget.
Issue #4607 measured that the secret held a token for the human account
``rjmurillo`` (id 6811113), so CI and every interactive agent session shared
one rate-limit budget, and nothing in any run log made that visible: the only
identity diagnostic (``verify_github_auth.py``) is gated behind
``enable-diagnostics: 'true'``, which defaults to false, and it prints the
login without comparing the id. A configured control with no test is an
assumption (retrospective 2026-08-05-pr-queue-and-doctrine.md, Learning 4).

This module makes the acceptance criterion of issue #4607 checkable from any
run log: it probes ``GET /user`` with the supplied credential and reports the
resolved ``login`` and ``id`` against the expected bot id, loudly.

Verdicts:

- ``MATCH``: probe succeeded and the id equals ``EXPECTED_BOT_ID``. Exit 0.
- ``MISMATCH``: probe succeeded but the id differs. The credential is a real
  token for the wrong account; only the repository owner can rotate it. Warns
  by default; ``IDENTITY_STRICT`` makes it exit 4 (auth).
- ``MISSING``: no credential supplied (fork PRs see empty secrets). Warns by
  default; strict mode exits 2 (config).
- ``UNKNOWN``: the probe failed (HTTP error, network, malformed payload). This
  is never reported as a pass. Warns by default; strict mode exits 3
  (external).

The workflow step runs this file with bare ``python3``, so every import must
be stdlib-only (see .claude/rules/ci-scripts.md MUST 18).
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3
EXIT_AUTH = 4

# rjmurillo-bot, verified live in issue #4607 (`gh api users/rjmurillo-bot`).
DEFAULT_EXPECTED_BOT_ID = "250269933"
DEFAULT_EXPECTED_BOT_LOGIN = "rjmurillo-bot"
DEFAULT_TOKEN_LABEL = "BOT_PAT"
DEFAULT_API_URL = "https://api.github.com"

VERDICT_MATCH = "MATCH"
VERDICT_MISMATCH = "MISMATCH"
VERDICT_MISSING = "MISSING"
VERDICT_UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class ProbeResult:
    """Outcome of one ``GET /user`` probe. ``login``/``account_id`` are set
    only when ``ok`` is true; ``error`` describes the failure otherwise."""

    ok: bool
    login: str = ""
    account_id: str = ""
    error: str = ""


def probe_user(token: str, api_url: str = DEFAULT_API_URL) -> ProbeResult:
    """Resolve the token's identity via ``GET /user``.

    Never raises: every failure collapses to ``ProbeResult(ok=False)`` so the
    caller reports UNKNOWN instead of crashing the step. The token is never
    included in any returned string.

    Only https URLs are opened. ``api_url`` comes from ``GITHUB_API_URL``,
    which the runner sets, but urllib would also follow ``file://``; refusing
    any other scheme removes that class outright (CWE-22 adjacent, flagged by
    semgrep dynamic-urllib-use-detected).
    """
    scheme = urllib.parse.urlsplit(api_url).scheme
    if scheme != "https":
        return ProbeResult(ok=False, error=f"refusing non-https API URL scheme {scheme!r}")
    request = urllib.request.Request(
        f"{api_url.rstrip('/')}/user",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "check-bot-identity",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return ProbeResult(ok=False, error=f"HTTP {exc.code} from /user")
    except urllib.error.URLError as exc:
        return ProbeResult(ok=False, error=f"network error: {exc.reason}")
    except (json.JSONDecodeError, UnicodeDecodeError, TimeoutError) as exc:
        return ProbeResult(ok=False, error=f"unreadable /user payload: {exc}")

    login = payload.get("login")
    account_id = payload.get("id")
    if not isinstance(login, str) or not isinstance(account_id, int):
        return ProbeResult(ok=False, error="/user payload missing login or id")
    return ProbeResult(ok=True, login=login, account_id=str(account_id))


def _append_line(path_value: str | None, line: str) -> None:
    if not path_value:
        return
    with Path(path_value).open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def _emit(verdict: str, detail: str, environ: dict[str, str]) -> None:
    """Write the verdict everywhere a reader might look: the log, the job
    summary page, and step outputs for downstream steps."""
    _append_line(
        environ.get("GITHUB_STEP_SUMMARY"),
        f"### Bot identity check: {verdict}\n\n{detail}",
    )
    output_path = environ.get("GITHUB_OUTPUT")
    _append_line(output_path, f"identity_verdict={verdict}")


def _strict(environ: dict[str, str]) -> bool:
    return environ.get("IDENTITY_STRICT", "").strip().lower() in {"1", "true", "yes"}


def check_bot_identity(
    environ: dict[str, str],
    probe: Callable[[str, str], ProbeResult] = probe_user,
) -> int:
    label = environ.get("TOKEN_LABEL") or DEFAULT_TOKEN_LABEL
    expected_id = environ.get("EXPECTED_BOT_ID") or DEFAULT_EXPECTED_BOT_ID
    expected_login = environ.get("EXPECTED_BOT_LOGIN") or DEFAULT_EXPECTED_BOT_LOGIN
    strict = _strict(environ)

    if not expected_id.isdigit():
        print(f"::error::EXPECTED_BOT_ID must be a numeric account id, got {expected_id!r}")
        return EXIT_CONFIG

    token = environ.get("IDENTITY_TOKEN", "")
    if not token:
        detail = (
            f"{label} is empty in this run (fork PRs and unset secrets both look "
            "like this). Identity cannot be verified."
        )
        print(f"::warning::{label} identity {VERDICT_MISSING}: {detail}")
        _emit(VERDICT_MISSING, detail, environ)
        return EXIT_CONFIG if strict else EXIT_OK

    result = probe(token, environ.get("GITHUB_API_URL") or DEFAULT_API_URL)

    if not result.ok:
        detail = (
            f"Could not resolve the {label} identity: {result.error}. "
            "This is UNKNOWN, not a pass; the acceptance criterion of issue "
            "#4607 is unverified in this run."
        )
        print(f"::warning::{label} identity {VERDICT_UNKNOWN}: {detail}")
        _emit(VERDICT_UNKNOWN, detail, environ)
        return EXIT_EXTERNAL if strict else EXIT_OK

    identity = f"login={result.login} id={result.account_id}"
    if result.account_id == expected_id:
        detail = (
            f"{label} resolves to {identity} (expected {expected_id}). CI has its own API budget."
        )
        print(f"{label} identity {VERDICT_MATCH}: {detail}")
        print(f"::notice::{label} identity {VERDICT_MATCH}: {identity}")
        _emit(VERDICT_MATCH, detail, environ)
        return EXIT_OK

    detail = (
        f"{label} resolves to {identity}, expected {expected_login} "
        f"id={expected_id}. CI shares this account's REST and GraphQL budget "
        "with every session using the same account (issue #4607, ADR-026 "
        f"Decision 5). Only the repository owner can fix this: mint a PAT while "
        f"signed in as {expected_login}, store it as the {label} repository "
        "secret, then confirm this check reports MATCH."
    )
    level = "error" if strict else "warning"
    print(f"::{level}::{label} identity {VERDICT_MISMATCH}: {detail}")
    _emit(VERDICT_MISMATCH, detail, environ)
    return EXIT_AUTH if strict else EXIT_OK


def main(
    argv: Sequence[str] | None = None,
    probe: Callable[[str, str], ProbeResult] = probe_user,
    environ: dict[str, str] | None = None,
) -> int:
    if argv:
        print("error: no arguments are supported", file=sys.stderr)
        return EXIT_CONFIG
    env = dict(os.environ) if environ is None else environ
    return check_bot_identity(env, probe=probe)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
