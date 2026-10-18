#!/usr/bin/env python3
# taste-lint: ignore file-size, scan, fence check, and fault report share one ratchet entry point.
"""Flag a rule file that cites a non-accepted ADR as binding (issue #5200).

A rule, `AGENTS.md`, or `CLAUDE.md` says "per ADR-078" or "MUST comply with
ADR-080". Nothing checked the cited record's own status. `ADR-078` is
`proposed` and `ADR-080` is `superseded` by ADR-111, yet both are cited as
live authority. A reader who trusts the citation obeys a decision the record
does not hold; a reader who checks the status learns that status is not worth
reading.

## What is scanned

Git-tracked files only, read from disk, per `.claude/rules/ci-scripts.md`
MUST 9. The canonical sources and every shipped mirror of them, because a
check that passes the source while a stale mirror ships the violation to
plugin consumers has not protected the consumer:

- `AGENTS.md` and `CLAUDE.md` at the repository root
- `templates/rules/*.md` (the source, per ADR-109)
- `.claude/rules/*.md`, `src/claude/rules/*.md`
- `.github/instructions/*.instructions.md`, `src/copilot-cli/instructions/*.md`

## Status resolution

Reuses :func:`check_skill_adr_bindings.adr_statuses`, which reads the
frontmatter `status:` through `check_adr_lifecycle.collect_records`, so ADR
parsing keeps one owner. Every `ADR-NNN-*.md` record carries a frontmatter
status since ADR-073 landed, so no prose fallback is needed. A cited number with
no record is the link gate's finding (`check_adr_links.py`) and is counted here,
not failed. A record whose status is empty (missing, unparseable, or non-scalar)
is counted the same way: it is not `accepted`, so its citations are not
skipped as if it were (issue #6506).

`proposed`, `rejected`, `deprecated` and `superseded` are non-accepted. The
issue names the first, second and fourth; `deprecated` is in ADR-073's enum and
a rule cannot cite a deprecated record as live any more than a superseded one.

## Citation classes

Each mention of a non-accepted ADR is placed in exactly one class. Only BINDING
fails the gate. A check that guesses on ambiguous prose trains people to add
ignore comments, so a mention the classifier cannot place is UNCLASSIFIED and is
reported, never failed.

- NOT A CITATION, never seen: inside an inline code span, a fenced block, an
  HTML comment or YAML frontmatter, or part of a file name or path such as
  `ADR-085-slug.md:428-431`.
- META: under a `References` style heading, after a `References:` label,
  or in a lineage clause: "ADR-092, which supersedes ADR-079" (ADR-079 is
  history), "ADR-002, formerly cited here, is deprecated", "superseded by
  ADR-111". The same sentence can hold one binding and one historical
  citation, so the test is on the mention, not the sentence.
- BINDING: the sentence carries MUST, SHALL, REQUIRED, "binding", "governs" or
  "requires", or the mention directly follows "per", "under", "comply with",
  "conform to", "governed by", "required by", "mandated by", "defined by" or
  "according to".
- UNCLASSIFIED: everything else, such as the terse `pins: ADR-080` in
  `AGENTS.md`.

## Not covered

A rule that restates an ADR's decision in prose without naming the ADR, as
`universal.md` MUST-4 does for ADR-093, has no citation to resolve. This check
cannot see it. Naming the ADR in that rule is an owner decision, not a
validator change.

## Ratchet

Violations exist when this gate lands, so a hard gate would red every push. The
baseline lists known violations by identity, `<path>::ADR-NNN`, not by count
(`ci-scripts.md` MUST 15 diffs on `(file, rule)` for the same reason: with a
count, one new violation hides behind one fix). A violation absent from the
baseline fails. A baseline entry the tree no longer produces also fails, so the
list shrinks when a citation is repaired and cannot mask a re-introduction.
Edit the baseline by hand: delete a line when its citation is fixed. Adding a
line legalises a violation and shows in review as an added line.

A scan that cannot see every tracked file does not pass. A tracked file that is
a symlink, a non-regular file, or leaves the repository is listed on stderr and
fails the run with exit 2. A fenced block with no closing fence masks every later
line of its file, so it is listed and fails the run with exit 1 (issue #6506).

Exit codes follow ADR-035: 0 ok, 1 new or stale violation or an unterminated
fence, 2 configuration fault or a tracked file the scan skipped, 3 git could not
list tracked files. Every terminal line carries the
examined count (`ci-scripts.md` MUST 12).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

_REPO_ROOT = _SCRIPT_DIR.parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from check_skill_adr_bindings import adr_statuses  # noqa: E402

from scripts.ci.count_ratchet import tracked_files  # noqa: E402

EXIT_OK = 0
EXIT_REGRESSION = 1
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3

CHECK = "rule-adr-citation"

#: ADR-073 status enum minus `accepted`. See the module docstring.
NON_ACCEPTED = frozenset({"proposed", "rejected", "deprecated", "superseded"})

SCAN_GLOBS = (
    "AGENTS.md",
    "CLAUDE.md",
    "templates/rules/*.md",
    ".claude/rules/*.md",
    "src/claude/rules/*.md",
    ".github/instructions/*.instructions.md",
    "src/copilot-cli/instructions/*.md",
)

BINDING = "binding"
META = "meta"
UNCLASSIFIED = "unclassified"

_BASELINE_PATH = Path(__file__).with_name("rule_adr_citations_baseline.json")

#: An ADR id not preceded by a path separator or word character and not followed
#: by a slug that ends in `.md`, so a file name with a line range is not a mention.
_MENTION_RE = re.compile(r"(?<![/\w-])ADR-(\d{1,4})\b(?![-\w]*\.md)")

_FENCE_RE = re.compile(r"^(```|~~~)[^\n]*\n.*?(?:^\1[^\n]*$|\Z)", re.DOTALL | re.MULTILINE)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
_CODE_SPAN_RE = re.compile(r"(?<!`)(`+)(?!`)[^\n]*?(?<!`)\1(?!`)")

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
_BIB_HEADING_RE = re.compile(
    r"^(?:references?|see also|sources?|bibliography|further reading|related\b.*|prior art)",
    re.IGNORECASE,
)
_BIB_LABEL_RE = re.compile(
    r"^[\s>*_\-]*(?:\d+[.)]\s*)?[*_]*(?:references?|refs?|see also|sources?)[*_]*\s*[:\-]",
    re.IGNORECASE,
)
_BLOCK_START_RE = re.compile(r"^\s*(?:[-*+]\s|\d+[.)]\s|\||>)")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\s*\|\s*|;\s+")

_LINEAGE_WORD = r"(?:supersed\w*|replac\w*|retir\w*|obsolet\w*|deprecat\w*|formerly|previously)"
_LINEAGE_BEFORE_RE = re.compile(
    rf"\b{_LINEAGE_WORD}\s+(?:by\s+)?(?:(?:the|older|prior|earlier|former|old)\s+)?"
    r"(?:ADR-\d+(?:'s)?\s*(?:,|and|or|/)\s*)*$",
    re.IGNORECASE,
)
_LINEAGE_AFTER_RE = re.compile(
    r"^(?:'s)?\W{0,3}(?:\w+\W+){0,2}?(?:is|was|were|are|been|now)?\W*"
    r"(?:formerly|superseded|deprecated|retired|replaced|obsolete|obsoleted|withdrawn)\b",
    re.IGNORECASE,
)
_BINDING_SENTENCE_RE = re.compile(
    r"\b(?:MUST|SHALL|REQUIRED)\b|\b(?:binding|governs|requires)\b",
)
_BINDING_BEFORE_RE = re.compile(
    r"\b(?:per|under|comply with|complies with|conforms? to|governed by|required by|"
    r"mandated by|defined by|according to)\s+(?:the\s+)?(?:ADR-\d+(?:,|\s+and|\s*/)\s*)*$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class Citation:
    """One mention of a non-accepted ADR, placed in a class."""

    path: str
    line: int
    adr: int
    status: str
    kind: str
    sentence: str

    @property
    def key(self) -> str:
        return f"{self.path}::ADR-{self.adr:03d}"

    def render(self) -> str:
        return (
            f"{self.path}:{self.line}: [{CHECK}] ADR-{self.adr:03d} is "
            f"{self.status} but is cited as binding: ...{self.sentence}..."
        )


def unterminated_fence_line(text: str) -> int | None:
    """Line number of the first fence that never closes, or ``None``.

    ``_FENCE_RE`` lets an open fence run to the end of the file so a missing
    close does not crash the scan, but then every later citation is masked.
    Frontmatter is blanked first so a ``---`` block cannot hold a fence.
    """
    body = _FRONTMATTER_RE.sub(_blank, text)
    for match in _FENCE_RE.finditer(body):
        lines = match.group(0).split("\n")
        if len(lines) < 2 or not lines[-1].startswith(match.group(1)):
            return body.count("\n", 0, match.start()) + 1
    return None


def _blank(match: re.Match[str]) -> str:
    """Replace a match with spaces, keeping newlines so line numbers hold."""
    return re.sub(r"[^\n]", " ", match.group(0))


def mask_noise(text: str) -> str:
    """Blank out text that cannot hold a citation, preserving every offset."""
    for pattern in (_FRONTMATTER_RE, _FENCE_RE, _COMMENT_RE, _CODE_SPAN_RE):
        text = pattern.sub(_blank, text)
    return text


def _is_bibliography_heading(title: str) -> bool:
    return bool(_BIB_HEADING_RE.match(title.strip("*_ ")))


def _continues(previous: str, line: str) -> bool:
    """True when ``line`` continues the sentence ``previous`` left open.

    Conservative on purpose: a wrap that starts a capital or ends in terminal
    punctuation starts a new block. A split can only turn a BINDING mention into
    UNCLASSIFIED, never the reverse.
    """
    stripped = line.strip()
    if not stripped or _BLOCK_START_RE.match(line) or stripped[0].isupper() or stripped[0] in "*#":
        return False
    return bool(previous.strip()) and previous.rstrip()[-1] not in ".!?:|"


def _blocks(masked: str) -> list[tuple[bool, list[tuple[int, str]]]]:
    """Split text into blocks of ``(lineno, text)`` lines, tagged bibliography."""
    blocks: list[tuple[bool, list[tuple[int, str]]]] = []
    bib_level = 0
    current: list[tuple[int, str]] = []
    for number, line in enumerate(masked.split("\n"), start=1):
        heading = _HEADING_RE.match(line)
        if heading:
            level = len(heading.group(1))
            if bib_level and level <= bib_level:
                bib_level = 0
            if not bib_level and _is_bibliography_heading(heading.group(2)):
                bib_level = level
            current = []
            continue
        if not line.strip():
            current = []
            continue
        if current and _continues(current[-1][1], line):
            current.append((number, line))
            continue
        current = [(number, line)]
        in_bibliography = bool(bib_level) or bool(_BIB_LABEL_RE.match(line))
        blocks.append((in_bibliography, current))
    return blocks


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    start = 0
    for match in _SENTENCE_SPLIT_RE.finditer(text):
        spans.append((start, match.start()))
        start = match.end()
    spans.append((start, len(text)))
    return spans


def classify(sentence: str, match: re.Match[str], tail_end: int, in_bibliography: bool) -> str:
    """Class of the mention ``match`` found in ``sentence``.

    ``tail_end`` bounds the text after the mention at the next ADR mention, so
    "ADR-092, which supersedes ADR-079" reads ADR-092's tail as ", which
    supersedes" and not as a statement that ADR-092 is retired.
    """
    if in_bibliography:
        return META
    before = sentence[: match.start()]
    after = sentence[match.end() : tail_end]
    if _LINEAGE_BEFORE_RE.search(before) or _LINEAGE_AFTER_RE.match(after):
        return META
    if _BINDING_SENTENCE_RE.search(sentence) or _BINDING_BEFORE_RE.search(before):
        return BINDING
    return UNCLASSIFIED


def _mentions_in_block(
    path: str,
    block: list[tuple[int, str]],
    in_bibliography: bool,
    statuses: dict[int, str],
    unknown: set[int],
) -> list[Citation]:
    text = " ".join(line for _, line in block)
    starts: list[tuple[int, int]] = []
    offset = 0
    for number, line in block:
        starts.append((offset, number))
        offset += len(line) + 1
    found: list[Citation] = []
    for start, end in _sentence_spans(text):
        sentence = text[start:end]
        matches = list(_MENTION_RE.finditer(sentence))
        for index, match in enumerate(matches):
            adr = int(match.group(1))
            status = statuses.get(adr)
            if not status:
                unknown.add(adr)
                continue
            if status not in NON_ACCEPTED:
                continue
            tail_end = matches[index + 1].start() if index + 1 < len(matches) else len(sentence)
            kind = classify(sentence, match, tail_end, in_bibliography)
            absolute = start + match.start()
            lineno = max(n for o, n in starts if o <= absolute)
            found.append(Citation(path, lineno, adr, status, kind, sentence))
    return found


def _excerpt(line: str, adr: int, width: int = 60) -> str:
    """The author's own text around the first mention of ``adr`` on ``line``."""
    match = re.search(rf"ADR-0*{adr}\b", line)
    centre = match.start() if match else 0
    return line[max(0, centre - width) : centre + width].strip()


def citations_in(
    path: str, text: str, statuses: dict[int, str], unknown: set[int]
) -> list[Citation]:
    """Every mention of a non-accepted ADR in ``text``, classified."""
    found: list[Citation] = []
    for in_bibliography, block in _blocks(mask_noise(text)):
        found.extend(_mentions_in_block(path, block, in_bibliography, statuses, unknown))
    # The masked sentence is blanked where code spans were, which reads badly in
    # a report. Show the author's own line instead.
    lines = text.split("\n")
    return [replace(c, sentence=_excerpt(lines[c.line - 1], c.adr)) for c in found]


@dataclass(frozen=True, slots=True)
class ScanResult:
    citations: list[Citation]
    candidates: int
    examined: int
    absent: list[str]
    unknown: set[int]
    unterminated: list[str] = field(default_factory=list)

    @property
    def binding(self) -> list[Citation]:
        return [c for c in self.citations if c.kind == BINDING]

    @property
    def unclassified(self) -> list[Citation]:
        return [c for c in self.citations if c.kind == UNCLASSIFIED]


def _readable(repo_root: Path, rel: str) -> Path | None:
    """The tracked file's path when it is a regular file inside the repository."""
    path = repo_root / rel
    try:
        inside = path.resolve().is_relative_to(repo_root.resolve())
    except OSError:
        return None
    return path if inside and path.is_file() else None


def scan(repo_root: Path, statuses: dict[int, str]) -> ScanResult | str:
    """Classify every non-accepted citation in the tracked scan set.

    Returns the fault reason when git could not list the files, so a gate that
    enumerated nothing never reports an empty findings list as a clean tree.
    """
    relatives = tracked_files(repo_root, SCAN_GLOBS)
    if relatives is None:
        return (
            f"git could not list tracked rule files under {repo_root}, so nothing "
            "was examined and the gate did not run"
        )
    citations: list[Citation] = []
    absent: list[str] = []
    unterminated: list[str] = []
    unknown: set[int] = set()
    for rel in sorted(relatives):
        path = _readable(repo_root, rel)
        if path is None:
            absent.append(rel)
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        fence_line = unterminated_fence_line(text)
        if fence_line is not None:
            unterminated.append(f"{rel}:{fence_line}")
        citations.extend(citations_in(rel, text, statuses, unknown))
    return ScanResult(
        citations, len(relatives), len(relatives) - len(absent), absent, unknown, unterminated
    )


def read_baseline(path: Path) -> set[str] | str:
    """Known-violation keys, or a one-line reason the file cannot be used."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        return f"baseline {path} could not be read: {exc}"
    except json.JSONDecodeError as exc:
        return f"baseline {path} is not valid JSON: {exc}"
    known = payload.get("known") if isinstance(payload, dict) else None
    if not isinstance(known, list) or not all(isinstance(item, str) for item in known):
        return f"baseline {path} has no `known` list of strings"
    return set(known)


def _config_fault(adr_dir: Path, statuses: dict[int, str]) -> str | None:
    if not adr_dir.is_dir():
        return f"ADR directory {adr_dir} does not exist, so no status could be resolved"
    if not statuses:
        return f"no ADR records found under {adr_dir}, so every citation would resolve to nothing"
    return None


def _report(result: ScanResult, new: list[str], stale: list[str], verbose: bool) -> None:
    for citation in result.binding:
        if citation.key in new:
            print(citation.render())
    for key in stale:
        print(
            f"{key}: [{CHECK}] baseline entry no longer produced by the tree. "
            "Delete the line from the baseline."
        )
    if verbose:
        for citation in result.unclassified:
            print(f"{citation.path}:{citation.line}: [{CHECK}] unclassified ADR-{citation.adr:03d}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Flag a rule file citing a non-accepted ADR as binding (issue #5200)."
    )
    parser.add_argument("--repo-root", default=".", help="Repository root to scan.")
    parser.add_argument("--baseline", default=str(_BASELINE_PATH), help="Known-violation list.")
    parser.add_argument("--verbose", action="store_true", help="List unclassified mentions.")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    adr_dir = repo_root / ".project-toolkit" / "architecture"
    statuses = adr_statuses(repo_root, adr_dir) if adr_dir.is_dir() else {}
    fault = _config_fault(adr_dir, statuses)
    baseline = read_baseline(Path(args.baseline)) if fault is None else fault
    if isinstance(baseline, str):
        print(f"[{CHECK}] config: {baseline}", file=sys.stderr)
        return EXIT_CONFIG

    result = scan(repo_root, statuses)
    if isinstance(result, str):
        print(f"[{CHECK}] external: {result}", file=sys.stderr)
        return EXIT_EXTERNAL
    if not result.examined:
        print(
            f"[{CHECK}] config: examined 0 of {result.candidates} tracked rule file(s), "
            "so this run measured nothing",
            file=sys.stderr,
        )
        return EXIT_CONFIG

    if result.absent:
        for rel in result.absent:
            print(
                f"{rel}: [{CHECK}] tracked file is not a regular file inside the repository, "
                "so it was not scanned",
                file=sys.stderr,
            )
        print(
            f"[{CHECK}] config: skipped {len(result.absent)} of {result.candidates} "
            "tracked rule file(s); a gate that cannot see every file has not passed.",
            file=sys.stderr,
        )
        return EXIT_CONFIG

    current = {c.key for c in result.binding}
    new = sorted(current - baseline)
    stale = sorted(baseline - current)
    _report(result, new, stale, args.verbose)
    for location in result.unterminated:
        print(
            f"{location}: [{CHECK}] code fence is never closed, so every later line of "
            "the file is masked and its citations went unchecked.",
            file=sys.stderr,
        )
    scope = (
        f"{len(current)} binding violation(s) ({len(baseline)} known), "
        f"{len(result.unclassified)} unclassified, across "
        f"{result.examined} of {result.candidates} tracked rule file(s), "
        f"{len(result.unknown)} ADR number(s) with no usable status"
    )
    if new or stale or result.unterminated:
        print(
            f"[{CHECK}] REGRESSION: {len(new)} new, {len(stale)} stale, "
            f"{len(result.unterminated)} unterminated fence(s); {scope}.",
            file=sys.stderr,
        )
        return EXIT_REGRESSION
    print(f"[{CHECK}] at baseline: {scope}.")
    return EXIT_OK


def validate_rule_adr_citations(repo_root: Path) -> bool:
    """Pre-PR gate adapter: True only when the run completed with no new or stale entry.

    A configuration fault (exit 2) and an external fault (exit 3) return False.
    A gate that could not run has not passed.
    """
    return main(["--repo-root", str(repo_root)]) == EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
