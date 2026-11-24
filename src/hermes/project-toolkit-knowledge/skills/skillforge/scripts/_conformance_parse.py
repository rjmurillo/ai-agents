"""Read a skill directory into the shape the conformance checks need.

The frontmatter parser here is deliberately small and standard-library only.
It never uses PyYAML, so a verdict does not depend on what is installed. It
reads block mappings, block sequences, plain and quoted scalars, and literal
or folded block scalars. Anything else (anchors, aliases, tags, complex flow
collections) raises UnsupportedError, and the checks that need typed values then
report NOT_EVALUATED instead of guessing.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from _path_guard import contained_realpath, is_within, resolve_root

# ADR-047 keeps this bootstrap inline because imports need sys.path first.
# This file's own plugin lib wins when it holds the shared frontmatter parser,
# so a foreign or older plugin root in the environment cannot shadow it. The
# environment root is the fallback for a script copied outside its plugin.
_PLUGIN_ROOT = os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT")
_LIB_DIR = Path(__file__).resolve().parents[3] / "lib"
if _PLUGIN_ROOT and not os.path.isfile(_LIB_DIR / "hook_utilities" / "frontmatter_block.py"):
    _LIB_DIR = Path(_PLUGIN_ROOT) / "lib"

if not os.path.isdir(_LIB_DIR):
    raise RuntimeError(
        "Expected portability helper lib directory not found: "
        f"{_LIB_DIR}. Set COPILOT_PLUGIN_ROOT or CLAUDE_PLUGIN_ROOT to the "
        "plugin root, or run from an ai-agents checkout."
    )
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from hook_utilities import frontmatter_block  # noqa: E402

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
    root: Path | None = None
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
    return Scalar(_plain_text(_strip_comment(text), line_no), plain=True)


def _plain_text(text: str, line_no: int) -> str:
    """Reject a plain scalar that YAML would read as a nested mapping."""
    if ": " in text or text.endswith(":"):
        raise ParseError(f"line {line_no}: ': ' in an unquoted value; quote the whole value")
    return text


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
    text = "\n".join(body) if style == "|" else _fold(body)
    if chomp == "-":
        return Scalar(text), i
    return Scalar(text + "\n"), i


def _fold(body: list[str]) -> str:
    """Fold block lines the way YAML's '>' style does.

    A break between two normal lines becomes a space. Blank lines between them
    become one newline each, and the break itself is dropped. A break next to a
    more-indented line is kept, so that line's layout survives.
    """
    text = ""
    previous: str | None = None
    blanks = 0
    for line in body:
        if not line:
            blanks += 1
            continue
        kind = "more" if line[0] in " \t" else "text"
        if previous is None:
            text += "\n" * blanks
        elif previous == "text" and kind == "text":
            text += "\n" * blanks if blanks else " "
        else:
            text += "\n" * (blanks + 1)
        text += line
        previous, blanks = kind, 0
    return text


def _plain_continuation(
    lines: list[str], start: int, parent_indent: int, first: str
) -> tuple[object, int]:
    parts = [first]
    i = start
    while i < len(lines) and lines[i].strip() and _indent(lines[i]) > parent_indent:
        if lines[i].strip().startswith("#"):
            break
        parts.append(_plain_text(_strip_comment(lines[i].strip()), i + 1))
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
    """Return (frontmatter, body, error). Frontmatter is None when absent.

    The fence rule is ``hook_utilities.frontmatter_block.split_frontmatter``.
    This module stays PyYAML-free, so only the block's text is read from the
    core and ``parse_frontmatter`` below interprets it.
    """
    text = text.lstrip("\ufeff").replace("\r\n", "\n")
    split = frontmatter_block.split_frontmatter(text)
    if split.status is frontmatter_block.FrontmatterStatus.ABSENT:
        return None, text, "SKILL.md does not start with a '---' line"
    if not split.found:
        return None, text, "the frontmatter has no closing '---' line"
    # The core's raw text runs from the opening fence's newline through the
    # closing fence's preceding newline. Drop both so line numbers in parse
    # errors count from the first line after the fence.
    raw = split.raw.removeprefix("\n").removesuffix("\n")
    return raw, split.body, None


def contained(doc: SkillDoc, path: Path) -> bool:
    """True when path resolves inside the root the caller trusts."""
    root = doc.root if doc.root is not None else doc.directory
    return contained_realpath(path, resolve_root(str(root))) is not None


def load_skill(directory: Path, root: Path | None = None) -> SkillDoc:
    """Read SKILL.md from a skill directory and parse what the checks need.

    Every file read stays inside root, which defaults to the skill directory.
    The file name must match exactly, so a case-insensitive filesystem cannot
    pass skill.md off as SKILL.md.
    """
    doc = SkillDoc(directory=directory, root=root)
    try:
        names = set(os.listdir(directory))
    except OSError as exc:
        doc.frontmatter_error = f"cannot list the skill directory: {exc}"
        return doc
    for name in ("SKILL.md", "skill.md"):
        if name in names and (directory / name).is_file():
            doc.skill_md = directory / name
            break
    if doc.skill_md is None:
        return doc
    if not contained(doc, doc.skill_md):
        doc.frontmatter_error = f"{doc.skill_md.name} resolves outside the root; not read"
        return doc
    try:
        doc.text = doc.skill_md.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        doc.frontmatter_error = f"cannot read {doc.skill_md.name} as UTF-8: {exc}"
        return doc
    parse_doc_text(doc)
    return doc


def parse_doc_text(doc: SkillDoc) -> None:
    """Split and parse doc.text, filling body, fields, and the error fields.

    Shared by `load_skill` and callers that hold SKILL.md text not on disk.
    """
    raw, doc.body, doc.frontmatter_error = split_frontmatter(doc.text)
    if raw is None:
        return
    doc.has_frontmatter = True
    try:
        doc.fields = parse_frontmatter(raw)
    except UnsupportedError as exc:
        doc.unsupported = str(exc)
    except ParseError as exc:
        doc.parse_error = str(exc)


def file_id(path: Path) -> tuple[int, int] | None:
    """Return the (device, inode) of the file a path reaches, or None when it cannot be read.

    Comparing file identity, not path text, also catches a hard link or a
    second symlink to the same file.
    """
    try:
        info = os.stat(path)
    except (OSError, RuntimeError, ValueError):
        return None
    return info.st_dev, info.st_ino


def _real(path: Path) -> str | None:
    """Return the case-normalized real path, or None when it cannot be resolved.

    A symlink loop raises on some Python versions; treating it as unresolvable
    keeps the judgments import on its exit-2 path instead of a traceback.
    """
    try:
        return os.path.normcase(os.path.realpath(path))
    except (OSError, RuntimeError, ValueError):
        return None


def inside_skill(path: Path, directory: Path, root: Path) -> bool:
    """True when path resolves to a file inside both the skill directory and root.

    resolved_identity owns the boundary rule. is_file raises on a directory the
    process can list but not enter on Python 3.10 to 3.13; that file is left out.
    """
    try:
        if not path.is_file():
            return False
    except OSError:
        return False
    return resolved_identity(path, directory, root) is not None


def resolved_identity(path: Path, directory: Path, root: Path) -> tuple[int, int] | None:
    """Resolve path once; return its (device, inode) only if it lies inside both boundaries.

    Containment and identity come from the same resolution, and lstat does not
    follow a final symlink, so a path swapped after resolving cannot pass.
    """
    real = _real(path)
    if real is None:
        return None
    if not is_within(real, resolve_root(str(root))):
        return None
    if not is_within(real, resolve_root(str(directory))):
        return None
    try:
        info = os.lstat(real)
    except OSError:
        return None
    return info.st_dev, info.st_ino
