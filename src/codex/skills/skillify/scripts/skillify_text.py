"""Text parsing shared by the skillify helpers.

Frontmatter, markdown sections, list counting, and tokenizing. Stdlib only.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
KEY_RE = re.compile(r"^([A-Za-z0-9_-]+):\s*(.*)$")
BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+\S")
SEPARATOR_RE = re.compile(r"^\s*\|[\s:|-]+\|?\s*$")
NUMBERED_RE = re.compile(r"^ {0,3}(\d+)[.)]\s+\S")
FENCE_OPEN_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
FENCE_CLOSE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})[ \t]*$")
UNDERLINE_RE = re.compile(r"^ {0,3}(=+|-+)[ \t]*$")
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
INLINE_CODE_RE = re.compile(r"(`+)[^`]*?\1")
BOM = "\ufeff"
TOKEN_RE = re.compile(r"[a-z0-9]+")

# Generic words are dropped so a broad skill cannot reach PATCH on them alone;
# the cost is that a workflow made only of such words has too few terms to judge.
STOPWORDS = frozenset(
    "a an and are as at be but by do does for from has have how in into is it its "
    "not of on or our that the their then this to use used using was when which "
    "will with you your skill skills file files write run verify check".split()
)


# Sections the skeleton (references/skill-skeleton.md, "Body sections") defines as
# descriptive rather than instructive: Triggers, Contract, Anti-patterns,
# Pitfalls, Verification. The framing paragraph sits under the level-1 title.
DESCRIPTIVE_SECTIONS = ("triggers", "contract", "anti-patterns", "pitfalls", "verification")

MARKER = "marker"
CONTENT = "content"
TEXT = "text"


class SkillifyError(Exception):
    """Input the helper cannot act on. Maps to exit code 1."""


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Split YAML-ish frontmatter into top-level string values and the body.

    Reads top-level keys with scalar, folded, literal, or quoted values.
    Indented lines under a key, including a nested map, are appended to that
    key's value as plain text. No nested structure is parsed.
    """
    lines = text.lstrip(BOM).splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, "\n".join(lines)
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return {}, "\n".join(lines)
    return _top_level_values(lines[1:end]), "\n".join(lines[end + 1 :])


def _top_level_values(lines: Sequence[str]) -> dict[str, str]:
    parts: dict[str, list[str]] = {}
    current: str | None = None
    for line in lines:
        match = KEY_RE.match(line)
        if match:
            current = match.group(1)
            parts[current] = [match.group(2)]
        elif current is not None and line.strip():
            parts[current].append(line.strip())
    return {key: _clean_scalar(value) for key, value in parts.items()}


def _clean_scalar(parts: Sequence[str]) -> str:
    first = parts[0].strip()
    if first[:1] in {">", "|"}:
        first = ""
    joined = " ".join(p for p in [first, *parts[1:]] if p).strip()
    if len(joined) >= 2 and joined[0] == joined[-1] and joined[0] in {'"', "'"}:
        quote = joined[0]
        joined = joined[1:-1]
        if quote == '"':
            joined = joined.replace('\\"', '"')
    return joined


class FenceTracker:
    """CommonMark-basics fence state, shared by every scan in this module.

    A fence opens on 3 or more backticks or tildes indented under 4 columns. A
    backtick fence whose info string holds a backtick is inline code, not a
    fence. It closes only on a run of the same character, at least as long,
    with no info string. Tabs count as 4 columns.
    """

    def __init__(self) -> None:
        self._opening = ""

    def feed(self, line: str) -> str:
        """Classify `line` as MARKER (opens or closes a fence), CONTENT, or TEXT."""
        expanded = line.expandtabs(4)
        return self._inside(expanded) if self._opening else self._outside(expanded)

    def _inside(self, line: str) -> str:
        match = FENCE_CLOSE_RE.match(line)
        if (
            match
            and match.group(1)[0] == self._opening[0]
            and len(match.group(1)) >= len(self._opening)
        ):
            self._opening = ""
            return MARKER
        return CONTENT

    def _outside(self, line: str) -> str:
        match = FENCE_OPEN_RE.match(line)
        if not match:
            return TEXT
        run, info = match.groups()
        if run[0] == "`" and "`" in info:
            return TEXT
        self._opening = run
        return MARKER


def line_kinds(lines: Sequence[str]) -> list[str]:
    """Classify every line with one FenceTracker pass."""
    tracker = FenceTracker()
    return [tracker.feed(line) for line in lines]


def indent_of(line: str) -> int:
    """Leading columns of `line`, tabs counted as 4."""
    expanded = line.expandtabs(4)
    return len(expanded) - len(expanded.lstrip(" "))


@dataclass(frozen=True)
class Section:
    """A markdown section: its normalized name and the lines under it."""

    name: str
    lines: tuple[str, ...]


Heading = tuple[int, int, str, int]  # line index, level, title, first content line


def split_sections(body: str) -> list[Section]:
    """Return every heading with its content.

    Headings are ATX (`## Title`) or single-line setext (a line over `===` or
    `---`). Lines inside fences are never headings.
    """
    lines = body.splitlines()
    headings = heading_spans(lines, line_kinds(lines))
    return [_section_at(lines, headings, n) for n in range(len(headings))]


def heading_spans(lines: Sequence[str], kinds: Sequence[str]) -> list[Heading]:
    """Find ATX and setext headings outside fences, in document order."""
    found: list[Heading] = []
    for index, line in enumerate(lines):
        if kinds[index] != TEXT:
            continue
        atx = HEADING_RE.match(line)
        if atx:
            found.append((index, len(atx.group(1)), atx.group(2), index + 1))
            continue
        level = _setext_level(lines, kinds, index)
        if level:
            found.append((index, level, line.strip(), index + 2))
    return found


def _setext_level(lines: Sequence[str], kinds: Sequence[str], index: int) -> int:
    """Return 1 or 2 when `lines[index]` is a single-line setext title, else 0.

    The title follows a blank line (or starts the body), is plain paragraph
    text, and sits directly above `===` or `---`. A `---` after a blank line
    is a rule, not a heading, because its own line cannot be a title.
    """
    line = lines[index]
    if index + 1 >= len(lines) or kinds[index + 1] != TEXT or indent_of(line) >= 4:
        return 0
    if index > 0 and lines[index - 1].strip():
        return 0
    if not line.strip() or UNDERLINE_RE.match(line) or line.lstrip().startswith(("#", ">", "|")):
        return 0
    if BULLET_RE.match(line):
        return 0
    under = UNDERLINE_RE.match(lines[index + 1])
    if not under:
        return 0
    return 1 if under.group(1)[0] == "=" else 2


def _section_at(lines: Sequence[str], headings: Sequence[Heading], n: int) -> Section:
    index, level, title, start = headings[n]
    end = len(lines)
    for later_index, later_level, _, _ in headings[n + 1 :]:
        if later_level <= level:
            end = later_index
            break
    return Section(normalize_heading(title), tuple(lines[start:end]))


def first_sections(body: str) -> dict[str, Section]:
    """Map section name to its first occurrence; a repeated heading is ignored."""
    found: dict[str, Section] = {}
    for section in split_sections(body):
        found.setdefault(section.name, section)
    return found


def procedure_section(sections: Mapping[str, Section], allow_process: bool) -> Section | None:
    """Pick the section that holds a skill's steps.

    `procedure` wins. With `allow_process`, fall back to the first section
    whose slug is `process` or starts with `process-` (document order), since
    host skills mostly use `## Process`.
    """
    if "procedure" in sections:
        return sections["procedure"]
    if not allow_process:
        return None
    return next(
        (sec for name, sec in sections.items() if name == "process" or name.startswith("process-")),
        None,
    )


@dataclass(frozen=True)
class Step:
    """One numbered step: its numeral, its prose, and the code under it.

    `fenced` holds fenced text, multi-line HTML comments, and indented code,
    none of which can carry an `(approval)` tag but all of which the backstop reads.
    """

    number: int
    text: str
    fenced: str

    @property
    def full(self) -> str:
        return f"{self.text} {self.fenced}".strip()


@dataclass(frozen=True)
class ParsedSteps:
    """Numbered steps plus lines in the section that belong to no step."""

    steps: tuple[Step, ...]
    loose: tuple[str, ...]


class _StepParser:
    """Single pass over a step section.

    Code (fences, multi-line HTML comments, indented code after a blank line)
    stays with the step above it and never starts a step. A line after a blank
    line that is neither numbered nor indented detaches from the step and, with
    every line up to the next numbered step, is loose.
    """

    def __init__(self) -> None:
        self.numbers: list[int] = []
        self.texts: list[str] = []
        self.code: list[list[str]] = []
        self.loose: list[str] = []
        self._fence = FenceTracker()
        self._comment = False
        self._gap = False
        self._detached = False

    def feed(self, line: str) -> None:
        stripped = line.strip()
        kind = self._fence.feed(line)
        if kind == MARKER:
            return
        if kind == CONTENT:
            self._code_line(stripped)
        elif not stripped:
            self._gap = True
        elif self._comment:
            self._comment = "-->" not in line
            self._code_line(stripped)
        else:
            self._text_line(line, stripped)

    def _owned(self) -> bool:
        return bool(self.texts) and not self._detached

    def _code_line(self, stripped: str) -> None:
        if self._owned():
            self.code[-1].append(stripped)
        else:
            self.loose.append(stripped)

    def _text_line(self, line: str, stripped: str) -> None:
        numbered = NUMBERED_RE.match(line)
        if numbered:
            self._new_step(int(numbered.group(1)), stripped)
        else:
            self._prose_line(line, stripped)
        opened = line.rfind("<!--")
        self._comment = opened != -1 and "-->" not in line[opened:]

    def _new_step(self, number: int, stripped: str) -> None:
        self.numbers.append(number)
        self.texts.append(stripped)
        self.code.append([])
        self._gap = False
        self._detached = False

    def _prose_line(self, line: str, stripped: str) -> None:
        if not self._owned():
            self._detached = True
            self.loose.append(stripped)
        elif self._gap and indent_of(line) >= 4:
            self.code[-1].append(stripped)
        elif self._gap and indent_of(line) == 0:
            self._detached = True
            self.loose.append(stripped)
        else:
            self.texts[-1] = f"{self.texts[-1]} {stripped}"
            self._gap = False


def parse_steps(lines: Sequence[str]) -> ParsedSteps:
    """Split a step section into numbered steps and loose lines."""
    parser = _StepParser()
    for line in lines:
        parser.feed(line)
    steps = tuple(
        Step(n, t, " ".join(c))
        for n, t, c in zip(parser.numbers, parser.texts, parser.code, strict=True)
    )
    return ParsedSteps(steps, tuple(parser.loose))


def approval_prose(text: str) -> str:
    """Step prose with HTML comments and inline code spans removed."""
    return INLINE_CODE_RE.sub("", HTML_COMMENT_RE.sub("", text))


def outside_step_lines(body: str, allow_process: bool) -> list[str]:
    """Instruction lines that sit outside the one step section.

    Skips fenced code, frontmatter (already stripped from `body`), the
    framing text under the title, and the descriptive sections. Lines in the
    step section belong to `parse_steps`, not here.
    """
    lines = body.splitlines()
    kinds = line_kinds(lines)
    heads = heading_spans(lines, kinds)
    chosen = _chosen_heading(heads, allow_process)
    at = {head[0]: n for n, head in enumerate(heads)}
    stack: list[tuple[int, int, str]] = []
    stray: list[str] = []
    for index, line in enumerate(lines):
        if index in at:
            n = at[index]
            while stack and stack[-1][1] >= heads[n][1]:
                stack.pop()
            stack.append((n, heads[n][1], normalize_heading(heads[n][2])))
        if kinds[index] == TEXT and line.strip() and _scanned(stack, chosen):
            stray.append(line.strip())
    return stray


def _chosen_heading(heads: Sequence[Heading], allow_process: bool) -> int | None:
    names = [normalize_heading(head[2]) for head in heads]
    if "procedure" in names:
        return names.index("procedure")
    if not allow_process:
        return None
    return next(
        (n for n, name in enumerate(names) if name == "process" or name.startswith("process-")),
        None,
    )


def _scanned(stack: Sequence[tuple[int, int, str]], chosen: int | None) -> bool:
    if not stack or stack[-1][1] == 1:
        return False
    if any(name in DESCRIPTIVE_SECTIONS for _, _, name in stack):
        return False
    return not any(n == chosen for n, _, _ in stack)


def step_section_count(sections: Sequence[Section], allow_process: bool) -> int:
    """Count sections that could hold the steps: `procedure`, else the Process family."""
    names = [section.name for section in sections]
    if "procedure" in names or not allow_process:
        return names.count("procedure")
    return sum(1 for name in names if name == "process" or name.startswith("process-"))


def normalize_heading(title: str) -> str:
    """Lowercase, drop punctuation, and join words with `-`: `Anti-Patterns` -> `anti-patterns`."""
    return "-".join(TOKEN_RE.findall(title.lower()))


def count_items(lines: Sequence[str]) -> int:
    """Count bullets, numbered items, and table data rows outside code fences."""
    count = 0
    table: list[str] = []
    kinds = line_kinds(lines)
    for line, kind in zip([*lines, ""], [*kinds, TEXT], strict=True):
        if kind != TEXT:
            continue
        if line.lstrip().startswith("|"):
            table.append(line)
            continue
        count += _table_rows(table)
        table = []
        if BULLET_RE.match(line):
            count += 1
    return count


def _table_rows(table: Sequence[str]) -> int:
    if not table:
        return 0
    has_header = any(SEPARATOR_RE.match(row) for row in table)
    data = [row for row in table if not SEPARATOR_RE.match(row)]
    return len(data) - (1 if has_header else 0)


def tokenize(text: str) -> frozenset[str]:
    """Lowercase word tokens, minus stop words, with one trailing `s` folded off."""
    tokens = set()
    for raw in TOKEN_RE.findall(text.lower()):
        if raw in STOPWORDS or len(raw) < 3:
            continue
        tokens.add(_fold_plural(raw))
    return frozenset(tokens)


def _fold_plural(word: str) -> str:
    """Drop one trailing `s` from a plural, keeping `status`, `process`, `analysis`."""
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word
