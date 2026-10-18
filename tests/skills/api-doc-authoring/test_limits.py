"""Proxy, size, deadline, and vacuous-lint limits of api_examples (issue #6506)."""

from __future__ import annotations

import argparse
import json
import socket
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


@contextmanager
def _serve_raw(behave: Callable[[socket.socket], None]) -> Iterator[str]:
    """Accept connections on a loopback port and hand each socket to `behave`."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(5)
    stop = threading.Event()

    def loop() -> None:
        listener.settimeout(0.1)
        while not stop.is_set():
            try:
                conn, _ = listener.accept()
            except OSError:
                continue
            threading.Thread(target=_guarded, args=(conn,), daemon=True).start()

    def _guarded(conn: socket.socket) -> None:
        with conn:
            try:
                behave(conn)
            except OSError:
                return

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{listener.getsockname()[1]}"
    finally:
        stop.set()
        thread.join(timeout=5)
        listener.close()


def _silent(conn: socket.socket) -> None:
    conn.recv(65536)
    time.sleep(3)


def _trickled_headers(conn: socket.socket) -> None:
    conn.recv(65536)
    for byte in b"HTTP/1.1 200 OK\r\nX-Slow: " + b"y" * 200:
        conn.sendall(bytes([byte]))
        time.sleep(0.05)


def _stalled_error_body(conn: socket.socket) -> None:
    conn.recv(65536)
    conn.sendall(b"HTTP/1.1 500 Err\r\nContent-Length: 100\r\n\r\nabcde")
    time.sleep(3)


def test_a_server_that_never_answers_is_cut_off_at_the_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ax, "REQUEST_DEADLINE_SECONDS", 0.4)
    started = time.monotonic()
    with _serve_raw(_silent) as base, pytest.raises(ax.InputError, match="slower than"):
        ax.send("GET", f"{base}/x", {}, b"")

    assert time.monotonic() - started < 2.5


def test_headers_trickled_inside_the_socket_timeout_are_cut_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The header phase has no body to count, so only the wall-clock deadline ends it."""
    monkeypatch.setattr(ax, "REQUEST_DEADLINE_SECONDS", 0.4)
    started = time.monotonic()
    with _serve_raw(_trickled_headers) as base, pytest.raises(ax.InputError, match="slower than"):
        ax.send("GET", f"{base}/x", {}, b"")

    assert time.monotonic() - started < 2.5


def test_a_socket_timeout_while_reading_an_error_body_is_unverifiable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The timeout surfaces inside the HTTPError handler. It must exit 2, not raise."""
    monkeypatch.setattr(ax, "TIMEOUT_SECONDS", 0.3)
    with _serve_raw(_stalled_error_body) as base, pytest.raises(ax.InputError, match="unreachable"):
        ax.send("GET", f"{base}/x", {}, b"")


def test_an_error_inside_the_worker_thread_reaches_the_caller() -> None:
    def boom() -> ax.Reply:
        raise ax.InputError("boom")

    with pytest.raises(ax.InputError, match="boom"):
        ax._within_deadline(boom, "http://x/")


def test_a_worker_result_inside_the_deadline_is_returned() -> None:
    assert ax._within_deadline(lambda: ax.Reply(204, b""), "http://x/") == ax.Reply(204, b"")


def test_a_trickling_server_is_cut_off_near_the_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A real socket: one byte per 0.1 s never trips the socket timeout, only the deadline."""
    monkeypatch.setattr(ax, "REQUEST_DEADLINE_SECONDS", 0.5)
    started = time.monotonic()
    with _serve_trickle(total=100, pause=0.1) as base, pytest.raises(ax.InputError, match="slower"):
        ax.send("GET", f"{base}/x", {}, b"")

    assert time.monotonic() - started < 5.0


def test_a_slow_body_that_finishes_inside_the_deadline_is_read_in_full() -> None:
    with _serve_trickle(total=5, pause=0.01) as base:
        assert ax.send("GET", f"{base}/x", {}, b"").body == b"xxxxx"


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
    with pytest.raises(ax.InputError, match=r"deadline after 0 of 2 examples, before `a`"):
        ax.cmd_run(args, sender)
    assert sent == []


def _run_that_passes_its_deadline_after_one_example(
    write_doc: WriteDoc, monkeypatch: pytest.MonkeyPatch, status: int, evidence: Path
) -> tuple[argparse.Namespace, Callable[..., ax.Reply]]:
    text = GOOD_DOC + "\n```http example=b expect=200\nGET /y\n```\n"
    doc = write_doc("d.md", text)
    real_monotonic = time.monotonic

    def sender(method: str, url: str, headers: dict[str, str], body: bytes) -> ax.Reply:
        # The first example finishes, then the clock jumps past the run deadline.
        monkeypatch.setattr(ax.time, "monotonic", lambda: real_monotonic() + 10_000)
        return ax.Reply(status, b"{}")

    args = argparse.Namespace(
        docs=[str(doc)],
        base_url="http://127.0.0.1:9",
        allow_remote=False,
        evidence=str(evidence),
        touching=None,
    )
    return args, sender


def test_a_failed_example_before_the_deadline_is_still_a_finding(
    write_doc: WriteDoc, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    evidence = tmp_path / "evidence.json"
    args, sender = _run_that_passes_its_deadline_after_one_example(
        write_doc, monkeypatch, 500, evidence
    )

    report, code = ax.cmd_run(args, sender)

    assert code == ax.EXIT_FINDINGS
    assert report["verdict"] == "FAIL" and report["executed"] == 1 and report["failed"] == 1
    assert report["deadline_exceeded"]["unrun"] == ["b"]
    assert json.loads(evidence.read_text(encoding="utf-8")) == report


def test_a_clean_partial_run_past_the_deadline_keeps_its_evidence_and_is_unverified(
    write_doc: WriteDoc, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    evidence = tmp_path / "evidence.json"
    args, sender = _run_that_passes_its_deadline_after_one_example(
        write_doc, monkeypatch, 200, evidence
    )

    with pytest.raises(ax.InputError, match=r"after 1 of 2 examples, before `b`.*not a verdict"):
        ax.cmd_run(args, sender)

    saved = json.loads(evidence.read_text(encoding="utf-8"))
    assert saved["verdict"] == "UNVERIFIED" and saved["executed"] == 1
    assert saved["deadline_exceeded"]["unrun"] == ["b"]


def test_lint_findings_are_kept_when_the_run_passes_its_deadline(
    write_doc: WriteDoc, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A lint-dirty doc is a finding (exit 1) even when the deadline cut the run short."""
    evidence = tmp_path / "evidence.json"
    args, sender = _run_that_passes_its_deadline_after_one_example(
        write_doc, monkeypatch, 200, evidence
    )
    bad = write_doc("bad.md", "```http example=c\nGET /z\n```\n")
    args.docs.append(str(bad))

    report, code = ax.cmd_run(args, sender)

    assert code == ax.EXIT_FINDINGS and report["verdict"] == "FAIL"
    assert report["lint_findings"]
    assert json.loads(evidence.read_text(encoding="utf-8"))["lint_findings"]


def test_main_maps_a_deadline_to_the_documented_exit_codes(
    write_doc: WriteDoc,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Assert the process exit code, not the helper's return: 1 with a FAIL, 2 without."""
    for status, expected in ((500, ax.EXIT_FINDINGS), (200, ax.EXIT_UNVERIFIABLE)):
        args, sender = _run_that_passes_its_deadline_after_one_example(
            write_doc, monkeypatch, status, tmp_path / f"e{status}.json"
        )
        monkeypatch.setitem(ax._COMMANDS, "run", lambda parsed, s=sender: ax.cmd_run(parsed, s))
        argv = ["run", *args.docs, "--base-url", args.base_url, "--evidence", args.evidence]
        assert ax.main(argv) == expected
        out = json.loads(capsys.readouterr().out)
        assert out["verdict"] in {"FAIL", "UNVERIFIED"}


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
