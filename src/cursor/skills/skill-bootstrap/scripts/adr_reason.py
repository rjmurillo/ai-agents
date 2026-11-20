# Port of aligndottech/align-cli at commit 8d758e9899677b61442b08ffda74b74887bfc42a
# Ported upstream file: src/lib/reason-extract.ts (extractReason, commitShaOf, and the
# helpers they use). Trailer and importer-text handling (stripTrailers, stripImporterMetadata,
# hasImporterMetadata) lives in adr_trailers.py.
# Not ported: withReasons, which shapes align's search JSON and has no consumer here.
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

Regex notes. Module-level patterns compile with ``re.ASCII`` so ``\\b``, ``\\w``, ``\\d`` and
case folding match the JavaScript source. ``$`` without a multiline flag is ``\\Z``
here, because Python's ``$`` also matches before a trailing newline. ASCII ``\\s`` does not match Unicode spaces such as U+00A0, which JavaScript's ``\\s`` does. Whitespace
normalisation (``flat`` in adr_trailers) stays Unicode-aware, as ``\\s`` is in JavaScript.
"""

from __future__ import annotations

import re
from typing import NamedTuple

from adr_trailers import (
    CONVENTIONAL_PREFIX,
    FIXES_ONLY,
    TRAILER,
    flat,
    has_importer_metadata,
    strip_importer_metadata,
    strip_trailers,
)

__all__ = ["REASON_MAX_CHARS", "commit_sha_of", "extract_reason"]

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
_BUMP_BODY = re.compile(
    r"^\s*(?:bumps?|updates?|upgrades?)\s+(?:\[?`?[\w@/.-]+`?\]?(?:\([^)]*\))?\s+)?(?:from|to)\b"
    r"|this pr contains the following updates|^\s*dependabot will resolve",
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
_HOLE_BEFORE_PUNCT = re.compile(r"\s*\ue000\s*([.,;:!?])", _A)
_HOLE = re.compile(r"\s*\ue000\s*", _A)

_COMMENT = re.compile(r"<!--[\s\S]*?(?:-->|\Z)", _A)
_FENCE = re.compile(r"^\s*(```|~~~)[\s\S]*?(?:^\s*\1|\Z)", _A | re.MULTILINE)
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
    out = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)
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
    if len(sentence) <= REASON_MAX_CHARS or labelled:
        return _cap(sentence)
    end = _marker_end(sentence)
    return _cap(sentence) if end is None or end <= REASON_MAX_CHARS else None


def _is_structural_line(line: str) -> bool:
    """Headings, tables, rules, trailers, issue pointers, task items and hash-led lines."""
    return bool(
        _HEADING_LINE.search(line)
        or _TABLE_LINE.search(line)
        or _RULE_LINE.search(line)
        or TRAILER.search(line)
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
    # Someone else's changes: bumps and release notes say what a dependency did.
    if _BUMP_BODY.search(text):
        return None
    dump = _DUMP_HEADING.search(text)
    if dump:
        text = text[: dump.start()]
    text = _COMMENT.sub("\n", text)
    return _FENCE.sub("\n", text)


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
    conventional = bool(CONVENTIONAL_PREFIX.search(text))
    if conventional:
        text = CONVENTIONAL_PREFIX.sub("", text, count=1)
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
    s = _HOLE_BEFORE_PUNCT.sub(r"\1", sentence)
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
    title_body_words = _words(CONVENTIONAL_PREFIX.sub("", flat_title, count=1))
    scored: list[_Scored] = []
    pos = 0
    for unit in _to_units(text):
        cleaned = _unit_text(unit)
        if cleaned is None:
            continue
        text_, labelled, subject_like = cleaned
        for sentence in _split_sentences(text_):
            pos += 1
            hit = _sentence_hit(
                sentence.strip(), labelled, subject_like, title_words, title_body_words
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
