"""Requests stay on the base URL host: no authority smuggling, no redirects."""

from __future__ import annotations

import argparse
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import api_examples as ax
import pytest

WriteDoc = Callable[[str, str], Path]


def test_path_without_leading_slash_is_not_a_parsed_example(write_doc: WriteDoc) -> None:
    doc = write_doc("d.md", "```http example=a expect=200\nGET @evil.example/x\n```\n")
    parsed = ax.parse_document(doc)
    assert parsed.examples == []
    assert [f["code"] for f in parsed.findings] == ["bad-request"]


def test_authority_smuggling_path_never_reaches_the_sender(write_doc: WriteDoc) -> None:
    doc = write_doc("d.md", "```http example=a expect=200\nGET @evil.example/x\n```\n")
    seen: list[str] = []

    def sender(method: str, url: str, headers: dict[str, str], body: bytes) -> ax.Reply:
        seen.append(url)
        return ax.Reply(200, b"{}")

    args = argparse.Namespace(
        docs=[str(doc)],
        base_url="http://127.0.0.1:9",
        allow_remote=False,
        evidence=None,
        touching=None,
    )
    with pytest.raises(ax.InputError):
        ax.cmd_run(args, sender)
    assert seen == []


@pytest.mark.parametrize("path", ["/a", "/a?x=1", "//a", "/a/b%20c"])
def test_slash_led_paths_parse(write_doc: WriteDoc, path: str) -> None:
    doc = write_doc("d.md", f"```http example=a expect=200\nGET {path}\n```\n")
    assert [e.path for e in ax.parse_document(doc).examples] == [path]


class _Target(BaseHTTPRequestHandler):
    hits: list[str] = []

    def log_message(self, *args: object) -> None:
        return

    def do_GET(self) -> None:
        type(self).hits.append(self.path)
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"{}")


def _redirector(location: str) -> type[BaseHTTPRequestHandler]:
    class Redirect(BaseHTTPRequestHandler):
        def log_message(self, *args: object) -> None:
            return

        def do_GET(self) -> None:
            self.send_response(302)
            self.send_header("Location", location)
            self.send_header("Content-Length", "0")
            self.end_headers()

    return Redirect


def _serve(handler: type[BaseHTTPRequestHandler]) -> HTTPServer:
    server = HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_redirects_are_returned_not_followed() -> None:
    _Target.hits = []
    target = _serve(_Target)
    source = _serve(_redirector(f"http://127.0.0.1:{target.server_port}/landed"))
    try:
        reply = ax.send("GET", f"http://127.0.0.1:{source.server_port}/start", {}, b"")
    finally:
        for server in (source, target):
            server.shutdown()
            server.server_close()
    assert reply.status == 302
    assert _Target.hits == []
