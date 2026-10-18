"""Proxy, size, deadline, and vacuous-lint limits of api_examples (issue #6506)."""

from __future__ import annotations

import argparse
import threading
import time
import urllib.request
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import api_examples as ax
import pytest

WriteDoc = Callable[[str, str], Path]
GOOD_DOC = "```http example=a expect=200\nGET /x\n```\n"


def _handler(status: int, body: bytes) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:
            return

        def do_GET(self) -> None:
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


@contextmanager
def _serve(status: int, body: bytes) -> Iterator[str]:
    server = HTTPServer(("127.0.0.1", 0), _handler(status, body))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


class _FakeOpener:
    def __init__(self) -> None:
        self.used = 0

    def open(self, request: Any, timeout: float) -> Any:
        self.used += 1
        raise OSError("fake opener reached")


# Proxies --------------------------------------------------------------------


@pytest.mark.parametrize(
    "url", ["http://127.0.0.1:8080/x", "http://localhost/x", "http://[::1]:9/x"]
)
def test_loopback_urls_use_the_opener_with_no_proxy(url: str) -> None:
    assert ax._opener_for(url) is ax._DIRECT_OPENER


@pytest.mark.parametrize("url", ["https://api.example.test/x", "http://203.0.113.9/x", "http:///x"])
def test_other_urls_keep_the_default_opener(url: str) -> None:
    assert ax._opener_for(url) is ax._OPENER


def test_the_direct_opener_has_no_proxy_handler_even_with_proxy_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty ProxyHandler registers nothing, and it stops build_opener adding the default."""
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:9")

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    for candidate in (opener, ax._DIRECT_OPENER):
        handlers = getattr(candidate, "handlers", None)
        assert isinstance(handlers, list) and handlers
        assert not [h for h in handlers if isinstance(h, urllib.request.ProxyHandler)]


def test_a_loopback_request_ignores_a_configured_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    """The default opener now points at a dead proxy. The loopback request must not use it."""
    dead_proxy = {"http": "http://127.0.0.1:9"}
    monkeypatch.setattr(
        ax, "_OPENER", urllib.request.build_opener(urllib.request.ProxyHandler(dead_proxy))
    )
    with _serve(200, b"{}") as base:
        reply = ax.send("GET", f"{base}/x", {}, b"")

    assert reply.status == 200


def test_a_remote_request_still_goes_through_the_default_opener(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeOpener()
    monkeypatch.setattr(ax, "_OPENER", fake)

    with pytest.raises(ax.InputError, match="unreachable"):
        ax.send("GET", "https://api.example.test/x", {}, b"")

    assert fake.used == 1


# Size cap -------------------------------------------------------------------


def test_a_body_at_the_cap_is_read_in_full(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ax, "MAX_BODY_BYTES", 100)
    with _serve(200, b"x" * 100) as base:
        reply = ax.send("GET", f"{base}/x", {}, b"")

    assert reply.status == 200 and len(reply.body) == 100


def test_a_body_over_the_cap_is_unverifiable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ax, "MAX_BODY_BYTES", 100)
    with _serve(200, b"x" * 101) as base, pytest.raises(ax.InputError, match="byte cap"):
        ax.send("GET", f"{base}/x", {}, b"")


def test_an_error_status_body_over_the_cap_is_also_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ax, "MAX_BODY_BYTES", 100)
    with _serve(500, b"y" * 5000) as base, pytest.raises(ax.InputError, match="byte cap"):
        ax.send("GET", f"{base}/x", {}, b"")


def test_a_body_spanning_several_chunks_is_joined_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ax, "_CHUNK_BYTES", 7)
    payload = bytes(range(65, 91)) * 3
    with _serve(200, payload) as base:
        assert ax.send("GET", f"{base}/x", {}, b"").body == payload


def test_an_empty_body_is_an_empty_reply() -> None:
    with _serve(204, b"") as base:
        assert ax.send("GET", f"{base}/x", {}, b"") == ax.Reply(204, b"")


def test_the_cap_ends_the_run_with_exit_two(
    write_doc: WriteDoc, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(ax, "MAX_BODY_BYTES", 10)
    doc = write_doc("d.md", GOOD_DOC)
    with _serve(200, b"z" * 50) as base:
        code = ax.main(["run", str(doc), "--base-url", base])

    assert code == ax.EXIT_UNVERIFIABLE
    assert "UNVERIFIED" in capsys.readouterr().out


# Deadlines ------------------------------------------------------------------


class _Handle:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = list(chunks)

    def read(self, size: int) -> bytes:
        return self._chunks.pop(0) if self._chunks else b""


def test_a_slow_body_is_refused_after_the_request_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = iter([0.0, 1.0, 1000.0, 2000.0])
    monkeypatch.setattr(ax.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(ax, "REQUEST_DEADLINE_SECONDS", 30)

    with pytest.raises(ax.InputError, match="slower than 30s"):
        ax._read_capped(_Handle([b"a", b"b", b"c", b"d"]), "http://x/")


@contextmanager
def _serve_trickle(total: int, pause: float) -> Iterator[str]:
    """Serve `total` bytes one at a time, `pause` seconds apart, under a Content-Length."""

    class Trickle(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:
            return

        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Length", str(total))
            self.end_headers()
            try:
                for _ in range(total):
                    self.wfile.write(b"x")
                    self.wfile.flush()
                    time.sleep(pause)
            except OSError:
                return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Trickle)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_a_trickling_server_is_cut_off_near_the_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A real socket: one byte per 0.1 s never trips the socket timeout, only the deadline."""
    monkeypatch.setattr(ax, "REQUEST_DEADLINE_SECONDS", 0.5)
    started = time.monotonic()
    with _serve_trickle(total=100, pause=0.1) as base, pytest.raises(ax.InputError, match="slower"):
        ax.send("GET", f"{base}/x", {}, b"")

    assert time.monotonic() - started < 3.0


def test_a_slow_body_that_finishes_inside_the_deadline_is_read_in_full() -> None:
    with _serve_trickle(total=5, pause=0.01) as base:
        assert ax.send("GET", f"{base}/x", {}, b"").body == b"xxxxx"


def test_a_fast_body_finishes_inside_the_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = iter([0.0, 1.0, 2.0, 3.0])
    monkeypatch.setattr(ax.time, "monotonic", lambda: next(clock))

    assert ax._read_capped(_Handle([b"a", b"b"]), "http://x/") == b"ab"


def test_a_run_past_its_deadline_is_unverifiable(
    write_doc: WriteDoc, monkeypatch: pytest.MonkeyPatch
) -> None:
    text = GOOD_DOC + "\n```http example=b expect=200\nGET /y\n```\n"
    doc = write_doc("d.md", text)
    monkeypatch.setattr(ax, "RUN_DEADLINE_SECONDS", -1)
    sent: list[str] = []

    def sender(method: str, url: str, headers: dict[str, str], body: bytes) -> ax.Reply:
        sent.append(url)
        return ax.Reply(200, b"{}")

    args = argparse.Namespace(
        docs=[str(doc)],
        base_url="http://127.0.0.1:9",
        allow_remote=False,
        evidence=None,
        touching=None,
    )
    with pytest.raises(ax.InputError, match="deadline after 0 of 2 examples"):
        ax.cmd_run(args, sender)
    assert sent == []


def test_a_run_inside_its_deadline_sends_every_example(write_doc: WriteDoc) -> None:
    doc = write_doc("d.md", GOOD_DOC)
    sent: list[str] = []

    def sender(method: str, url: str, headers: dict[str, str], body: bytes) -> ax.Reply:
        sent.append(url)
        return ax.Reply(200, b"{}")

    args = argparse.Namespace(
        docs=[str(doc)],
        base_url="http://127.0.0.1:9",
        allow_remote=False,
        evidence=None,
        touching=None,
    )
    report, code = ax.cmd_run(args, sender)

    assert code == ax.EXIT_OK and report["executed"] == 1 and len(sent) == 1


# Vacuous lint ---------------------------------------------------------------


def test_lint_of_a_document_with_no_examples_is_unverifiable(
    write_doc: WriteDoc, capsys: pytest.CaptureFixture[str]
) -> None:
    doc = write_doc("d.md", "# Title\n\nJust prose.\n")

    code = ax.main(["lint", str(doc)])

    assert code == ax.EXIT_UNVERIFIABLE
    out = capsys.readouterr().out
    assert "UNVERIFIED" in out and "no examples" in out


def test_lint_of_an_empty_file_is_unverifiable(write_doc: WriteDoc) -> None:
    assert ax.main(["lint", str(write_doc("d.md", ""))]) == ax.EXIT_UNVERIFIABLE


def test_lint_of_several_documents_with_no_examples_is_unverifiable(write_doc: WriteDoc) -> None:
    docs = [str(write_doc(f"{n}.md", "prose\n")) for n in ("a", "b")]

    assert ax.main(["lint", *docs]) == ax.EXIT_UNVERIFIABLE


def test_lint_with_findings_but_no_parsed_example_still_reports_the_findings(
    write_doc: WriteDoc,
) -> None:
    """A broken request is a finding, not a vacuous pass: exit 1, not 2."""
    doc = write_doc("d.md", "```http example=a expect=200\nGET @evil.example/x\n```\n")

    assert ax.main(["lint", str(doc)]) == ax.EXIT_FINDINGS


def test_lint_passes_when_one_document_holds_an_example(write_doc: WriteDoc) -> None:
    docs = [write_doc("empty.md", "prose\n"), write_doc("good.md", GOOD_DOC)]

    assert ax.main(["lint", *(str(d) for d in docs)]) == ax.EXIT_OK
