"""Parsing and structure-lint tests for api_examples."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import api_examples as ax
import pytest
from api_fixtures import WORKED_EXAMPLE
from doc_examples import ParsedDoc

WriteDoc = Callable[[str, str], Path]

GOOD = """# Doc

```http example=a expect=200
GET /things
```

```json response=a
{"ok": true}
```
"""


def codes(parsed: ParsedDoc) -> list[str]:
    return [f["code"] for f in parsed.findings]


def test_worked_example_parses_clean() -> None:
    parsed = ax.parse_document(WORKED_EXAMPLE)
    assert parsed.findings == []
    assert [e.id for e in parsed.examples] == [
        "create-order",
        "get-order",
        "reject-zero-quantity",
        "missing-order",
    ]


def test_request_headers_body_and_response_are_extracted(write_doc: WriteDoc) -> None:
    parsed = ax.parse_document(write_doc("d.md", GOOD))
    (example,) = parsed.examples
    assert (example.method, example.path, example.expect) == ("GET", "/things", 200)
    assert example.has_response and example.response == {"ok": True}
    assert example.line == 3


def test_post_headers_and_body(write_doc: WriteDoc) -> None:
    text = (
        "```http example=p expect=201\nPOST /x HTTP/1.1\nContent-Type: application/json\n"
        'X-Trace: 1\n\n{"a": 1}\n```\n'
    )
    (example,) = ax.parse_document(write_doc("d.md", text)).examples
    assert example.headers == {"Content-Type": "application/json", "X-Trace": "1"}
    assert example.body == '{"a": 1}'


def test_header_line_without_a_colon_is_skipped(write_doc: WriteDoc) -> None:
    text = "```http example=p expect=200\nGET /x\nnot-a-header\nAccept: */*\n```\n"
    (example,) = ax.parse_document(write_doc("d.md", text)).examples
    assert example.headers == {"Accept": "*/*"}


def test_illustrative_http_fence_is_ignored(write_doc: WriteDoc) -> None:
    parsed = ax.parse_document(write_doc("d.md", "```http\nGET /not-an-example\n```\n"))
    assert parsed.examples == [] and parsed.findings == []


def test_other_languages_are_ignored(write_doc: WriteDoc) -> None:
    text = "```python example=a expect=200\nprint(1)\n```\n"
    parsed = ax.parse_document(write_doc("d.md", text))
    assert parsed.examples == [] and parsed.findings == []


def test_longer_outer_fence_hides_inner_example(write_doc: WriteDoc) -> None:
    text = "````text\n```http example=a expect=200\nGET /x\n```\n````\n"
    assert ax.parse_document(write_doc("d.md", text)).examples == []


def test_tilde_fences_work(write_doc: WriteDoc) -> None:
    text = "~~~http example=a expect=200\nGET /x\n~~~\n"
    assert len(ax.parse_document(write_doc("d.md", text)).examples) == 1


def test_unclosed_fence_yields_nothing(write_doc: WriteDoc) -> None:
    parsed = ax.parse_document(write_doc("d.md", "```http example=a expect=200\nGET /x\n"))
    assert parsed.examples == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("```http expect=200\nGET /x\n```\n", "missing-id"),
        ("```http example=a\nGET /x\n```\n", "missing-expect"),
        ("```http example=a expect=ok\nGET /x\n```\n", "missing-expect"),
        ("```http example=a expect=200\nnot a request\n```\n", "bad-request"),
        ("```http example=a expect=200\n```\n", "bad-request"),
        (
            "```http example=a expect=200\nGET /x\n```\n"
            "```http example=a expect=200\nGET /y\n```\n",
            "duplicate-id",
        ),
        ("```json response=ghost\n{}\n```\n", "unverified-response"),
        (
            "```http example=a expect=200\nGET /x\n```\n```json response=a\n{oops\n```\n",
            "bad-response-json",
        ),
    ],
)
def test_structure_findings(write_doc: WriteDoc, text: str, expected: str) -> None:
    assert expected in codes(ax.parse_document(write_doc("d.md", text)))


def test_unreadable_document_is_an_input_error(tmp_path: Path) -> None:
    with pytest.raises(ax.InputError):
        ax.parse_document(tmp_path / "missing.md")


def test_error_table_row_with_empty_cause_and_action(write_doc: WriteDoc) -> None:
    text = "| Status | Cause | Action |\n|---|---|---|\n| 404 | | |\n| 422 | bad | fix |\n"
    found = codes(ax.parse_document(write_doc("d.md", text)))
    assert sorted(found) == ["error-missing-action", "error-missing-cause"]


def test_error_table_unknown_marker_is_accepted(write_doc: WriteDoc) -> None:
    text = "| Status | Cause | Action |\n|---|---|---|\n| 500 | Unknown | Unknown |\n"
    assert ax.parse_document(write_doc("d.md", text)).findings == []


def test_error_table_without_action_column(write_doc: WriteDoc) -> None:
    text = "| Status | Cause |\n|---|---|\n| 404 | gone |\n"
    assert codes(ax.parse_document(write_doc("d.md", text))) == ["error-missing-action"]


def test_short_error_row_reports_missing_cells(write_doc: WriteDoc) -> None:
    text = "| Status | Cause | Action |\n|---|---|---|\n| 404 |\n"
    found = codes(ax.parse_document(write_doc("d.md", text)))
    assert sorted(found) == ["error-missing-action", "error-missing-cause"]


def test_non_error_tables_are_not_linted(write_doc: WriteDoc) -> None:
    text = "| Field | Type |\n|---|---|\n| sku | |\n"
    assert ax.parse_document(write_doc("d.md", text)).findings == []


def test_table_inside_a_fence_is_not_linted(write_doc: WriteDoc) -> None:
    text = "```text\n| Status | Cause | Action |\n|---|---|---|\n| 404 | | |\n```\n"
    assert ax.parse_document(write_doc("d.md", text)).findings == []


def test_pipe_text_without_separator_is_not_a_table(write_doc: WriteDoc) -> None:
    assert ax.parse_document(write_doc("d.md", "a | b\nnot a separator\n")).findings == []
