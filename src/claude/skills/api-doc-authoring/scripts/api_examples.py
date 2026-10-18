#!/usr/bin/env python3
"""Run the executable HTTP examples in API documentation and record evidence.

The documentation is the thing under test. An executable example is a fenced
``http`` block whose info string carries an id and the expected status, with an
optional ``json`` block that documents the response::

    ```http example=create-order expect=201
    POST /orders
    Content-Type: application/json

    {"sku": "A-1", "qty": 2}
    ```

    ```json response=create-order
    {"id": "<id>", "status": "pending"}
    ```

Subcommands (stdlib only, output is one JSON object):

``list``  Examples found, optionally filtered to a request path prefix.
``lint``  Structure findings: bad fences, unverified responses, error tables
          with a missing cause or action. A document set with no examples is
          unverifiable (exit 2), so a wrong path never passes vacuously.
``run``   Send each example to a local base URL and compare status and the
          documented response. Writes an evidence file when asked.

Exit codes: 0 clean, 1 findings or failed examples, 2 bad input or unverifiable (unreachable
server, remote base URL without an explicit flag, no examples to lint, a response over the size
cap or cut short, a request or run past its deadline). A failure or lint finding found before
such a stop is still exit 1. A stop with ``--evidence`` writes the file (UNVERIFIED if none failed).
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import ipaddress
import json
import platform
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))

from doc_examples import (
    Example,
    InputError,
    parse_document,
)

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_UNVERIFIABLE = 2

TIMEOUT_SECONDS = 10
# The socket timeout restarts on every receive, so a trickling server never trips it. These
# bound bytes and wall clock: 2 MiB is far above a documented JSON reply, 30 s is three socket
# timeouts. A run can overshoot its deadline by one request deadline (checked between examples).
MAX_BODY_BYTES = 2 * 1024 * 1024
REQUEST_DEADLINE_SECONDS = 30
RUN_DEADLINE_SECONDS = 300
_CHUNK_BYTES = 64 * 1024
REDACTED_HEADERS = frozenset({"authorization", "cookie", "proxy-authorization", "x-api-key"})

_PLACEHOLDER = re.compile(r"^<[^<>]+>$")


def _is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def check_base_url(base_url: str, allow_remote: bool) -> str:
    """Return the normalized base URL or raise InputError."""
    parts = urlsplit(base_url)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise InputError(f"base URL must be http(s)://host[:port], got `{base_url}`")
    if not allow_remote and not _is_loopback(parts.hostname):
        raise InputError(
            f"refusing non-loopback host `{parts.hostname}`: examples can mutate state; "
            "point at a local or mock server, or pass --allow-remote for a test environment"
        )
    return base_url.rstrip("/")


@dataclass
class Reply:
    """What the server returned."""

    status: int
    body: bytes


Sender = Callable[[str, str, dict[str, str], bytes], Reply]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Return a 3xx as a reply. A redirect could leave the loopback-checked host."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)
# An empty ProxyHandler turns off HTTP_PROXY and HTTPS_PROXY: loopback must reach the local server.
_DIRECT_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)


def _opener_for(url: str) -> urllib.request.OpenerDirector:
    host = urlsplit(url).hostname
    return _DIRECT_OPENER if host is not None and _is_loopback(host) else _OPENER


def _read_capped(handle: Any, url: str) -> bytes:
    """Read a body in chunks. Refuse one past the byte cap or cut short of its Content-Length."""
    chunks: list[bytes] = []
    total = 0
    while chunk := handle.read(_CHUNK_BYTES):
        total += len(chunk)
        if total > MAX_BODY_BYTES:
            raise InputError(f"response from {url} is over the {MAX_BODY_BYTES} byte cap")
        chunks.append(chunk)
    size = handle.headers.get("Content-Length", "")
    if size.isdigit() and total < int(size):
        raise InputError(f"response from {url} was cut off at {total} of {size} bytes")
    return b"".join(chunks)


def _fetch(request: urllib.request.Request, url: str) -> Reply:
    try:
        with _opener_for(url).open(request, timeout=TIMEOUT_SECONDS) as handle:
            return Reply(handle.status, _read_capped(handle, url))
    except urllib.error.HTTPError as exc:
        return Reply(exc.code, _read_capped(exc, url))


def _within_deadline(call: Callable[[], Reply], url: str) -> Reply:
    """Run `call` on a daemon thread and give up after REQUEST_DEADLINE_SECONDS.

    The deadline covers connect, headers, and body together. A late thread is left to
    end on its own socket timeout or when the process exits, and its result is dropped.
    """
    outcome: list[Reply | Exception] = []

    def work() -> None:
        try:
            outcome.append(call())
        except Exception as exc:  # re-raised on the caller's thread
            outcome.append(exc)

    worker = threading.Thread(target=work, daemon=True)
    worker.start()
    worker.join(REQUEST_DEADLINE_SECONDS)
    if not outcome:
        raise InputError(f"response from {url} is slower than {REQUEST_DEADLINE_SECONDS}s")
    if isinstance(outcome[0], Exception):
        raise outcome[0]
    return outcome[0]


def send(method: str, url: str, headers: dict[str, str], body: bytes) -> Reply:
    """Send one request and return status and body. Non-2xx is a Reply, not an error."""
    request = urllib.request.Request(url, data=body or None, headers=headers, method=method)
    try:
        return _within_deadline(lambda: _fetch(request, url), url)
    except (urllib.error.URLError, http.client.HTTPException, OSError) as exc:
        raise InputError(f"server unreachable at {url}: {exc}") from exc


def _json_type(value: Any) -> str:
    return type(value).__name__


def compare_response(documented: Any, actual: Any, where: str = "$") -> list[str]:
    """Return mismatches. Documented keys must exist in the actual response.

    Values must be equal unless the documented value is an `<angle>` placeholder,
    which only constrains the JSON type to string. Extra keys in the actual
    response are allowed: the doc may show the fields a developer needs.
    """
    if isinstance(documented, dict):
        return _compare_object(documented, actual, where)
    if isinstance(documented, list):
        return _compare_list(documented, actual, where)
    if isinstance(documented, str) and _PLACEHOLDER.match(documented):
        if isinstance(actual, str):
            return []
        return [f"{where}: placeholder `{documented}` expects a string, got {_json_type(actual)}"]
    if documented != actual or _json_type(documented) != _json_type(actual):
        return [f"{where}: documented {documented!r}, actual {actual!r}"]
    return []


def _compare_object(documented: dict[str, Any], actual: Any, where: str) -> list[str]:
    if not isinstance(actual, dict):
        return [f"{where}: documented object, actual {_json_type(actual)}"]
    out: list[str] = []
    for key, value in documented.items():
        if key not in actual:
            out.append(f"{where}.{key}: documented key missing from the response")
            continue
        out.extend(compare_response(value, actual[key], f"{where}.{key}"))
    return out


def _compare_list(documented: list[Any], actual: Any, where: str) -> list[str]:
    if not isinstance(actual, list):
        return [f"{where}: documented array, actual {_json_type(actual)}"]
    out: list[str] = []
    for position, value in enumerate(documented):
        if position >= len(actual):
            out.append(f"{where}[{position}]: documented element missing from the response")
            continue
        out.extend(compare_response(value, actual[position], f"{where}[{position}]"))
    return out


def _redact(headers: dict[str, str]) -> dict[str, str]:
    return {k: ("<redacted>" if k.lower() in REDACTED_HEADERS else v) for k, v in headers.items()}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _decode_json(raw: bytes) -> Any:
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def run_example(example: Example, base_url: str, sender: Sender) -> dict[str, Any]:
    """Execute one example and return its evidence record."""
    url = base_url + example.path
    payload = example.body.encode("utf-8")
    reply = sender(example.method, url, dict(example.headers), payload)
    mismatches: list[str] = []
    if reply.status != example.expect:
        mismatches.append(f"status: documented {example.expect}, actual {reply.status}")
    if example.has_response:
        actual = _decode_json(reply.body)
        if actual is None:
            mismatches.append("response: body is not JSON but the doc shows a JSON response")
        else:
            mismatches.extend(compare_response(example.response, actual))
    return {
        "id": example.id,
        "doc": example.doc,
        "line": example.line,
        "request": {
            "method": example.method,
            "url": url,
            "headers": _redact(example.headers),
            "body_sha256": _sha256(payload),
        },
        "expected_status": example.expect,
        "actual_status": reply.status,
        "response_sha256": _sha256(reply.body),
        "verdict": "FAIL" if mismatches else "PASS",
        "mismatches": mismatches,
    }


def _collect(
    paths: Sequence[str], touching: str | None
) -> tuple[list[Example], list[dict[str, Any]]]:
    if not paths:
        raise InputError("pass at least one markdown file")
    examples: list[Example] = []
    findings: list[dict[str, Any]] = []
    for raw in paths:
        parsed = parse_document(Path(raw))
        examples.extend(parsed.examples)
        findings.extend(parsed.findings)
    if touching is not None:
        examples = [e for e in examples if e.path.startswith(touching)]
    return examples, findings


def _describe(example: Example) -> dict[str, Any]:
    return {
        "id": example.id,
        "doc": example.doc,
        "line": example.line,
        "method": example.method,
        "path": example.path,
        "expect": example.expect,
    }


def cmd_list(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    """List examples, optionally only those touching a path prefix."""
    examples, _ = _collect(args.docs, args.touching)
    return {"count": len(examples), "examples": [_describe(e) for e in examples]}, EXIT_OK


def cmd_lint(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    """Report structure findings. No network."""
    examples, findings = _collect(args.docs, None)
    if not examples and not findings:
        raise InputError("no examples found in the given files; nothing was linted")
    verdict = "FAIL" if findings else "PASS"
    report = {"verdict": verdict, "examples": len(examples), "findings": findings}
    return report, (EXIT_FINDINGS if findings else EXIT_OK)


def _evidence(
    args: argparse.Namespace, base_url: str, results: list[dict[str, Any]]
) -> dict[str, Any]:
    docs = {d: _sha256(Path(d).read_bytes()) for d in args.docs}
    failed = [r for r in results if r["verdict"] == "FAIL"]
    return {
        "verdict": "FAIL" if failed else "PASS",
        "base_url": base_url,
        "ran_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "python": platform.python_version(),
        "doc_sha256": docs,
        "touching": args.touching,
        "executed": len(results),
        "failed": len(failed),
        "results": results,
    }


def cmd_run(args: argparse.Namespace, sender: Sender = send) -> tuple[dict[str, Any], int]:
    """Execute examples against a local or mock server."""
    base_url = check_base_url(args.base_url, args.allow_remote)
    examples, findings = _collect(args.docs, args.touching)
    runnable = [e for e in examples if e.expect is not None]
    if not runnable:
        raise InputError("no executable examples matched; nothing was verified")
    deadline = time.monotonic() + RUN_DEADLINE_SECONDS
    results: list[dict[str, Any]] = []
    for example in runnable:
        if time.monotonic() > deadline:
            return _past_deadline(args, base_url, results, runnable[len(results) :], findings)
        try:
            results.append(run_example(example, base_url, sender))
        except InputError as exc:
            return _request_failed(args, base_url, results, runnable[len(results) :], findings, exc)
    report = _report(args, base_url, results, findings)
    _write_evidence(args, report)
    return report, (EXIT_OK if report["verdict"] == "PASS" else EXIT_FINDINGS)


def _report(
    args: argparse.Namespace,
    base_url: str,
    results: list[dict[str, Any]],
    findings: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the run report; a lint finding makes the verdict FAIL."""
    report = _evidence(args, base_url, results)
    report["lint_findings"] = findings
    if findings:
        report["verdict"] = "FAIL"
    return report


def _write_evidence(args: argparse.Namespace, report: dict[str, Any]) -> None:
    if args.evidence:
        Path(args.evidence).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def _stopped(
    args: argparse.Namespace,
    base_url: str,
    results: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    *,
    key: str,
    detail: dict[str, Any],
    message: str,
) -> tuple[dict[str, Any], int]:
    """Keep the finished results when a run stops early.

    A finished FAIL or a lint finding stays exit 1: the doc is stale or malformed whether
    or not the rest ran. With neither, the run is unverifiable (exit 2, ``message``). Either
    way the evidence file records the finished results, the lint findings, and ``detail``.
    """
    report = _report(args, base_url, results, findings)
    failed = report["verdict"] == "FAIL"
    if not failed:
        report["verdict"] = "UNVERIFIED"
    report[key] = detail
    _write_evidence(args, report)
    if failed:
        return report, EXIT_FINDINGS
    raise InputError(message)


def _past_deadline(
    args: argparse.Namespace,
    base_url: str,
    results: list[dict[str, Any]],
    unrun: list[Example],
    findings: list[dict[str, Any]],
) -> tuple[dict[str, Any], int]:
    """Stop a run that passed its deadline; the examples that never ran are listed."""
    detail = {"seconds": RUN_DEADLINE_SECONDS, "unrun": [e.id for e in unrun]}
    message = (
        f"run passed its {RUN_DEADLINE_SECONDS}s deadline after {len(results)} of "
        f"{len(results) + len(unrun)} examples, before `{unrun[0].id}`; "
        "the run is unverified and the finished results are not a verdict"
    )
    return _stopped(
        args, base_url, results, findings, key="deadline_exceeded", detail=detail, message=message
    )


def _request_failed(
    args: argparse.Namespace,
    base_url: str,
    results: list[dict[str, Any]],
    unrun: list[Example],
    findings: list[dict[str, Any]],
    error: InputError,
) -> tuple[dict[str, Any], int]:
    """Stop a run whose request could not finish (deadline, byte cap, unreachable server).

    ``unrun`` starts with the example that failed. Its request may have reached the server,
    so the report names it under ``example`` and lists only the examples after it as unrun.
    Earlier results and lint findings are kept, as for a run deadline.
    """
    detail = {"example": unrun[0].id, "error": str(error), "unrun": [e.id for e in unrun[1:]]}
    message = (
        f"example `{unrun[0].id}` could not finish after {len(results)} of "
        f"{len(results) + len(unrun)} examples: {error}; "
        "the run is unverified and the finished results are not a verdict"
    )
    return _stopped(
        args, base_url, results, findings, key="request_failed", detail=detail, message=message
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name, helptext in (
        ("list", "list executable examples"),
        ("lint", "check example and error-table structure"),
        ("run", "execute examples against a local or mock server"),
    ):
        child = sub.add_parser(name, help=helptext)
        child.add_argument("docs", nargs="+", help="markdown files")
        if name != "lint":
            child.add_argument(
                "--touching", help="only examples whose request path starts with this"
            )
    run = sub.choices["run"]
    run.add_argument(
        "--base-url", required=True, help="http://127.0.0.1:PORT of a local or mock API"
    )
    run.add_argument("--allow-remote", action="store_true", help="permit a non-loopback host")
    run.add_argument("--evidence", help="write the evidence JSON here")
    return parser


_COMMANDS: dict[str, Callable[[argparse.Namespace], tuple[dict[str, Any], int]]] = {
    "list": cmd_list,
    "lint": cmd_lint,
    "run": cmd_run,
}


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""
    args = build_parser().parse_args(argv)
    try:
        report, code = _COMMANDS[args.command](args)
    except InputError as exc:
        print(json.dumps({"verdict": "UNVERIFIED", "error": str(exc)}))
        return EXIT_UNVERIFIABLE
    print(json.dumps(report, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
