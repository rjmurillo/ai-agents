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
          with a missing cause or action.
``run``   Send each example to a local base URL and compare status and the
          documented response. Writes an evidence file when asked.

Exit codes: 0 clean, 1 findings or failed examples, 2 bad input or unverifiable
(unreachable server, remote base URL without an explicit flag).
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import platform
import re
import sys
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


def send(method: str, url: str, headers: dict[str, str], body: bytes) -> Reply:
    """Send one request and return status and body. Non-2xx is a Reply, not an error."""
    request = urllib.request.Request(url, data=body or None, headers=headers, method=method)
    try:
        with _OPENER.open(request, timeout=TIMEOUT_SECONDS) as handle:
            return Reply(handle.status, handle.read())
    except urllib.error.HTTPError as exc:
        return Reply(exc.code, exc.read())
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
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
    results = [run_example(e, base_url, sender) for e in runnable]
    report = _evidence(args, base_url, results)
    report["lint_findings"] = findings
    if findings:
        report["verdict"] = "FAIL"
    if args.evidence:
        Path(args.evidence).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report, (EXIT_OK if report["verdict"] == "PASS" else EXIT_FINDINGS)


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
