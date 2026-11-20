#!/usr/bin/env python3
"""Flag a live ADR that cites a superseded ADR as current authority.

ADR-107 line 710 said "ADR-080 (model pin justification policy): owns
`model:` on any authored artifact." ADR-111 had already superseded ADR-080, so
the record named a retired decision as the current owner of a policy. The
sibling gates resolve citations in rule files (`check_rule_adr_citations.py`)
and in `SKILL.md` `metadata.adr` (`check_skill_adr_bindings.py`). Neither reads
an ADR body. This gate does.

## What is scanned

Git-tracked `.project-toolkit/architecture/ADR-NNN-*.md` records whose own
status is `accepted` or `proposed`; a retired record is history as a whole.
Only mentions of a `superseded` record are classified: a `deprecated` or
`rejected` target has no successor to cite instead.

## Why the rule gate's classifier is not reused as is

The rule gate treats everything under a `Related ...` heading as bibliography.
The ADR-107 bullet that prompted this gate sits under a Related Decisions
heading, so that gate returns META for it. The divergence is pinned in
`tests/validation/test_check_adr_supersession_citations.py`. The masking,
block, sentence, mention and lineage helpers come from the rule gate, so both
gates parse prose one way.

## Citation classes

Each mention of a superseded ADR lands in exactly one class. Only AUTHORITY
fails the gate. A mention the classifier cannot place is UNCLASSIFIED and is
counted, never failed.

- NOT A CITATION, never seen: in a fenced block, an HTML comment, the
  frontmatter, an inline code span, or a file name such as
  `ADR-080-model-pin-justification-policy.md`.
- HISTORY: the cited record is in this record's own `supersedes` list; the
  mention sits inside double quotes; a lineage clause wraps it ("superseded by
  ADR-111", "which supersedes ADR-080"); the sentence names a successor of the
  cited record anywhere in its `superseded-by` chain; the sentence says
  history, historical, precedent, lineage, originally, formerly, previously,
  no longer, at the time, or used to (not after is, are or be), or a past-tense
  "was", "were" or "had been" before governed, owned, defined, required or
  mandated; or "not" or "never" (optionally plus governed, owned, defined,
  required or bound) plus from, by, under, per, cite, follow, use or rely on
  precedes the mention, alone or in a list joined by commas, or, and.
- AUTHORITY: the sentence carries MUST, SHALL or REQUIRED, or one of governs,
  governing, governed by, owns, owned by, current owner, owner of, binding,
  authority, in force or requires; or the mention follows a binding phrase
  the rule gate's `BINDING_BEFORE_RE` lists ("per", "under", "comply with").
- UNCLASSIFIED: everything else. HISTORY wins when a sentence carries both.

## Not covered

- A table cell is its own sentence (the splitter cuts on `|`), so a row
  classifies only when the cell that names the ADR also carries the signal.
- An UNCLASSIFIED mention never fails. A blind read of all 131 at `31a65de8e`
  (2026-11-20) judged 25 of them live authority, so recall is partial.
- A stray straight `"` (an inch mark) earlier in a paragraph reads later
  mentions as quoted, so they pass as HISTORY.

## Ratchet

The baseline keys known violations by identity, `<path>::ADR-NNN`, like the rule
gate, so a second citation in a baselined record passes. New or stale entries
fail. A PR that supersedes an ADR must repoint live citers or add them here.

Exit codes follow ADR-035: 0 ok, 1 new or stale violation or an unterminated
fence, 2 configuration fault or a tracked record the scan could not read, 3 git
could not list tracked files. Every terminal line carries the examined count.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

_REPO_ROOT = _SCRIPT_DIR.parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# The rule gate owns prose parsing for ADR citations; it exports these names so
# both gates parse prose one way.
from check_adr_lifecycle import Record, collect_records  # noqa: E402
from check_rule_adr_citations import (  # noqa: E402
    BINDING_BEFORE_RE,
    CODE_SPAN_RE,
    COMMENT_RE,
    FENCE_RE,
    FRONTMATTER_RE,
    LINEAGE_AFTER_RE,
    LINEAGE_BEFORE_RE,
    MENTION_RE,
    blank,
    blocks,
    read_baseline,
    readable,
    sentence_spans,
    unterminated_fence_line,
)

from scripts.ci.count_ratchet import tracked_files  # noqa: E402

EXIT_OK = 0
EXIT_REGRESSION = 1
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3

CHECK = "adr-supersession-citation"

ADR_DIR = ".project-toolkit/architecture"
LIVE = frozenset({"accepted", "proposed"})
SUPERSEDED = "superseded"

AUTHORITY = "authority"
HISTORY = "history"
UNCLASSIFIED = "unclassified"

_BASELINE_PATH = Path(__file__).with_name("adr_supersession_citations_baseline.json")

_ADR_ID_RE = re.compile(r"(?:ADR-)?0*(\d{1,4})\b")
_AUTHORITY_CASED_RE = re.compile(r"\b(?:MUST|SHALL|REQUIRED)\b")
_AUTHORITY_RE = re.compile(
    r"\b(?:governs|governing|governed by|owns|owned by|current owner|owner of|binding|"
    r"authority|in force|requires)\b",
    re.IGNORECASE,
)
_HISTORY_RE = re.compile(
    r"\b(?:histor(?:y|ical|ically)|precedent|lineage|originally|formerly|"
    r"previously|no longer|at the time|(?<!\bis )(?<!\bare )(?<!\bbe )used to|"
    r"(?:was|were|had been)\s+(?:governed|owned|defined|required|mandated))\b",
    re.IGNORECASE,
)
_NEGATED_BEFORE_RE = re.compile(
    r"\b(?:not|never)\s+(?:(?:governed|owned|defined|required|bound)\s+)?"
    r"(?:from|by|under|per|cite|follow|use|rely on)\s+"
    r"(?:ADR-\d+,?\s+(?:(?:or|and)\s+)?)*$",  # one owner per space: linear time
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class Citation:
    """One mention of a superseded ADR inside a live ADR, placed in a class."""

    path: str
    line: int
    adr: int
    kind: str
    excerpt: str

    @property
    def key(self) -> str:
        return f"{self.path}::ADR-{self.adr:03d}"

    def render(self, successor: int | None) -> str:
        repoint = f"; cite ADR-{successor:03d} instead" if successor else ""
        return (
            f"{self.path}:{self.line}: [{CHECK}] ADR-{self.adr:03d} is superseded "
            f"but is cited as current authority{repoint}: ...{self.excerpt}..."
        )


@dataclass(frozen=True, slots=True)
class Corpus:
    """Status and supersession edges for every ADR record that parsed."""

    status: dict[int, str]
    supersedes: dict[int, frozenset[int]]
    successor: dict[int, int]

    def chain(self, adr: int) -> list[int]:
        """Records that replaced ``adr``, nearest first; stops at a cycle."""
        found: list[int] = []
        current = self.successor.get(adr)
        while current is not None and current not in found:
            found.append(current)
            current = self.successor.get(current)
        return found

    def terminal_successor(self, adr: int) -> int | None:
        """The last record in ``adr``'s chain, the one a citation should name."""
        chain = self.chain(adr)
        return chain[-1] if chain else None


def _ids(value: object) -> frozenset[int]:
    """ADR numbers named by a frontmatter value: a list, one string, or null."""
    items = value if isinstance(value, list) else [value]
    return frozenset(
        int(m.group(1))
        for item in items
        if item is not None
        for m in _ADR_ID_RE.finditer(str(item))
    )


def build_corpus(records: list[Record]) -> Corpus:
    """Status and edges from frontmatter; successors from `superseded-by` and
    from another record's `supersedes`, so a one-sided edge still counts."""
    status: dict[int, str] = {}
    supersedes: dict[int, frozenset[int]] = {}
    successor: dict[int, int] = {}
    for record in records:
        meta = record.frontmatter if isinstance(record.frontmatter, dict) else {}
        raw = meta.get("status")
        status[record.number] = (
            "" if raw is None or isinstance(raw, (list, dict)) else str(raw).strip().lower()
        )
        supersedes[record.number] = _ids(meta.get("supersedes"))
        for target in sorted(_ids(meta.get("superseded-by"))):
            successor.setdefault(record.number, target)
    for number, replaced in supersedes.items():
        for old in replaced:
            successor.setdefault(old, number)
    return Corpus(status, supersedes, successor)


def _soften_code_span(match: re.Match[str]) -> str:
    """Keep a code span's words (`superseded` is lineage), drop its delimiters,
    quotes and ADR ids: an id inside a span is still not a citation."""
    text = match.group(0).replace("`", " ").replace('"', " ")
    return re.sub(r"ADR-", "ADR_", text)


def mask_non_citations(text: str) -> str:
    """Blank what cannot hold a citation, preserving every offset."""
    for pattern in (FRONTMATTER_RE, FENCE_RE, COMMENT_RE):
        text = pattern.sub(blank, text)
    # The shared patterns import untyped, so pin the result type here.
    masked: str = CODE_SPAN_RE.sub(_soften_code_span, text)
    return masked


def _quote_depth(text: str) -> int:
    """Open double quotes in ``text``: straight quotes by parity, curly by balance."""
    return text.count('"') % 2 + max(0, text.count("“") - text.count("”"))


def _paragraph_prefixes(masked: str) -> list[str]:
    """For each line (index 0 is line 1), the paragraph text above it.

    Quote state is counted over the paragraph, not the block or the sentence:
    the shared block splitter starts a new block at a capitalised wrap, and the
    sentence splitter cuts on `.`, so either can split one quotation in two.
    """
    prefixes: list[str] = []
    paragraph = ""
    for line in masked.split("\n"):
        if not line.strip():
            paragraph = ""
        prefixes.append(paragraph)
        paragraph += line + "\n"
    return prefixes


def _names_successor(sentence: str, successors: list[int]) -> bool:
    return any(re.search(rf"(?<![/\w-])ADR-0*{n}\b", sentence) for n in successors)


@dataclass(frozen=True, slots=True)
class ClassifyContext:
    """Facts about a mention that its sentence alone does not carry."""

    corpus: Corpus
    own_supersedes: frozenset[int]
    quoted: bool


def classify(sentence: str, match: re.Match[str], tail_end: int, context: ClassifyContext) -> str:
    """Class of ``match``, a mention of a superseded ADR in ``sentence``."""
    adr = int(match.group(1))
    before = sentence[: match.start()]
    after = sentence[match.end() : tail_end]
    if (
        adr in context.own_supersedes
        or context.quoted
        or LINEAGE_BEFORE_RE.search(before)
        or LINEAGE_AFTER_RE.match(after)
        or _NEGATED_BEFORE_RE.search(before)
        or _names_successor(sentence, context.corpus.chain(adr))
        or _HISTORY_RE.search(sentence)
    ):
        return HISTORY
    if (
        _AUTHORITY_CASED_RE.search(sentence)
        or _AUTHORITY_RE.search(sentence)
        or BINDING_BEFORE_RE.search(before)
    ):
        return AUTHORITY
    return UNCLASSIFIED


def _excerpt(line: str, adr: int, width: int = 60) -> str:
    """The author's own text around the first mention of ``adr`` on ``line``."""
    match = re.search(rf"ADR-0*{adr}\b", line)
    centre = match.start() if match else 0
    return line[max(0, centre - width) : centre + width].strip()


def citations_in(path: str, own: int, text: str, corpus: Corpus) -> list[Citation]:
    """Every mention of a superseded ADR in the record ``own``, classified."""
    found: list[tuple[int, int, str]] = []
    own_supersedes = corpus.supersedes.get(own, frozenset())
    masked = mask_non_citations(text)
    prefixes = _paragraph_prefixes(masked)
    for _bibliography, block in blocks(masked):
        joined = " ".join(line for _, line in block)
        starts: list[tuple[int, int]] = []
        offset = 0
        for number, line in block:
            starts.append((offset, number))
            offset += len(line) + 1
        for start, end in sentence_spans(joined):
            sentence = joined[start:end]
            matches = list(MENTION_RE.finditer(sentence))
            for index, match in enumerate(matches):
                adr = int(match.group(1))
                if adr == own or corpus.status.get(adr) != SUPERSEDED:
                    continue
                tail_end = matches[index + 1].start() if index + 1 < len(matches) else len(sentence)
                absolute = start + match.start()
                line_offset, lineno = max((o, n) for o, n in starts if o <= absolute)
                before = prefixes[lineno - 1] + joined[line_offset:absolute]
                context = ClassifyContext(corpus, own_supersedes, _quote_depth(before) > 0)
                found.append((lineno, adr, classify(sentence, match, tail_end, context)))
    lines = text.split("\n")
    return [Citation(path, n, adr, kind, _excerpt(lines[n - 1], adr)) for n, adr, kind in found]


@dataclass(frozen=True, slots=True)
class ScanResult:
    citations: list[Citation]
    candidates: int
    examined: int
    absent: list[str]
    unterminated: list[str] = field(default_factory=list)

    @property
    def authority(self) -> list[Citation]:
        return [c for c in self.citations if c.kind == AUTHORITY]

    @property
    def unclassified(self) -> list[Citation]:
        return [c for c in self.citations if c.kind == UNCLASSIFIED]


def scan(repo_root: Path, records: list[Record], corpus: Corpus) -> ScanResult | str:
    """Classify every superseded-ADR mention in the tracked live records.

    Returns the fault reason when git cannot list files, never an empty list.
    """
    tracked = tracked_files(repo_root, (f"{ADR_DIR}/ADR-*.md",))
    if tracked is None:
        return f"git could not list tracked ADR records under {repo_root}, so nothing was examined"
    by_path = {record.path: record for record in records}
    candidates = sorted(rel for rel in tracked if re.match(rf"{ADR_DIR}/ADR-\d+-", rel))
    citations: list[Citation] = []
    absent: list[str] = []
    unterminated: list[str] = []
    examined = 0
    for rel in candidates:
        record = by_path.get(rel)
        path = readable(repo_root, rel)
        if record is None or path is None:
            absent.append(rel)
            continue
        examined += 1
        if corpus.status.get(record.number) not in LIVE:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            absent.append(rel)
            continue
        fence_line = unterminated_fence_line(text)
        if fence_line is not None:
            unterminated.append(f"{rel}:{fence_line}")
        citations.extend(citations_in(rel, record.number, text, corpus))
    return ScanResult(citations, len(candidates), examined, absent, unterminated)


def _report(
    result: ScanResult, corpus: Corpus, new: list[str], stale: list[str], verbose: bool
) -> None:
    for citation in result.authority:
        if citation.key in new:
            print(citation.render(corpus.terminal_successor(citation.adr)))
    for key in stale:
        print(
            f"{key}: [{CHECK}] baseline entry no longer produced by the tree. "
            "Delete the line from the baseline."
        )
    if verbose:
        for citation in result.unclassified:
            print(f"{citation.path}:{citation.line}: [{CHECK}] unclassified ADR-{citation.adr:03d}")


def _fail_absent(result: ScanResult) -> int:
    for rel in result.absent:
        print(
            f"{rel}: [{CHECK}] tracked ADR record could not be read or parsed, "
            "so it was not scanned",
            file=sys.stderr,
        )
    print(
        f"[{CHECK}] config: skipped {len(result.absent)} of {result.candidates} tracked ADR "
        "record(s); a gate that cannot see every record has not passed.",
        file=sys.stderr,
    )
    return EXIT_CONFIG


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Flag a live ADR citing a superseded ADR as current authority."
    )
    parser.add_argument("--repo-root", default=".", help="Repository root to scan.")
    parser.add_argument("--baseline", default=str(_BASELINE_PATH), help="Known-violation list.")
    parser.add_argument("--verbose", action="store_true", help="List unclassified mentions.")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    adr_dir = repo_root / ADR_DIR
    if not adr_dir.is_dir():
        print(
            f"[{CHECK}] config: ADR directory {adr_dir} does not exist; examined 0 record(s)",
            file=sys.stderr,
        )
        return EXIT_CONFIG
    records, _violations = collect_records(adr_dir, repo_root)
    if not records:
        print(
            f"[{CHECK}] config: no ADR records found under {adr_dir}; examined 0 record(s)",
            file=sys.stderr,
        )
        return EXIT_CONFIG
    baseline = read_baseline(Path(args.baseline))
    if isinstance(baseline, str):
        print(f"[{CHECK}] config: {baseline}; examined 0 record(s)", file=sys.stderr)
        return EXIT_CONFIG

    corpus = build_corpus(records)
    result = scan(repo_root, records, corpus)
    if isinstance(result, str):
        print(f"[{CHECK}] external: {result}; examined 0 record(s)", file=sys.stderr)
        return EXIT_EXTERNAL
    if not result.examined:
        print(
            f"[{CHECK}] config: examined 0 of {result.candidates} tracked ADR record(s), "
            "so this run measured nothing",
            file=sys.stderr,
        )
        return EXIT_CONFIG
    if result.absent:
        return _fail_absent(result)

    current = {c.key for c in result.authority}
    new = sorted(current - baseline)
    stale = sorted(baseline - current)
    _report(result, corpus, new, stale, args.verbose)
    for location in result.unterminated:
        print(
            f"{location}: [{CHECK}] code fence is never closed, so every later line of "
            "the record is masked and its citations went unchecked.",
            file=sys.stderr,
        )
    scope = (
        f"{len(current)} authority violation(s) ({len(baseline)} known), "
        f"{len(result.unclassified)} unclassified, across "
        f"{result.examined} of {result.candidates} tracked ADR record(s)"
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


def validate_adr_supersession_citations(repo_root: Path) -> bool:
    """Pre-PR gate adapter: True only when the run completed with no new or stale entry.

    A configuration fault (exit 2) and an external fault (exit 3) return False.
    A gate that could not run has not passed.
    """
    return main(["--repo-root", str(repo_root)]) == EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
