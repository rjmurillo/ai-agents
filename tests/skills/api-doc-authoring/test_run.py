"""Execution, stale-example, and mutation-control tests for api_examples."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import api_examples as ax
import pytest
from api_fixtures import WORKED_EXAMPLE

WriteDoc = Callable[[str, str], Path]


def run_args(
    docs: list[Path],
    base_url: str,
    evidence: Path | None = None,
    touching: str | None = None,
    allow_remote: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        docs=[str(d) for d in docs],
        base_url=base_url,
        allow_remote=allow_remote,
        evidence=str(evidence) if evidence else None,
        touching=touching,
    )


def trusting_sender(documented: dict[str, tuple[int, Any]]) -> ax.Sender:
    """A verifier that never calls the API: it believes the prose (mutation control)."""

    def _send(method: str, url: str, headers: dict[str, str], body: bytes) -> ax.Reply:
        path = url.split("/", 3)[3]
        status, payload = documented[f"{method} /{path}"]
        return ax.Reply(status, json.dumps(payload).encode("utf-8"))

    return _send


def test_working_examples_pass_and_evidence_is_recorded(order_api: str, tmp_path: Path) -> None:
    evidence = tmp_path / "evidence.json"
    report, code = ax.cmd_run(run_args([WORKED_EXAMPLE], order_api, evidence))
    assert code == ax.EXIT_OK and report["verdict"] == "PASS"
    assert report["executed"] == 4 and report["failed"] == 0
    saved = json.loads(evidence.read_text(encoding="utf-8"))
    assert saved["base_url"] == order_api
    assert len(saved["doc_sha256"][str(WORKED_EXAMPLE)]) == 64
    first = saved["results"][0]
    assert first["request"]["url"] == f"{order_api}/orders"
    assert first["actual_status"] == 201 and len(first["response_sha256"]) == 64
    assert saved["python"] and saved["ran_at"]


def test_stale_example_fails_after_the_api_changes(changed_order_api: str, tmp_path: Path) -> None:
    report, code = ax.cmd_run(run_args([WORKED_EXAMPLE], changed_order_api))
    assert code == ax.EXIT_FINDINGS and report["verdict"] == "FAIL"
    failed = {r["id"]: r for r in report["results"] if r["verdict"] == "FAIL"}
    assert "create-order" in failed
    assert "status: documented 201, actual 422" in failed["create-order"]["mismatches"]


def test_mutation_control_prose_only_trust_misses_the_stale_example(
    order_api: str, changed_order_api: str
) -> None:
    """Without execution the stale doc looks fine. With execution it fails."""
    documented = {
        "POST /orders": (201, {"id": "ord_1", "status": "pending"}),
        "GET /orders/ord_1": (200, {"id": "ord_1", "status": "pending", "qty": 2}),
        "GET /orders/ord_999": (404, {"error": "order_not_found"}),
    }
    args = run_args([WORKED_EXAMPLE], changed_order_api, touching="/orders/")
    trusted, trusted_code = ax.cmd_run(args, sender=trusting_sender(documented))
    executed, executed_code = ax.cmd_run(args)
    assert (trusted["verdict"], trusted_code) == ("PASS", ax.EXIT_OK)
    assert (executed["verdict"], executed_code) == ("FAIL", ax.EXIT_FINDINGS)


def test_documented_status_mutation_is_caught(order_api: str, write_doc: WriteDoc) -> None:
    text = WORKED_EXAMPLE.read_text(encoding="utf-8").replace(
        "example=create-order expect=201", "example=create-order expect=200"
    )
    report, code = ax.cmd_run(run_args([write_doc("m.md", text)], order_api))
    assert code == ax.EXIT_FINDINGS
    assert "status: documented 200, actual 201" in report["results"][0]["mismatches"]


def test_documented_field_mutation_is_caught(order_api: str, write_doc: WriteDoc) -> None:
    text = WORKED_EXAMPLE.read_text(encoding="utf-8").replace(
        '{"id": "<id>", "status": "pending"}', '{"id": "<id>", "state": "pending"}'
    )
    report, code = ax.cmd_run(run_args([write_doc("m.md", text)], order_api))
    assert code == ax.EXIT_FINDINGS
    assert "$.state: documented key missing from the response" in report["results"][0]["mismatches"]


def test_touching_selects_only_affected_examples(order_api: str) -> None:
    report, code = ax.cmd_run(run_args([WORKED_EXAMPLE], order_api, touching="/orders/ord_999"))
    assert code == ax.EXIT_OK and [r["id"] for r in report["results"]] == ["missing-order"]


def test_authorization_header_is_redacted_in_evidence(order_api: str, write_doc: WriteDoc) -> None:
    text = "```http example=a expect=404\nGET /orders/none\nAuthorization: Bearer secret\n```\n"
    report, _ = ax.cmd_run(run_args([write_doc("d.md", text)], order_api))
    headers = report["results"][0]["request"]["headers"]
    assert headers == {"Authorization": "<redacted>"}
    assert "secret" not in json.dumps(report)


def test_lint_findings_fail_the_run(order_api: str, write_doc: WriteDoc) -> None:
    text = "```http example=a expect=404\nGET /orders/none\n```\n```json response=ghost\n{}\n```\n"
    report, code = ax.cmd_run(run_args([write_doc("d.md", text)], order_api))
    assert code == ax.EXIT_FINDINGS
    assert report["lint_findings"][0]["code"] == "unverified-response"


def test_no_matching_examples_is_unverified_not_pass(order_api: str) -> None:
    with pytest.raises(ax.InputError, match="nothing was verified"):
        ax.cmd_run(run_args([WORKED_EXAMPLE], order_api, touching="/nowhere"))


def test_example_without_status_is_not_executed(order_api: str, write_doc: WriteDoc) -> None:
    text = "```http example=a\nGET /orders/none\n```\n"
    with pytest.raises(ax.InputError):
        ax.cmd_run(run_args([write_doc("d.md", text)], order_api))


def test_unreachable_server_is_unverified(write_doc: WriteDoc) -> None:
    text = "```http example=a expect=200\nGET /x\n```\n"
    with pytest.raises(ax.InputError, match="unreachable"):
        ax.cmd_run(run_args([write_doc("d.md", text)], "http://127.0.0.1:1"))


def test_non_json_body_when_json_is_documented(write_doc: WriteDoc) -> None:
    text = '```http example=a expect=200\nGET /x\n```\n```json response=a\n{"a": 1}\n```\n'

    def html(*_: Any) -> ax.Reply:
        return ax.Reply(200, b"<html>")

    result = ax.run_example(
        ax.parse_document(write_doc("d.md", text)).examples[0], "http://127.0.0.1:1", html
    )
    assert result["verdict"] == "FAIL"
    assert "not JSON" in result["mismatches"][0]


def test_non_utf8_body_is_not_json(write_doc: WriteDoc) -> None:
    text = "```http example=a expect=200\nGET /x\n```\n```json response=a\n{}\n```\n"

    def binary(*_: Any) -> ax.Reply:
        return ax.Reply(200, b"\xff\xfe")

    example = ax.parse_document(write_doc("d.md", text)).examples[0]
    assert ax.run_example(example, "http://x", binary)["verdict"] == "FAIL"


@pytest.mark.parametrize(
    ("host", "allowed"),
    [
        ("http://127.0.0.1:8080", True),
        ("http://localhost:8080/", True),
        ("http://[::1]:8080", True),
        ("https://api.example.com", False),
        ("http://10.0.0.5", False),
    ],
)
def test_remote_hosts_are_refused_without_the_flag(host: str, allowed: bool) -> None:
    if allowed:
        assert ax.check_base_url(host, False) == host.rstrip("/")
        return
    with pytest.raises(ax.InputError, match="non-loopback"):
        ax.check_base_url(host, False)
    assert ax.check_base_url(host, True) == host.rstrip("/")


@pytest.mark.parametrize("bad", ["ftp://x", "not a url", "http://"])
def test_bad_base_url_is_rejected(bad: str) -> None:
    with pytest.raises(ax.InputError, match="base URL"):
        ax.check_base_url(bad, True)


@pytest.mark.parametrize(
    ("documented", "actual", "expected"),
    [
        ({"a": 1}, {"a": 1, "extra": 2}, []),
        ({"a": 1}, {"a": 2}, ["$.a: documented 1, actual 2"]),
        ({"a": 1}, {"a": 1.0}, ["$.a: documented 1, actual 1.0"]),
        ({"a": "<x>"}, {"a": "v"}, []),
        ({"a": "<x>"}, {"a": 3}, ["$.a: placeholder `<x>` expects a string, got int"]),
        ({"a": {"b": 1}}, {"a": 1}, ["$.a: documented object, actual int"]),
        ([1, 2], [1, 2, 3], []),
        ([1, 2], [1], ["$[1]: documented element missing from the response"]),
        ([1], {"a": 1}, ["$: documented array, actual dict"]),
        ([{"id": "<i>"}], [{"id": "z"}], []),
    ],
)
def test_compare_response(documented: Any, actual: Any, expected: list[str]) -> None:
    assert ax.compare_response(documented, actual) == expected


def test_send_returns_http_errors_as_replies(order_api: str) -> None:
    reply = ax.send("GET", f"{order_api}/orders/none", {}, b"")
    assert reply.status == 404 and b"order_not_found" in reply.body
