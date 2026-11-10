"""Tests for code_scanning_transport.py: GET-only gh calls and fail-loud paging."""

from __future__ import annotations

import subprocess
from unittest.mock import patch

import code_scanning_transport as transport_mod
import pytest
from test_helpers import make_completed_process

SkipError = transport_mod.SkipError


class TestNextLink:
    ANALYSES = "repos/o/r/code-scanning/analyses?ref=refs/pull/7/merge&per_page=100"
    ALERTS = "repos/o/r/code-scanning/alerts?state=open&per_page=100"

    def _follow(self, url, endpoint=None):
        link = f'<{url}>; rel="next"'
        return transport_mod._next_endpoint(link, endpoint or self.ANALYSES)

    def test_the_real_link_shape_names_the_repository_id_and_is_followed(self):
        url = "https://api.github.com/repositories/1116049814/code-scanning/analyses?per_page=100&page=2"
        assert self._follow(url) == (
            "repositories/1116049814/code-scanning/analyses?per_page=100&page=2"
        )

    def test_the_requested_repos_path_is_followed(self):
        url = "https://api.github.com/repos/o/r/code-scanning/alerts?state=open&after=abc"
        assert (
            self._follow(url, self.ALERTS) == "repos/o/r/code-scanning/alerts?state=open&after=abc"
        )

    def test_the_enterprise_shape_needs_gh_host_and_drops_the_api_prefix(self, monkeypatch):
        monkeypatch.setenv("GH_HOST", "ghe.example")
        url = "https://ghe.example/api/v3/repositories/9/code-scanning/analyses?page=2"
        assert self._follow(url) == "repositories/9/code-scanning/analyses?page=2"

    def test_the_api_v3_prefix_on_the_api_host_is_accepted(self):
        url = "https://api.github.com/api/v3/repos/o/r/code-scanning/analyses?page=2"
        assert self._follow(url) == "repos/o/r/code-scanning/analyses?page=2"

    @pytest.mark.parametrize(
        "url",
        [
            "https://evil.example/repositories/9/code-scanning/analyses?page=2",
            "https://ghe.example/api/v3/repositories/9/code-scanning/analyses?page=2",
            "http://api.github.com/repositories/9/code-scanning/analyses?page=2",
            "https://api.github.com.evil.example/repositories/9/code-scanning/analyses?page=2",
            "https://api.github.com/repos/x/y/actions/secrets?page=2",
            "https://api.github.com/repos/o/r/code-scanning/alerts?page=2",
            "https://api.github.com/repositories/9/code-scanning/alerts?page=2",
            "https://api.github.com/repos/o/r/code-scanning/../actions/secrets?page=2",
            "https://api.github.com/repositories/9/../../x/code-scanning/analyses?page=2",
            "https://api.github.com/repositories/abc/code-scanning/analyses?page=2",
            "https://api.github.com/-repos/o/r/code-scanning/analyses?page=2",
            "https://api.github.com/repositories/9/code-scanning/analyses",
            "https://api.github.com/repositories/9/code-scanning/analyses?page=2&token=x",
            "https://api.github.com/repositories/9/code-scanning/analyses?--input=x",
            "https://api.github.com/repositories/9/code-scanning/analyses?state=open",
        ],
    )
    def test_a_link_that_is_not_the_same_list_one_page_on_is_refused(self, url):
        with pytest.raises(SkipError, match="unusable next link"):
            self._follow(url)

    def test_a_next_link_cannot_produce_an_endpoint_that_starts_with_a_dash(self):
        url = "https://api.github.com/-x?page=2"
        with pytest.raises(SkipError, match="unusable next link"):
            self._follow(url)

    @pytest.mark.parametrize("link", [None, "", '<https://x/y?page=1>; rel="prev"'])
    def test_no_next_relation_means_the_last_page(self, link):
        assert transport_mod._next_endpoint(link, self.ANALYSES) is None


class TestTransport:
    def _run(self, **kwargs):
        defaults = {"stdout": "HTTP/2.0 200 OK\r\nLink: <x>\r\n\r\n[]", "returncode": 0}
        defaults.update(kwargs)
        return make_completed_process(**defaults)

    def test_issues_a_get_only_gh_api_call(self):
        with patch.object(transport_mod.subprocess, "run", return_value=self._run()) as run:
            transport_mod.gh_get("repos/o/r/code-scanning/alerts")
        command = run.call_args.args[0]
        assert command[:5] == ["gh", "api", "--include", "--method", "GET"]
        for flag in (
            "-X",
            "--input",
            "-f",
            "-F",
            "--field",
            "--raw-field",
            "POST",
            "PATCH",
            "DELETE",
        ):
            assert flag not in command

    def test_the_endpoint_follows_a_double_dash_so_it_cannot_be_read_as_a_flag(self):
        with patch.object(transport_mod.subprocess, "run", return_value=self._run()) as run:
            transport_mod.gh_get("repos/o/r/code-scanning/alerts")
        command = run.call_args.args[0]
        assert command[-2:] == ["--", "repos/o/r/code-scanning/alerts"]

    def test_sends_the_accept_header_when_asked(self):
        with patch.object(transport_mod.subprocess, "run", return_value=self._run()) as run:
            transport_mod.gh_get("repos/o/r/code-scanning/analyses/1", "application/sarif+json")
        command = run.call_args.args[0]
        assert command[command.index("-H") + 1] == "Accept: application/sarif+json"
        assert command[-1] == "repos/o/r/code-scanning/analyses/1"

    def test_splits_headers_from_the_body_and_lowercases_names(self):
        stdout = 'HTTP/2.0 200 OK\nLink: <u>; rel="next"\nX-Thing: 1\n\n[1]'
        with patch.object(transport_mod.subprocess, "run", return_value=self._run(stdout=stdout)):
            headers, body = transport_mod.gh_get("e")
        assert headers["link"] == '<u>; rel="next"'
        assert body == "[1]"

    def test_a_response_without_a_header_block_is_skipped(self):
        with patch.object(transport_mod.subprocess, "run", return_value=self._run(stdout="[]")):
            with pytest.raises(SkipError, match="no header block"):
                transport_mod.gh_get("e")

    @pytest.mark.parametrize(
        ("stderr", "code", "fragment"),
        [
            ("gh: Forbidden (HTTP 403)", 4, "authorization or not-found error (HTTP 403)"),
            ("gh: Not Found (HTTP 404)", 4, "(HTTP 404)"),
            ("gh: Unauthorized (HTTP 401)", 4, "(HTTP 401)"),
            ("gh: Server Error (HTTP 502)", 3, "request failed (HTTP 502)"),
            ("API rate limit exceeded (HTTP 403)", 3, "rate limit"),
            ("connection reset", 3, "request failed"),
        ],
    )
    def test_failures_become_fixed_reasons_with_adr_035_codes(self, stderr, code, fragment):
        with patch.object(
            transport_mod.subprocess, "run", return_value=self._run(stderr=stderr, returncode=1)
        ):
            with pytest.raises(SkipError) as caught:
                transport_mod.gh_get("e")
        assert caught.value.exit_code == code
        assert fragment in caught.value.reason
        for remote_word in ("Forbidden", "Not Found", "Unauthorized", "Server Error", "reset"):
            assert remote_word not in caught.value.reason

    def test_a_timeout_is_skipped(self):
        with patch.object(
            transport_mod.subprocess, "run", side_effect=subprocess.TimeoutExpired("gh", 30)
        ):
            with pytest.raises(SkipError, match="timed out"):
                transport_mod.gh_get("e")

    def test_a_missing_gh_binary_is_an_auth_class_skip(self):
        with patch.object(transport_mod.subprocess, "run", side_effect=FileNotFoundError("gh")):
            with pytest.raises(SkipError) as caught:
                transport_mod.gh_get("e")
        assert caught.value.exit_code == 4
