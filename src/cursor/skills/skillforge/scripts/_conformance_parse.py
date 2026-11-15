"""Read a skill directory into the shape the conformance checks need.

The frontmatter parser here is deliberately small and standard-library only.
It never uses PyYAML, so a verdict does not depend on what is installed. It
reads block mappings, block sequences, plain and quoted scalars, and literal
or folded block scalars. Anything else (anchors, aliases, tags, complex flow
collections) raises UnsupportedError, and the checks that need typed values then
report NOT_EVALUATED instead of guessing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

KEY_RE = re.compile(r"^([A-Za-z0-9_][A-Za-z0-9_.-]*)[ \t]*:(?:[ \t]+(.*)|[ \t]*)$")
BLOCK_SCALAR_RE = re.compile(r"^([|>])([+-]?)([1-9]?)([+-]?)\s*(?:#.*)?$")
SIMPLE_FLOW_LIST_RE = re.compile(r"^\[([^\[\]{}\"'&*!]*)\]$")

# YAML 1.2 core schema: plain scalars that a standard loader turns into a
# non-string value.
_CORE_TYPES = (
    ("null", re.compile(r"^(?:~|null|Null|NULL)$")),
    ("bool", re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$")),
    ("int", re.compile(r"^(?:[-+]?[0-9]+|0o[0-7]+|0x[0-9a-fA-F]+)$")),
    (
        "float",
        re.compile(
            r"^(?:[-+]?(?:\.[0-9]+|[0-9]+(?:\.[0-9]*)?)(?:[eE][-+]?[0-9]+)?"
            r"|[-+]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN))$"
        ),
    ),
)


class UnsupportedError(Exception):
    """The frontmatter uses a YAML construct this parser does not read."""


class ParseError(Exception):
    """The frontmatter is not a valid YAML mapping."""


class Scalar(str):
    """A string value that remembers whether it was written unquoted."""

    plain: bool = False

    def __new__(cls, text: str, plain: bool = False) -> Scalar:
        obj = super().__new__(cls, text)
        obj.plain = plain
        return obj


def core_type(value: object) -> str | None:
    """Return the YAML core type a plain scalar resolves to, or None for a string."""
    if not isinstance(value, Scalar) or not value.plain:
        return None
    for name, pattern in _CORE_TYPES:
        if pattern.match(value):
            return name
    return None


@dataclass
class SkillDoc:
    """Everything the checks read about one skill directory."""

    directory: Path
    skill_md: Path | None = None
    text: str = ""
    has_frontmatter: bool = False
    frontmatter_error: str | None = None
    body: str = ""
    fields: dict[str, object] | None = None
    parse_error: str | None = None
    unsupported: str | None = None
    notes: list[str] = field(default_factory=list)


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _is_skippable(line: str) -> bool:
    stripped = line.strip()
    return not stripped or stripped.startswith("#")


def _strip_comment(text: str) -> str:
    match = re.search(r"\s#", text)
    return text[: match.start()].rstrip() if match else text.rstrip()


_ESCAPES = {"n": "\n", "t": "\t", '"': '"', "\\": "\\", "/": "/", "0": "\0"}


def _unquote(text: str, line_no: int) -> Scalar:
    """Read one single- or double-quoted scalar that fits on its line."""
    quote = text[0]
    out: list[str] = []
    i = 1
    while i < len(text):
        char = text[i]
        if quote == "'" and char == "'":
            if text[i + 1 : i + 2] == "'":
                out.append("'")
                i += 2
                continue
            break
        if quote == '"' and char == "\\":
            nxt = text[i + 1 : i + 2]
            if nxt not in _ESCAPES:
                raise UnsupportedError(f"line {line_no}: escape \\{nxt} is not supported")
            out.append(_ESCAPES[nxt])
            i += 2
            continue
        if quote == '"' and char == '"':
            break
        out.append(char)
        i += 1
    else:
        raise UnsupportedError(f"line {line_no}: multi-line quoted strings are not supported")
    rest = text[i + 1 :].strip()
    if rest and not rest.startswith("#"):
        raise ParseError(f"line {line_no}: unexpected text after the closing quote")
    return Scalar("".join(out))


def _scalar(text: str, line_no: int) -> object:
    if text[0] in "'\"":
        return _unquote(text, line_no)
    if text[0] in "&*!":
        raise UnsupportedError(f"line {line_no}: anchors, aliases, and tags are not supported")
    if text in ("[]", "{}"):
        return [] if text == "[]" else {}
    if text[0] in "[{":
        match = SIMPLE_FLOW_LIST_RE.match(text)
        if not match:
            raise UnsupportedError(f"line {line_no}: this flow collection is not supported")
        items = [part.strip() for part in match.group(1).split(",")]
        return [Scalar(item, plain=True) for item in items if item]
    if text[0] in "@`%":
        raise ParseError(f"line {line_no}: a plain scalar cannot start with {text[0]!r}")
    return Scalar(_strip_comment(text), plain=True)


def _block_scalar(
    lines: list[str], start: int, parent_indent: int, header: re.Match[str]
) -> tuple[Scalar, int]:
    style = header.group(1)
    chomp = header.group(2) or header.group(4)
    if chomp == "+" or header.group(3):
        raise UnsupportedError("keep chomping and indentation indicators are not supported")
    collected: list[str] = []
    i = start
    while i < len(lines) and (not lines[i].strip() or _indent(lines[i]) > parent_indent):
        collected.append(lines[i])
        i += 1
    while collected and not collected[-1].strip():
        collected.pop()
        i -= 1
    content = [line for line in collected if line.strip()]
    if not content:
        return Scalar(""), i
    width = min(_indent(line) for line in content)
    body = [line[width:] if line.strip() else "" for line in collected]
    if style == "|":
        text = "\n".join(body)
    else:
        text = ""
        for index, line in enumerate(body):
            if index and line and body[index - 1]:
                text += " "
            elif index:
                text += "\n"
            text += line
    if chomp == "-":
        return Scalar(text), i
    return Scalar(text + "\n"), i


def _plain_continuation(
    lines: list[str], start: int, parent_indent: int, first: str
) -> tuple[object, int]:
    parts = [first]
    i = start
    while i < len(lines) and lines[i].strip() and _indent(lines[i]) > parent_indent:
        if lines[i].strip().startswith("#"):
            break
        parts.append(_strip_comment(lines[i].strip()))
        i += 1
    return Scalar(" ".join(parts), plain=True), i


def _sequence(lines: list[str], start: int, indent: int) -> tuple[list[object], int]:
    items: list[object] = []
    i = start
    while i < len(lines):
        line = lines[i]
        if _is_skippable(line):
            i += 1
            continue
        if _indent(line) != indent or not line.lstrip().startswith("-"):
            break
        rest = line.strip()[1:].strip()
        if not rest:
            raise UnsupportedError(f"line {i + 1}: nested sequence items are not supported")
        if KEY_RE.match(rest):
            raise UnsupportedError(f"line {i + 1}: mappings inside a sequence are not supported")
        items.append(_scalar(rest, i + 1))
        i += 1
    return items, i


def _key_line(line: str, line_no: int) -> tuple[str, str]:
    """Split one 'key: value' line, or raise for a line this parser cannot read."""
    match = KEY_RE.match(line.strip())
    if match:
        return match.group(1), (match.group(2) or "").strip()
    if line.strip().startswith(("'", '"', "?")):
        raise UnsupportedError(f"line {line_no}: quoted or complex keys are not supported")
    raise ParseError(f"line {line_no}: expected 'key: value'")


def _inline_value(lines: list[str], i: int, indent: int, rest: str) -> tuple[object, int]:
    """Read a value written on the key's own line, plus any continuation lines."""
    header = BLOCK_SCALAR_RE.match(rest)
    if header:
        return _block_scalar(lines, i, indent, header)
    value = _scalar(rest, i)
    if isinstance(value, Scalar) and value.plain:
        return _plain_continuation(lines, i, indent, str(value))
    return value, i


def _nested_value(lines: list[str], i: int, indent: int) -> tuple[object, int]:
    """Read the block under a bare 'key:', or None when there is no block."""
    j = i
    while j < len(lines) and _is_skippable(lines[j]):
        j += 1
    if j >= len(lines):
        return None, i
    child = _indent(lines[j])
    is_item = lines[j].lstrip().startswith("-")
    if child < indent or (child == indent and not is_item):
        return None, i
    if is_item:
        return _sequence(lines, j, child)
    return _mapping(lines, j, child)


def _mapping(lines: list[str], start: int, indent: int) -> tuple[dict[str, object], int]:
    result: dict[str, object] = {}
    i = start
    while i < len(lines):
        line = lines[i]
        if _is_skippable(line):
            i += 1
            continue
        if "\t" in line[: _indent(line) + 1]:
            raise ParseError(f"line {i + 1}: tabs are not allowed in YAML indentation")
        if _indent(line) < indent:
            break
        if _indent(line) > indent:
            raise ParseError(f"line {i + 1}: unexpected indentation")
        key, rest = _key_line(line, i + 1)
        if key in result:
            raise ParseError(f"line {i + 1}: duplicate key {key!r}")
        if rest and not rest.startswith("#"):
            result[key], i = _inline_value(lines, i + 1, indent, rest)
        else:
            result[key], i = _nested_value(lines, i + 1, indent)
    return result, i


def parse_frontmatter(raw: str) -> dict[str, object]:
    """Parse frontmatter text into nested dicts, lists, and Scalar strings."""
    lines = raw.split("\n")
    first = next((line for line in lines if not _is_skippable(line)), None)
    if first is None:
        return {}
    if _indent(first) != 0:
        raise ParseError("the frontmatter must start at column 0")
    result, end = _mapping(lines, 0, 0)
    leftover = next((n for n in range(end, len(lines)) if not _is_skippable(lines[n])), None)
    if leftover is not None:
        raise ParseError(f"line {leftover + 1}: expected 'key: value'")
    return result


def split_frontmatter(text: str) -> tuple[str | None, str, str | None]:
    """Return (frontmatter, body, error). Frontmatter is None when absent."""
    text = text.lstrip("﻿").replace("\r\n", "\n")
    lines = text.split("\n")
    if not lines or lines[0].rstrip() != "---":
        return None, text, "SKILL.md does not start with a '---' line"
    for index in range(1, len(lines)):
        if lines[index].rstrip() == "---":
            return "\n".join(lines[1:index]), "\n".join(lines[index + 1 :]), None
    return None, text, "the frontmatter has no closing '---' line"


def load_skill(directory: Path) -> SkillDoc:
    """Read SKILL.md from a skill directory and parse what the checks need."""
    doc = SkillDoc(directory=directory)
    for name in ("SKILL.md", "skill.md"):
        candidate = directory / name
        if candidate.is_file():
            doc.skill_md = candidate
            if name == "skill.md":
                doc.notes.append("found skill.md; the spec names SKILL.md")
            break
    if doc.skill_md is None:
        return doc
    try:
        doc.text = doc.skill_md.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        doc.frontmatter_error = f"cannot read SKILL.md as UTF-8: {exc}"
        return doc
    raw, doc.body, doc.frontmatter_error = split_frontmatter(doc.text)
    if raw is None:
        return doc
    doc.has_frontmatter = True
    try:
        doc.fields = parse_frontmatter(raw)
    except UnsupportedError as exc:
        doc.unsupported = str(exc)
    except ParseError as exc:
        doc.parse_error = str(exc)
    return doc
