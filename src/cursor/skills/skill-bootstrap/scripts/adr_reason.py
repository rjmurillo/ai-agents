# Port of aligndottech/align-cli at commit 8d758e9899677b61442b08ffda74b74887bfc42a
# Ported upstream file: src/lib/reason-extract.ts (extractReason, commitShaOf, and the
# helpers they use). Trailer and importer-text handling (stripTrailers, stripImporterMetadata,
# hasImporterMetadata) lives in adr_shape.py.
# Not ported: withReasons, which shapes align's search JSON and has no consumer here.
# Extension E3, breaking_change, has no upstream source.
# Sibling ports: adr_shape.py, adr_reason.py, adr_commits.py, adr_docs.py, adr_locate.py,
# adr_log.py, adr_scan.py, bootstrap_adr.py.
# MIT, Copyright (c) 2026 Align Tech Ltd, see LICENSE-align
"""The stated reason behind a decision, pulled out of its own text with no model.

Picks up to two sentences of a commit body that SAY why. Rules, all deterministic:

- A sentence qualifies only through a causal marker (because, so that, to avoid, ...)
  or an explicit "Why:" / "Reason:" label. Strong markers outrank medium ones.
- The text is the author's own words, cleaned of markup. Nothing is paraphrased.
- Importer metadata, trailers, "Fixes #N" lines, bot bodies, release-note dumps,
  tables, code, HTML comments and URLs are never reasons.
- A sentence that only repeats the title is dropped.
- None when nothing qualifies. A wrong reason is worse than none.

``breaking_change`` is new (extension E3, Conventional Commits 1.0.0). It sits here because a
breaking commit skips the rationale gate that this module feeds.

Regex notes: see the module docstring of ``adr_shape.py``; they apply to every module here.
"""

from __future__ import annotations

import re
from typing import NamedTuple

from adr_shape import (
    FIXES_ONLY,
    REASON_CONVENTIONAL_PREFIX,
    TRAILER,
    flat,
    has_importer_metadata,
    is_trailer_line,
    strip_importer_metadata,
    strip_trailers,
)

__all__ = ["REASON_MAX_CHARS", "breaking_change", "commit_sha_of", "extract_reason"]

# Per-sentence cap, cut at a word boundary. A display choice.
REASON_MAX_CHARS = 180
_MAX_SENTENCES = 2
# Only the head of a body is read: a 280k-character line must not cost a second.
_MAX_INPUT_CHARS = 6000
# Fewer words than this is a heading or a label, not a statement.
_MIN_WORDS = 5

_A = re.ASCII
_I = re.IGNORECASE | re.ASCII

# Sections that start a dump of someone else's changes.
_DUMP_HEADING = re.compile(
    r"^\s{0,3}(?:#{1,6}\s*)?(?:\*\*)?(?:what'?s changed|release notes?|changelog"
    r"|full changelog|commits|sourced from|bug fixes|features)\b"
    r"|^\s{0,3}#{1,6}\s*\[?v?\d+\.\d+",
    _I | re.MULTILINE,
)
# ``[ \t]*`` after a line anchor, never ``\s*``: ``\s*`` also eats newlines, so every line start
# of a long run of blank lines would rescan the rest of the run.
_BUMP_BODY = re.compile(
    r"^[ \t]*(?:bumps?|updates?|upgrades?)\s+(?:\[?`?[\w@/.-]+`?\]?(?:\([^)]*\))?\s+)?(?:from|to)\b"
    r"|this pr contains the following updates|^[ \t]*dependabot will resolve",
    _I | re.MULTILINE,
)

_STRONG = [
    re.compile(p, _I)
    for p in (
        r"\bbecause\b",
        r"\bso that\b",
        r"\bin order to\b",
        r"\bto avoid\b",
        r"\bto prevent\b",
        r"\bdue to\b",
        r"\bas a result\b",
        r"\bwas causing\b",
        r"\bcaused by\b",
        # "since" as a cause starts a clause ("since it is..."); as a date or version
        # it does not ("since node 16", "since pnpm/pnpm#1234", "since the first release").
        r"\bsince\s+(?:(?:the|it|its|we|they|this|that|there|a|an|our|these|those|you|i|all"
        r"|both|each|every|no|not|only|one|most|many)\b"
        r"(?!\s+(?:last|first|previous|beginning|start|release|version|v?\d))"
        r"|[\w.:/#-]+\s+(?:is|are|was|were|has|have|had|does|do|can|could|will|would|must"
        r"|should|may|might|needs?|uses?|finds?|takes?|lives?|stores?|ignores?|supports?"
        r"|reads?|runs?|returns?|calls?|makes?|requires?|works?|handles?|treats?)\b)",
    )
]
# These words DESCRIBE a change as often as they explain it, so they count only next
# to a word that names a problem.
_MEDIUM = [
    re.compile(p, _I)
    for p in (
        r"\binstead of\b",
        r"\brather than\b",
        r"\bpreviously\b",
        r"\bno longer\b",
        r"\bto fix\b",
        r"\bregression\b",
        r"\bdeprecated\b",
        r"\breplaces\b",
        r"\botherwise\b",
    )
]
_PROBLEM = re.compile(
    r"\b(?:break(?:s|ing)?|broke|broken|fail(?:s|ed|ing|ure)?|crash(?:es|ed|ing)?"
    r"|leak(?:s|ed|ing)?|incorrect(?:ly)?|wrong(?:ly)?|bugs?|errors?|slow(?:er|ly)?|hangs?"
    r"|lead(?:s|ing)? to|result(?:s|ed|ing)? in|caus(?:e|es|ed|ing))\b",
    _I,
)
_WEAK = [
    re.compile(p, _I)
    for p in (
        r"\bsecurity\b",
        r"\bperformance\b",
        r"\bvulnerab\w*",
        r"\bmemory leak\b",
        r"\bcrash(?:es|ed)?\b",
    )
]
_LABEL = re.compile(r"^(why|reason|rationale|motivation)\s*:\s*", _I)
# A label followed by a placeholder or a pointer says nothing.
_EMPTY_LABEL_BODY = re.compile(r"^(?:n/?a|none|see|tbd|todo|-)\b", _I)
_NEGATED = re.compile(r"(?:\bnot|\bnever|n't)\s+(?:just\s+|only\s+|simply\s+)?because\b", _I)
_FILE_TOKEN = re.compile(
    r"\b[\w-]+\.(?:ts|tsx|js|jsx|mjs|md|json|py|rs|go|txt|yml|yaml|css|html|toml|sh)\b", _I
)
_QUOTED = re.compile('"[^"]*"|\u201c[^\u201d]*\u201d')
_BREAKING_CHANGE = re.compile(r"breaking change", _I)
_ISSUE_KEY = re.compile(r"^\s*(?:bug|issue):", _I)

# A PR template's task list is a form someone ticked, never a reason.
_TASK_ITEM = re.compile(r"^\s*(?:[*+-]|\d+[.)])\s+\[[ xX]\]", _A)
_BULLET = re.compile(r"^\s*(?:[*+-]|\d+[.)])\s+", _A)
_NOISE_SENTENCE = re.compile(
    r"^merge (?:pull request|branch|remote-tracking)\b|\b(?:sourced from|dependabot|renovate)\b",
    _I,
)

# A removed URL leaves a marker, so a reason whose OBJECT was the link ("because of
# <url>") is dropped rather than printed with a hole in it.
_URL_HOLE = "\ue000"
_HTML_TAG = re.compile(
    r"</?(?:a|p|em|strong|b|i|u|code|pre|br|hr|h[1-6]|ul|ol|li|details|summary|blockquote"
    r"|div|span|img|sup|sub|table|thead|tbody|tr|td|th)\b[^>]*>",
    _I,
)
_DANGLING_LINK = re.compile(
    r"(?:\b(?:because of|due to|of|to|by|with|from|for|on|in|and|or)|,)\s*\ue000", _A
)
# Applied to flat text only (``_sentence_hit`` flattens first), where a whitespace run is one
# space, so ``\s?`` matches what ``\s*`` did, in linear time, and two holes in a row both go.
_HOLE_BEFORE_PUNCT = re.compile(r"\s?\ue000\s?([.,;:!?])", _A)
_HOLE = re.compile(r"\s?\ue000\s?", _A)

_COMMENT = re.compile(r"<!--[\s\S]*?(?:-->|\Z)", _A)
_FENCE = re.compile(r"^[ \t]*(```|~~~)[\s\S]*?(?:^[ \t]*\1|\Z)", _A | re.MULTILINE)
_COMMIT_SHA = re.compile(r"(?:/commit/|^git://commit/)([0-9a-f]{7,40})(?:[/?#]|\Z)", _A)

_QUOTE_MARK = re.compile(r"^\s*>+\s?", _A)
_HEADING_LINE = re.compile(r"^\s*#{1,6}\s", _A)
_TABLE_LINE = re.compile(r"^\s*\|", _A)
_RULE_LINE = re.compile(r"^\s*[-=*_|: ]{3,}\s*\Z", _A)
_HASH_LINE = re.compile(r"^\s*(?=[0-9a-f]*\d)[0-9a-f]{7,40}\b", _A)
_LINE_END_PUNCT = re.compile(r"[.!?:;,]\Z", _A)
_CAPITAL_START = re.compile(r"[A-Z]", _A)
_QUESTION_END = re.compile(r"\?\Z", _A)

# Fixed-width stand-in for the source's variable-width lookbehind: the abbreviation
# test runs on the text before the whitespace, after the split point is found.
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(`\[])", _A)
_ABBREVIATION_END = re.compile(
    r"(?<![A-Za-z0-9_])(?:e\.g|i\.e|etc|vs|cf|[Mm]r|[Mm]rs|[Mm]s|[Dd]r|Inc|Ltd|[Jj]r|[Ss]r|St)\.\Z",
    _A,
)
_ABBREVIATION_WINDOW = 9


class _Unit(NamedTuple):
    text: str
    bullet: bool


class _Scored(NamedTuple):
    pos: int
    score: float
    text: str


def commit_sha_of(source_url: str | None) -> str | None:
    """The commit sha a commit-backed decision points at, from its source URL."""
    if not source_url:
        return None
    match = _COMMIT_SHA.search(source_url)
    return match.group(1) if match else None


def _strip_markup(text: str) -> str:
    # One level of balanced parentheses in the URL (``wiki/Raft_(algorithm)``). Each branch stops
    # at the next parenthesis, so an unclosed ``[`` or ``(`` run stays linear.
    out = re.sub(r"!?\[([^\[\]]*)\]\((?:[^()]|\([^()]*\))*\)", r"\1", text)
    out = _HTML_TAG.sub(" ", out)
    out = re.sub(r"https?://\S+", f" {_URL_HOLE} ", out)
    out = re.sub(r"(\*\*|__)(.+?)\1", r"\2", out)
    out = re.sub(r"`([^`]*)`", r"\1", out)
    out = re.sub(r"(^|\s)[*_]([^*_\s][^*_]*)[*_](?=\s|[.,;:!?]|\Z)", r"\1\2", out)
    return flat(out)


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _is_mostly_english(text: str) -> bool:
    letters = sum(1 for ch in text if ch.isalpha())
    ascii_letters = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    return letters > 0 and ascii_letters / letters >= 0.8


def _repeats_title(sentence: str, title_words: list[str], title_body_words: list[str]) -> bool:
    sw = _words(sentence)
    if not sw or not title_words:
        return False
    in_title = set(title_words)
    if sum(1 for w in sw if w in in_title) / len(sw) >= 0.8:
        return True
    # The importer cuts a long title at 80 characters, so a body that opens with the
    # whole subject continues past where the title stops. Same words up to the cut.
    head = title_body_words[:-1]
    return len(head) >= 3 and all(i < len(sw) and sw[i] == w for i, w in enumerate(head))


def _score(sentence: str, labelled: bool) -> float:
    n = 3.0 if labelled else 0.0
    if any(p.search(sentence) for p in _STRONG):
        n = max(n, 3.0)
    elif any(p.search(sentence) for p in _MEDIUM) and _PROBLEM.search(
        _BREAKING_CHANGE.sub("", sentence)
    ):
        n = max(n, 2.0)
    if n > 0 and any(p.search(sentence) for p in _WEAK):
        n += 0.5
    return n


def _cap(sentence: str) -> str:
    if len(sentence) <= REASON_MAX_CHARS:
        return sentence
    head = sentence[:REASON_MAX_CHARS]
    cut = head if sentence[REASON_MAX_CHARS] == " " else re.sub(r"\s*\S*\Z", "", head, count=1)
    kept = re.sub(r"[,;:\-\s]+\Z", "", cut.rstrip() or head)
    return f"{kept}..."


def _marker_end(sentence: str) -> int | None:
    """Where the earliest strong or medium marker ends, or None when there is none."""
    best: tuple[int, int] | None = None
    for pattern in (*_STRONG, *_MEDIUM):
        match = pattern.search(sentence)
        if match and (best is None or match.start() < best[0]):
            best = (match.start(), match.end())
    return None if best is None else best[1]


def _fit(sentence: str, labelled: bool) -> str | None:
    """The text to show for a qualifying sentence.

    A long one is cut at the cap, which can hide the marker that qualified it, so a
    sentence whose marker lies past the cap is dropped rather than shown as a fragment.
    """
    shown = _cap(sentence)
    if len(sentence) <= REASON_MAX_CHARS or labelled:
        return shown
    # ``_cap`` ends a cut sentence with "...": the kept prefix is what the marker must fit in.
    end = _marker_end(sentence)
    return shown if end is None or end <= len(shown) - len("...") else None


def _is_trailer(line: str) -> bool:
    """A trailer key line. ``Issue:`` and ``Bug:`` count only when the value is a pointer."""
    return bool(TRAILER.search(line)) and (not _ISSUE_KEY.match(line) or is_trailer_line(line))


def _is_structural_line(line: str) -> bool:
    """Headings, tables, rules, trailers, issue pointers, task items and hash-led lines."""
    return bool(
        _HEADING_LINE.search(line)
        or _TABLE_LINE.search(line)
        or _RULE_LINE.search(line)
        or _is_trailer(line)
        or FIXES_ONLY.search(line)
        or _TASK_ITEM.search(line)
        or _HASH_LINE.search(line)
    )


def _starts_new_item(prev: str, line: str) -> bool:
    """Short unpunctuated lines are list entries, not a wrapped paragraph."""
    return (
        len(prev) < 60
        and not _LINE_END_PUNCT.search(prev)
        and bool(_CAPITAL_START.match(line.strip()))
    )


def _to_units(text: str) -> list[_Unit]:
    """Units are paragraphs and bullet items. Hard-wrapped lines of one unit are joined."""
    units: list[_Unit] = []
    current: list[str] = []
    is_bullet = False

    def flush() -> None:
        nonlocal current, is_bullet
        if current:
            units.append(_Unit(" ".join(current), is_bullet))
        current = []
        is_bullet = False

    for raw in text.split("\n"):
        line = _QUOTE_MARK.sub("", raw, count=1)
        if not line.strip() or _is_structural_line(line):
            flush()
        elif _BULLET.search(line):
            flush()
            is_bullet = True
            current.append(_BULLET.sub("", line, count=1))
        else:
            if current and _starts_new_item(current[-1], line):
                flush()
            current.append(line.strip())
    flush()
    return units


def _split_sentences(text: str) -> list[str]:
    """Split after . ! ? and whitespace before a capital, digit, quote or bracket.

    No split after an abbreviation (e.g., i.e., vs., etc., Mr., Dr., Inc., ...).
    """
    pieces: list[str] = []
    last = 0
    for match in _SENTENCE_BREAK.finditer(text):
        window = text[max(0, match.start() - _ABBREVIATION_WINDOW) : match.start()]
        if _ABBREVIATION_END.search(window):
            continue
        pieces.append(text[last : match.start()])
        last = match.end()
    pieces.append(text[last:])
    return pieces


def _prepare_text(title: str, body: str, flat_title: str) -> str | None:
    """The head of the body, cleaned of importer text, title echo, dumps and code."""
    bare = strip_importer_metadata(body)
    text = (strip_trailers(bare, title) if has_importer_metadata(body) else bare)[:_MAX_INPUT_CHARS]
    trimmed = text.lstrip()
    newline = trimmed.find("\n")
    first_line = flat(trimmed if newline < 0 else trimmed[:newline])
    if flat_title and first_line == flat_title:
        text = "" if newline < 0 else trimmed[newline:]
    # Code and comments go first: an example in them is not the body's own bump or changelog.
    text = _FENCE.sub("\n", _COMMENT.sub("\n", text))
    # Someone else's changes: bumps and release notes say what a dependency did.
    if _BUMP_BODY.search(text):
        return None
    dump = _DUMP_HEADING.search(text)
    return text if dump is None else text[: dump.start()]


def _unit_text(unit: _Unit) -> tuple[str, bool, bool] | None:
    """The cleaned text of a unit, whether it was labelled, and whether it reads as a subject."""
    text = _strip_markup(unit.text)
    labelled = False
    label = _LABEL.search(text)
    if label:
        labelled = True
        text = text[label.end() :]
        if _EMPTY_LABEL_BODY.search(text):
            return None
    # A squashed sub-commit title says what changed. Only a strong marker makes it a reason.
    conventional = bool(REASON_CONVENTIONAL_PREFIX.search(text))
    if conventional:
        text = REASON_CONVENTIONAL_PREFIX.sub("", text, count=1)
    return text, labelled, conventional or unit.bullet


def _sentence_hit(
    sentence: str,
    labelled: bool,
    subject_like: bool,
    title_words: list[str],
    title_body_words: list[str],
) -> tuple[float, str] | None:
    """Score and display text of one sentence, or None when it does not qualify."""
    if _DANGLING_LINK.search(sentence):
        return None
    s = _HOLE_BEFORE_PUNCT.sub(r"\1", flat(sentence))
    s = _HOLE.sub(" ", s).strip()
    if len(_words(s)) < _MIN_WORDS or not _is_mostly_english(s) or _NOISE_SENTENCE.search(s):
        return None
    if _repeats_title(s, title_words, title_body_words) or _QUESTION_END.search(s):
        return None
    # Score what the author asserts: not text in quotation marks (someone else's claim),
    # not a file name that happens to contain a marker word, not a negated "because".
    asserted = _FILE_TOKEN.sub(" ", _QUOTED.sub(" ", s))
    if _NEGATED.search(asserted):
        return None
    score = _score(asserted, labelled)
    if score < 2 or (subject_like and score < 3):
        return None
    shown = _fit(s, labelled)
    return None if shown is None else (score, shown)


def _score_units(text: str, flat_title: str) -> list[_Scored]:
    title_words = _words(flat_title)
    title_body_words = _words(REASON_CONVENTIONAL_PREFIX.sub("", flat_title, count=1))
    scored: list[_Scored] = []
    pos = 0
    for unit in _to_units(text):
        cleaned = _unit_text(unit)
        if cleaned is None:
            continue
        text_, labelled, subject_like = cleaned
        for index, sentence in enumerate(_split_sentences(text_)):
            pos += 1
            # The label introduces the first sentence only. The rest qualify on their own.
            hit = _sentence_hit(
                sentence.strip(),
                labelled and index == 0,
                subject_like,
                title_words,
                title_body_words,
            )
            if hit:
                scored.append(_Scored(pos, hit[0], hit[1]))
    return scored


def extract_reason(title: str, body: str | None) -> str | None:
    """Up to two sentences of ``body`` that state why, strongest first, in body order."""
    if not body:
        return None
    flat_title = flat(title or "")
    text = _prepare_text(title, body, flat_title)
    if text is None:
        return None
    scored = _score_units(text, flat_title)
    if not scored:
        return None
    best = sorted(scored, key=lambda s: (-s.score, s.pos))[:_MAX_SENTENCES]
    return " ".join(s.text for s in sorted(best, key=lambda s: s.pos))


# ---------------------------------------------------------------------------
# E3: breaking-change signal (extension, Conventional Commits 1.0.0)
# ---------------------------------------------------------------------------

_BREAKING_SUBJECT = re.compile(r"^[a-z]+(?:\([^)]*\))?!:", _I)
# The token is uppercase by the specification. BREAKING-CHANGE is its synonym.
_BREAKING_FOOTER = re.compile(r"^BREAKING[ -]CHANGE:[ \t]+\S", re.MULTILINE | _A)
# Both Conventional Commits separators: ``Key: value`` and ``Key #value``.
_FOOTER_LINE = re.compile(r"^[A-Za-z][A-Za-z0-9-]*(?::[ \t]+|[ \t]+#)\S", _A)
_BLANK_LINES = re.compile(r"\n[ \t]*\n", _A)


def breaking_change(subject: str, body: str) -> bool:
    """Does the commit mark itself as a breaking change?

    True for a ``type!:`` or ``type(scope)!:`` subject, and for a ``BREAKING CHANGE:``
    or ``BREAKING-CHANGE:`` line that begins a line in the footer. The footer is the
    last paragraph, or an earlier one when only trailer paragraphs (such as
    ``Co-Authored-By`` or ``Refs #1``) follow it. The phrase in mid-body prose or inside
    a fenced example does not count.
    """
    if _BREAKING_SUBJECT.search(subject.strip()):
        return True
    unfenced = _FENCE.sub("\n", body.replace("\r\n", "\n"))
    paragraphs = _BLANK_LINES.split(unfenced.strip())
    for paragraph in reversed(paragraphs):
        if _BREAKING_FOOTER.search(paragraph):
            return True
        if not _is_trailer_paragraph(paragraph):
            return False
    return False


def _is_trailer_paragraph(paragraph: str) -> bool:
    """A paragraph that opens with a footer line. Later lines continue its value."""
    lines = [line for line in paragraph.split("\n") if line.strip()]
    return bool(lines) and _FOOTER_LINE.match(lines[0]) is not None
