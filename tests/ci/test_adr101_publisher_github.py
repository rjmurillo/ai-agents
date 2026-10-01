"""Tests for scripts/ci/adr101_publisher_github.py.

The opener is replaced with a recording fake, so no request leaves the process.
What these pin: one fixed host, the right token on the right call, a redirect
that raises instead of replaying a token, and errors that carry no body.
"""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
from email.message import Message
from typing import Any

import pytest

from scripts.ci import adr101_publisher_github as gh
from scripts.ci.adr101_publisher_inputs import CHECK_NAME

READ_TOKEN = "ghs_read_secret"
APP_TOKEN = "ghs_app_secret"
HEAD = "a" * 40
BASE = "b" * 40


class FakeOpener:
    def __init__(self, result: bytes | Exception) -> None:
        self.result = result
        self.requests: list[urllib.request.Request] = []
        self.timeouts: list[float] = []

    def open(
        self,
        fullurl: urllib.request.Request,
        data: None = None,
        timeout: float | None = None,
    ) -> io.BytesIO:
        self.requests.append(fullurl)
        self.timeouts.append(0.0 if timeout is None else timeout)
        if isinstance(self.result, Exception):
            raise self.result
        return io.BytesIO(self.result)


def client(result: bytes | Exception) -> tuple[gh.GitHubApi, FakeOpener]:
    opener = FakeOpener(result)
    return gh.GitHubApi("rjmurillo/ai-agents", READ_TOKEN, APP_TOKEN, opener), opener


def sent_json(request: urllib.request.Request) -> Any:
    assert isinstance(request.data, bytes)
    return json.loads(request.data)


def body(payload: Any) -> bytes:
    return json.dumps(payload).encode("utf-8")


class TestReads:
    def test_get_pull_uses_the_read_token_and_the_fixed_host(self) -> None:
        api, opener = client(body({"head": {"sha": HEAD}, "base": {"sha": BASE}}))

        pull = api.get_pull("42")

        request = opener.requests[0]
        assert request.full_url == "https://api.github.com/repos/rjmurillo/ai-agents/pulls/42"
        assert request.get_header("Authorization") == f"Bearer {READ_TOKEN}"
        assert request.get_method() == "GET"
        assert (pull.head_sha, pull.base_sha) == (HEAD, BASE)

    def test_get_run_reads_head_sha_and_status(self) -> None:
        api, opener = client(body({"head_sha": HEAD, "status": "completed"}))

        run = api.get_run("9001")

        assert opener.requests[0].full_url.endswith("/actions/runs/9001")
        assert (run.head_sha, run.status) == (HEAD, "completed")

    @pytest.mark.parametrize("number", ["", "4;id", "../x", "4 2", "-1"])
    def test_a_non_numeric_pull_number_never_reaches_a_url(self, number: str) -> None:
        api, opener = client(b"{}")

        with pytest.raises(ValueError):
            api.get_pull(number)

        assert opener.requests == []

    @pytest.mark.parametrize("run_id", ["", "x", "1/2"])
    def test_a_non_numeric_run_id_never_reaches_a_url(self, run_id: str) -> None:
        api, opener = client(b"{}")

        with pytest.raises(ValueError):
            api.get_run(run_id)

        assert opener.requests == []

    @pytest.mark.parametrize("repository", ["", "a", "../b", "a/../b", "a/b/c", "a b/c"])
    def test_a_bad_repository_is_refused_at_construction(self, repository: str) -> None:
        with pytest.raises(ValueError):
            gh.GitHubApi(repository, READ_TOKEN, APP_TOKEN)


class TestWrites:
    def test_create_check_run_uses_the_app_token_and_the_pinned_name(self) -> None:
        api, opener = client(body({"id": 777}))

        check_id = api.create_check_run(HEAD, "success", "digest", "title", "summary")

        request = opener.requests[0]
        sent = sent_json(request)
        assert check_id == 777
        assert request.get_header("Authorization") == f"Bearer {APP_TOKEN}"
        assert request.get_method() == "POST"
        assert request.full_url.endswith("/check-runs")
        assert sent["name"] == CHECK_NAME
        assert sent["head_sha"] == HEAD
        assert sent["status"] == "completed"
        assert sent["conclusion"] == "success"
        assert sent["external_id"] == "digest"
        assert request.get_header("Content-type") == "application/json"

    def test_create_check_run_truncates_long_text(self) -> None:
        api, opener = client(body({"id": 1}))

        api.create_check_run(HEAD, "failure", "d", "t" * 5000, "s" * 5000)

        sent = sent_json(opener.requests[0])
        assert len(sent["output"]["title"]) == 500
        assert len(sent["output"]["summary"]) == 500

    def test_get_check_run_returns_the_authoring_app_id(self) -> None:
        payload = {
            "name": CHECK_NAME,
            "head_sha": HEAD,
            "conclusion": "success",
            "external_id": "d",
            "app": {"id": 123456},
        }
        api, opener = client(body(payload))

        seen = api.get_check_run(777)

        assert opener.requests[0].get_header("Authorization") == f"Bearer {APP_TOKEN}"
        assert seen.app_id == "123456"
        assert seen.name == CHECK_NAME
        assert seen.external_id == "d"

    def test_set_conclusion_patches_through_the_app_token(self) -> None:
        api, opener = client(body({"id": 777}))

        api.set_conclusion(777, "failure", "retracted")

        request = opener.requests[0]
        assert request.get_method() == "PATCH"
        assert request.full_url.endswith("/check-runs/777")
        assert sent_json(request)["conclusion"] == "failure"


class TestFailures:
    def test_an_http_error_carries_the_status_and_no_body(self) -> None:
        error = urllib.error.HTTPError(
            "https://api.github.com/x", 403, "Forbidden", Message(), io.BytesIO(b"secret body")
        )
        api, _ = client(error)

        with pytest.raises(gh.ApiError) as caught:
            api.get_pull("42")

        assert caught.value.status == 403
        assert "secret body" not in str(caught.value)
        assert READ_TOKEN not in str(caught.value)

    @pytest.mark.parametrize("exc", [urllib.error.URLError("dns"), TimeoutError(), OSError("x")])
    def test_a_transport_failure_is_status_zero(self, exc: Exception) -> None:
        api, _ = client(exc)

        with pytest.raises(gh.ApiError) as caught:
            api.get_pull("42")

        assert caught.value.status == 0

    @pytest.mark.parametrize(
        "raw",
        [b"not json", b"\xff\xfe", b"[1, 2]", b'"text"', b"null", b"x" * (1024 * 1024 + 5)],
    )
    def test_a_response_that_is_not_a_json_object_is_refused(self, raw: bytes) -> None:
        api, _ = client(raw)

        with pytest.raises(gh.ApiError):
            api.get_pull("42")

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {"head": {"sha": HEAD}},
            {"head": {"sha": None}, "base": {"sha": BASE}},
            {"head": {"sha": 5}, "base": {"sha": BASE}},
            {"head": "x", "base": {"sha": BASE}},
        ],
    )
    def test_a_missing_or_mistyped_field_is_refused(self, payload: dict[str, Any]) -> None:
        api, _ = client(body(payload))

        with pytest.raises(gh.ApiError):
            api.get_pull("42")

    @pytest.mark.parametrize("bad_id", [True, "7", 1.5, None])
    def test_a_check_run_id_that_is_not_an_integer_is_refused(self, bad_id: Any) -> None:
        api, _ = client(body({"id": bad_id}))

        with pytest.raises(gh.ApiError):
            api.create_check_run(HEAD, "success", "d", "t", "s")

    def test_a_non_integer_app_id_is_refused(self) -> None:
        payload = {
            "name": "n",
            "head_sha": HEAD,
            "conclusion": "success",
            "external_id": "d",
            "app": {"id": "123"},
        }
        api, _ = client(body(payload))

        with pytest.raises(gh.ApiError):
            api.get_check_run(1)

    def test_a_redirect_raises_so_a_token_never_leaves_the_host(self) -> None:
        handler = gh._NoRedirect()
        request = urllib.request.Request("https://api.github.com/x")

        with pytest.raises(gh.ApiError) as caught:
            handler.redirect_request(
                request, io.BytesIO(b""), 301, "Moved", Message(), "https://evil.example/x"
            )

        assert caught.value.status == 301

    def test_the_timeout_is_bounded(self) -> None:
        api, opener = client(body({"head": {"sha": HEAD}, "base": {"sha": BASE}}))

        api.get_pull("42")

        assert opener.timeouts == [gh.TIMEOUT_SECONDS]

    def test_the_real_opener_has_the_redirect_guard(self) -> None:
        handlers = [type(h) for h in vars(gh._opener())["handlers"]]

        assert gh._NoRedirect in handlers
