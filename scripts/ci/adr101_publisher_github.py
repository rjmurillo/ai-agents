"""GitHub API access for the ADR-101 requirement 2a publisher (issue #5245).

Two tokens, never mixed. The read token is the workflow's own ``GITHUB_TOKEN``
(``contents: read``, ``pull-requests: read``, ``actions: read``): it reads the
pull request pointers and the triggering workflow run. The App token is the
short-lived installation token (``checks: write``, metadata read): it writes and
reads the check run. A check run authored through the App token carries the
App's id, which is the property a ruleset can pin by ``integration_id``.

Hardening, because this job holds credentials in a public repository:

  * one fixed host, ``https://api.github.com``; a redirect raises instead of
    being followed, so a token is never replayed to another host;
  * the repository name is validated before it reaches a URL path;
  * a response is read up to one MiB and must parse to a JSON object;
  * an error carries the status code and a fixed phrase, never the response body
    or the request, because a run log in a public repository is world readable.

Standard library only (``ci-scripts.md`` MUST 18).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from email.message import Message
from typing import IO, Any, Protocol

from scripts.ci.adr101_publisher_inputs import CHECK_NAME, is_number, is_repository

API_ROOT = "https://api.github.com"
TIMEOUT_SECONDS = 30
MAX_RESPONSE_BYTES = 1024 * 1024
_MAX_TEXT = 500


class ApiError(Exception):
    """An API call failed. ``status`` is 0 for a transport or shape failure."""

    def __init__(self, status: int, phrase: str) -> None:
        super().__init__(f"GitHub API call failed ({phrase}, status {status})")
        self.status = status
        self.phrase = phrase


@dataclass(frozen=True, slots=True)
class PullState:
    """The pointers of a pull request at the moment they were read."""

    head_sha: str
    base_sha: str
    base_ref: str = "main"


@dataclass(frozen=True, slots=True)
class RunState:
    """The facts of the triggering workflow run that the publisher cross-checks."""

    head_sha: str
    status: str


@dataclass(frozen=True, slots=True)
class CheckRunState:
    """A check run as GitHub reports it back."""

    check_id: int
    name: str
    head_sha: str
    conclusion: str
    external_id: str
    app_id: str


class Opener(Protocol):
    """The one method of ``OpenerDirector`` this client uses, so a test can fake it."""

    def open(
        self,
        fullurl: urllib.request.Request,
        data: None = None,
        timeout: float | None = None,
    ) -> AbstractContextManager[IO[bytes]]: ...


class PublisherApi(Protocol):
    """What the publisher needs, so a test can stand in for the network."""

    def get_pull(self, number: str) -> PullState: ...

    def get_run(self, run_id: str) -> RunState: ...

    def create_check_run(
        self, head_sha: str, conclusion: str, external_id: str, title: str, summary: str
    ) -> int: ...

    def get_check_run(self, check_id: int) -> CheckRunState: ...

    def set_conclusion(self, check_id: int, conclusion: str, summary: str) -> None: ...


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse every redirect so an Authorization header cannot leave the host."""

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: Message,
        newurl: str,
    ) -> urllib.request.Request | None:
        raise ApiError(code, "redirect refused")


def _opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(_NoRedirect())


def _field(payload: Mapping[str, Any], *path: str) -> object:
    """Walk ``path`` through nested objects, raising on a missing or null link."""
    node: object = payload
    for key in path:
        if not isinstance(node, Mapping) or node.get(key) is None:
            raise ApiError(0, f"response lacks {'.'.join(path)}")
        node = node[key]
    return node


def _text(payload: Mapping[str, Any], *path: str) -> str:
    value = _field(payload, *path)
    if not isinstance(value, str):
        raise ApiError(0, f"{'.'.join(path)} is not text")
    return value


def _number_text(payload: Mapping[str, Any], *path: str) -> str:
    value = _field(payload, *path)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ApiError(0, f"{'.'.join(path)} is not an integer")
    return str(value)


class GitHubApi:
    """The real client. Holds both tokens and never prints either."""

    def __init__(
        self, repository: str, read_token: str, app_token: str, opener: Opener | None = None
    ) -> None:
        if not is_repository(repository):
            raise ValueError("repository must be owner/name")
        self._repository = repository
        self._read_token = read_token
        self._app_token = app_token
        self._opener: Opener
        if opener is None:
            self._opener = _opener()
        else:
            self._opener = opener

    def _call(
        self, token: str, method: str, path: str, body: Mapping[str, Any] | None = None
    ) -> Mapping[str, Any]:
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            f"{API_ROOT}/repos/{self._repository}{path}", data=data, method=method
        )
        request.add_header("Authorization", f"Bearer {token}")
        request.add_header("Accept", "application/vnd.github+json")
        request.add_header("X-GitHub-Api-Version", "2022-11-28")
        request.add_header("User-Agent", "adr101-publisher")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with self._opener.open(request, timeout=TIMEOUT_SECONDS) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            raise ApiError(exc.code, "http error") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise ApiError(0, "transport error") from None
        return _parse_object(raw)

    def get_pull(self, number: str) -> PullState:
        """Read the pull request's current head and base SHAs."""
        if not is_number(number):
            raise ValueError("pull request number must be numeric")
        payload = self._call(self._read_token, "GET", f"/pulls/{number}")
        return PullState(
            head_sha=_text(payload, "head", "sha"),
            base_sha=_text(payload, "base", "sha"),
            base_ref=_text(payload, "base", "ref"),
        )

    def get_run(self, run_id: str) -> RunState:
        """Read the triggering workflow run's head SHA and status."""
        if not is_number(run_id):
            raise ValueError("run id must be numeric")
        payload = self._call(self._read_token, "GET", f"/actions/runs/{run_id}")
        return RunState(head_sha=_text(payload, "head_sha"), status=_text(payload, "status"))

    def create_check_run(
        self, head_sha: str, conclusion: str, external_id: str, title: str, summary: str
    ) -> int:
        """Create a completed check run through the App token; return its id."""
        body = {
            "name": CHECK_NAME,
            "head_sha": head_sha,
            "status": "completed",
            "conclusion": conclusion,
            "external_id": external_id,
            "output": {"title": title[:_MAX_TEXT], "summary": summary[:_MAX_TEXT]},
        }
        payload = self._call(self._app_token, "POST", "/check-runs", body)
        return int(_number_text(payload, "id"))

    def get_check_run(self, check_id: int) -> CheckRunState:
        """Read a check run back, including the id of the App that authored it."""
        payload = self._call(self._app_token, "GET", f"/check-runs/{int(check_id)}")
        return CheckRunState(
            check_id=int(check_id),
            name=_text(payload, "name"),
            head_sha=_text(payload, "head_sha"),
            conclusion=_text(payload, "conclusion"),
            external_id=_text(payload, "external_id"),
            app_id=_number_text(payload, "app", "id"),
        )

    def set_conclusion(self, check_id: int, conclusion: str, summary: str) -> None:
        """Change a check run's conclusion, used to retract a success."""
        output = {"title": conclusion, "summary": summary[:_MAX_TEXT]}
        body = {"conclusion": conclusion, "output": output}
        self._call(self._app_token, "PATCH", f"/check-runs/{int(check_id)}", body)


def _parse_object(raw: bytes) -> Mapping[str, Any]:
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ApiError(0, "response too large")
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise ApiError(0, "response is not JSON") from None
    if not isinstance(parsed, dict):
        raise ApiError(0, "response is not an object")
    return parsed
