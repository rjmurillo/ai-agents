"""Parse API documentation into executable examples and structure findings.

Shared by ``api_examples.py``. An executable example is a fenced ``http`` block
whose info string carries ``example=<id>`` and ``expect=<status>``; a ``json``
block with ``response=<id>`` documents what comes back. Error tables are
checked for a cause and an action per row.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

UNKNOWN_CELL = "unknown"

_FENCE_OPEN = re.compile(r"^(?P<indent> {0,3})(?P<fence>`{3,}|~{3,})\s*(?P<info>.*?)\s*$")
_REQUEST_LINE = re.compile(r"^(?P<method>[A-Z]+)\s+(?P<path>/\S*)(?:\s+HTTP/\d(?:\.\d)?)?$")
_TABLE_SEPARATOR = re.compile(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?$")


class InputError(Exception):
    """The caller supplied something the tool cannot verify."""


@dataclass
class Example:
    """One executable request parsed from a documentation fence."""

    id: str
    doc: str
    line: int
    method: str
    path: str
    headers: dict[str, str]
    body: str
    expect: int | None
    response: Any = None
    has_response: bool = False


@dataclass
class ParsedDoc:
    """Examples plus structural findings for one document."""

    examples: list[Example] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)


def _finding(doc: str, line: int, code: str, message: str) -> dict[str, Any]:
    return {"doc": doc, "line": line, "code": code, "message": message}


def _info_pairs(info: str) -> tuple[str, dict[str, str]]:
    parts = info.split()
    lang = parts[0].lower() if parts else ""
    pairs = {k: v for k, _, v in (p.partition("=") for p in parts[1:]) if k and v}
    return lang, pairs


def _fence_blocks(lines: list[str]) -> list[tuple[int, str, list[str]]]:
    """Return (line, info, body lines) for each closed fenced block.

    A fence closes on the same character with at least the opening length, so a
    longer outer fence can show a shorter fence as plain text.
    """
    blocks: list[tuple[int, str, list[str]]] = []
    opener: re.Match[str] | None = None
    start = 0
    body: list[str] = []
    for number, text in enumerate(lines, start=1):
        if opener is None:
            opener = _FENCE_OPEN.match(text)
            if opener:
                start, body = number, []
            continue
        marker = opener.group("fence")
        stripped = text.strip()
        if stripped and set(stripped) == {marker[0]} and len(stripped) >= len(marker):
            blocks.append((start, opener.group("info"), body))
            opener = None
        else:
            body.append(text)
    return blocks


def _parse_request(body: list[str]) -> tuple[str, str, dict[str, str], str] | None:
    if not body:
        return None
    match = _REQUEST_LINE.match(body[0].strip())
    if match is None:
        return None
    headers: dict[str, str] = {}
    index = 1
    while index < len(body) and body[index].strip():
        name, sep, value = body[index].partition(":")
        if sep:
            headers[name.strip()] = value.strip()
        index += 1
    payload = "\n".join(body[index + 1 :]).strip()
    return match.group("method"), match.group("path"), headers, payload


def _parse_expect(raw: str | None) -> int | None:
    if raw is None or not raw.isdigit():
        return None
    return int(raw)


def _build_example(doc: str, line: int, pairs: dict[str, str], body: list[str]) -> Example | str:
    request = _parse_request(body)
    if request is None:
        return "http example block has no valid `METHOD /path` request line"
    method, path, headers, payload = request
    expect = _parse_expect(pairs.get("expect"))
    return Example(pairs.get("example", ""), doc, line, method, path, headers, payload, expect)


def _example_problems(example: Example, seen: set[str]) -> list[tuple[str, str]]:
    problems: list[tuple[str, str]] = []
    if not example.id:
        problems.append(("missing-id", "http example needs `example=<id>` in its info string"))
    elif example.id in seen:
        problems.append(("duplicate-id", f"example id `{example.id}` is used more than once"))
    if example.expect is None:
        problems.append(("missing-expect", "http example needs a numeric `expect=<status>`"))
    return problems


def _attach_response(
    doc: str,
    line: int,
    pairs: dict[str, str],
    body: list[str],
    by_id: dict[str, Example],
    findings: list[dict[str, Any]],
) -> None:
    target = pairs["response"]
    example = by_id.get(target)
    if example is None:
        findings.append(
            _finding(
                doc,
                line,
                "unverified-response",
                f"response block names `{target}` but no executable request has that id",
            )
        )
        return
    try:
        example.response = json.loads("\n".join(body))
    except json.JSONDecodeError as exc:
        findings.append(_finding(doc, line, "bad-response-json", f"response `{target}`: {exc.msg}"))
        return
    example.has_response = True


def parse_document(path: Path) -> ParsedDoc:
    """Parse one markdown file into examples and structure findings."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise InputError(f"cannot read {path}: {exc}") from exc
    doc = str(path)
    lines = text.splitlines()
    parsed = ParsedDoc()
    by_id: dict[str, Example] = {}
    for line, info, body in _fence_blocks(lines):
        lang, pairs = _info_pairs(info)
        if lang == "http" and ("example" in pairs or "expect" in pairs):
            built = _build_example(doc, line, pairs, body)
            if isinstance(built, str):
                parsed.findings.append(_finding(doc, line, "bad-request", built))
                continue
            for code, message in _example_problems(built, set(by_id)):
                parsed.findings.append(_finding(doc, line, code, message))
            parsed.examples.append(built)
            by_id.setdefault(built.id, built)
        elif lang == "json" and "response" in pairs:
            _attach_response(doc, line, pairs, body, by_id, parsed.findings)
    parsed.findings.extend(_table_findings(doc, lines))
    return parsed


def _cells(row: str) -> list[str]:
    return [cell.strip() for cell in row.strip().strip("|").split("|")]


def _is_error_table(header: list[str]) -> bool:
    names = [h.lower() for h in header]
    first = names[0] if names else ""
    return first in {"status", "error", "code", "status code"} and "cause" in names


def _row_findings(doc: str, line: int, header: list[str], cells: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    names = [h.lower() for h in header]
    for column in ("cause", "action"):
        if column not in names:
            continue
        value = cells[names.index(column)] if names.index(column) < len(cells) else ""
        if not value:
            out.append(
                _finding(
                    doc,
                    line,
                    f"error-missing-{column}",
                    f"error row `{cells[0]}` has an empty {column}; "
                    f"write the evidenced {column} or `{UNKNOWN_CELL}`",
                )
            )
    return out


def _table_findings(doc: str, lines: list[str]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    in_fence: set[int] = set()
    for opened, _info, body in _fence_blocks(lines):
        in_fence.update(range(opened, opened + len(body) + 2))
    index = 0
    while index < len(lines) - 1:
        row = lines[index]
        follows = _TABLE_SEPARATOR.match(lines[index + 1].strip())
        if index + 1 in in_fence or "|" not in row or not follows:
            index += 1
            continue
        header = _cells(row)
        index += 2
        is_errors = _is_error_table(header)
        if is_errors and "action" not in [h.lower() for h in header]:
            findings.append(
                _finding(doc, index, "error-missing-action", "error table has no Action column")
            )
        while index < len(lines) and "|" in lines[index]:
            if is_errors:
                findings.extend(_row_findings(doc, index + 1, header, _cells(lines[index])))
            index += 1
    return findings
