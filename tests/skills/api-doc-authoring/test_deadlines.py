"""Request and run deadlines of api_examples (issue #6506)."""

from __future__ import annotations

import argparse
import json
import socket
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import api_examples as ax
import pytest

WriteDoc = Callable[[str, str], Path]
GOOD_DOC = "```http example=a expect=200\nGET /x\n```\n"


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


def _cut_short(status: bytes) -> Callable[[socket.socket], None]:
    """Promise 100 body bytes, send 5, then close: a truncated reply."""

    def behave(conn: socket.socket) -> None:
        conn.recv(65536)
        conn.sendall(b"HTTP/1.1 " + status + b"\r\nContent-Length: 100\r\n\r\nabcde")

    return behave


@pytest.mark.parametrize("status", [b"200 OK", b"500 Err"])
def test_a_body_cut_short_of_its_content_length_is_unverifiable(status: bytes) -> None:
    """A reply that ends early must not read as a complete reply, for any status."""
    with _serve_raw(_cut_short(status)) as base, pytest.raises(ax.InputError, match="cut off"):
        ax.send("GET", f"{base}/x", {}, b"")


def test_a_body_that_matches_its_content_length_is_read_in_full() -> None:
    """Negative control: the check does not refuse a complete reply."""

    def complete(conn: socket.socket) -> None:
        conn.recv(65536)
        conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 5\r\n\r\nabcde")

    with _serve_raw(complete) as base:
        reply = ax.send("GET", f"{base}/x", {}, b"")

    assert (reply.status, reply.body) == (200, b"abcde")


def test_a_reply_with_no_content_length_is_not_refused() -> None:
    """Edge: a close-delimited body has no promised length to compare."""

    def close_delimited(conn: socket.socket) -> None:
        conn.recv(65536)
        conn.sendall(b"HTTP/1.0 200 OK\r\n\r\nabcde")

    with _serve_raw(close_delimited) as base:
        reply = ax.send("GET", f"{base}/x", {}, b"")

    assert reply.body == b"abcde"


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


@pytest.mark.parametrize(
    ("status", "exit_code", "verdict"),
    [(500, 1, "FAIL"), (200, 2, "UNVERIFIED")],
)
def test_main_maps_a_deadline_to_the_documented_exit_codes(
    write_doc: WriteDoc,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    status: int,
    exit_code: int,
    verdict: str,
) -> None:
    """Assert the process exit code, not the helper's return: 1 with a FAIL, 2 without."""
    args, sender = _run_that_passes_its_deadline_after_one_example(
        write_doc, monkeypatch, status, tmp_path / "evidence.json"
    )
    monkeypatch.setitem(ax._COMMANDS, "run", lambda parsed: ax.cmd_run(parsed, sender))
    argv = ["run", *args.docs, "--base-url", args.base_url, "--evidence", args.evidence]

    assert ax.main(argv) == exit_code
    assert json.loads(capsys.readouterr().out)["verdict"] == verdict


def _run_args(doc: Path, evidence: Path | None) -> argparse.Namespace:
    return argparse.Namespace(
        docs=[str(doc)],
        base_url="http://127.0.0.1:9",
        allow_remote=False,
        evidence=None if evidence is None else str(evidence),
        touching=None,
    )


def _fail_then_stall(slow: Callable[[], ax.Reply]) -> Callable[..., ax.Reply]:
    """Answer the first example with a 500 (a FAIL), then run ``slow`` for the second."""
    calls: list[str] = []

    def sender(method: str, url: str, headers: dict[str, str], body: bytes) -> ax.Reply:
        calls.append(url)
        return ax.Reply(500, b"{}") if len(calls) == 1 else slow()

    return sender


def _stall_with(message: str) -> Callable[[], ax.Reply]:
    def slow() -> ax.Reply:
        raise ax.InputError(message)

    return slow


@pytest.mark.parametrize(
    "message",
    [
        "response from http://x/y is slower than 30s",
        "response from http://x/y is over the 10 byte cap",
        "server unreachable at http://x/y: refused",
    ],
)
def test_a_failed_example_survives_a_later_request_that_cannot_finish(
    write_doc: WriteDoc, tmp_path: Path, message: str
) -> None:
    """A FAIL then a slow, oversized or unreachable example stays exit 1 with evidence."""
    text = GOOD_DOC + "\n```http example=b expect=200\nGET /y\n```\n"
    evidence = tmp_path / "evidence.json"
    args = _run_args(write_doc("d.md", text), evidence)

    report, code = ax.cmd_run(args, _fail_then_stall(_stall_with(message)))

    assert code == ax.EXIT_FINDINGS
    assert report["verdict"] == "FAIL" and report["executed"] == 1 and report["failed"] == 1
    assert report["request_failed"] == {"example": "b", "error": message, "unrun": []}
    assert json.loads(evidence.read_text(encoding="utf-8")) == report


def test_a_request_that_cannot_finish_first_is_unverified_and_keeps_evidence(
    write_doc: WriteDoc, tmp_path: Path
) -> None:
    text = GOOD_DOC + "\n```http example=b expect=200\nGET /y\n```\n"
    evidence = tmp_path / "evidence.json"
    args = _run_args(write_doc("d.md", text), evidence)

    with pytest.raises(ax.InputError, match=r"example `a` could not finish after 0 of 2.*slow"):
        ax.cmd_run(args, lambda *_: _stall_with("slow")())

    saved = json.loads(evidence.read_text(encoding="utf-8"))
    assert saved["verdict"] == "UNVERIFIED" and saved["executed"] == 0
    assert saved["request_failed"]["example"] == "a"
    assert saved["request_failed"]["unrun"] == ["b"]


def test_a_request_that_cannot_finish_keeps_lint_findings_as_a_finding(
    write_doc: WriteDoc, tmp_path: Path
) -> None:
    doc = write_doc("d.md", GOOD_DOC + "\n```http example=c\nGET /z\n```\n")
    args = _run_args(doc, tmp_path / "evidence.json")

    report, code = ax.cmd_run(args, lambda *_: _stall_with("slow")())

    assert code == ax.EXIT_FINDINGS and report["verdict"] == "FAIL"
    assert report["lint_findings"] and report["executed"] == 0


def test_main_exits_one_for_a_fail_then_a_stalled_request(
    write_doc: WriteDoc,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    text = GOOD_DOC + "\n```http example=b expect=200\nGET /y\n```\n"
    args = _run_args(write_doc("d.md", text), tmp_path / "evidence.json")
    sender = _fail_then_stall(_stall_with("response from http://x/y is slower than 30s"))
    monkeypatch.setitem(ax._COMMANDS, "run", lambda parsed: ax.cmd_run(parsed, sender))
    argv = ["run", *args.docs, "--base-url", args.base_url, "--evidence", args.evidence]

    assert ax.main(argv) == ax.EXIT_FINDINGS
    assert json.loads(capsys.readouterr().out)["verdict"] == "FAIL"


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
