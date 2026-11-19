"""Advisory documentation style checks for `prose_lint.py --docs-style`.

Every hit is advisory: the caller reports each one at INFO severity, so none
of them changes an exit code. The checks catch the style defects a docs
reviewer would otherwise raise after the pull request opens.

Kinds:
  heading-case   ATX heading that is not in sentence case.
  link-text      Link text that says nothing: "this link", a bare URL, and so on.
  vague-opener   First line of a section opens "This is ..." or "It does ...".
  example-email  Email address on a real domain, where example.com belongs.
  token-shaped   String shaped like a GitHub, Anthropic, or AWS credential.

`heading-case`, `link-text`, and `vague-opener` read prose only (fenced code is
blanked). `example-email` and `token-shaped` also read fenced code, because
examples and sample config live there.

markdownlint MD059 already flags "here" and "click here" as link text, so that
rule owns those two; they are listed here only so one run reports every
non-descriptive link.
"""

from __future__ import annotations

import re
from typing import NamedTuple


class StyleHit(NamedTuple):
    """One advisory finding, located by 1-indexed line and column."""

    line: int
    column: int
    kind: str
    match: str
    note: str


PROPER_NOUNS = frozenset(
    {
        "GitHub", "Copilot", "Claude", "Codex", "Cursor", "Python", "PowerShell",
        "Markdown", "Windows", "Linux", "macOS", "Git", "Azure", "Microsoft",
        "Anthropic", "OpenAI", "Serena", "Hermes", "Muse", "Node", "npm", "ADR",
        "PR", "CI", "API", "CLI", "JSON", "YAML", "URL", "MCP", "Hindsight",
        "Grok", "ConfigGen", "Lefthook", "I",
    }
)  # fmt: skip
VAGUE_LINK_TEXT = frozenset({"this link", "link", "this page", "here", "click here"})
VAGUE_VERBS = (
    "is|are|was|does|will|can|should|has|lets|allows|provides|makes|means|covers|runs|checks"
)
EXAMPLE_DOMAINS = ("example.com", "example.org", "example.net")
NOREPLY_DOMAINS = ("users.noreply.github.com", "noreply.github.com")
FILE_EXTENSIONS = frozenset(
    {"png", "jpg", "jpeg", "gif", "svg", "webp", "ico", "css", "js", "ts", "json", "md", "txt"}
)

_ATX = re.compile(r"^ {0,3}#{1,6}[ \t]+(?P<text>.*?)(?:[ \t]+#+)?[ \t]*$")
_CODE_SPAN = re.compile(r"(`+)(?:(?!\1).)+?\1")
_LINK_URL = re.compile(r"\]\([^)]*\)")
_NUMBERING = re.compile(r"^\d+(?:\.\d+)*[.)]?$")
_LINK = re.compile(r"(?<!!)\[(?P<text>[^\[\]]*)\]\((?P<dest>[^()\s]*)(?:\s+\"[^\"]*\")?\)")
# Reference-style links: [text][label] and the collapsed form [text][].
_REF_LINK = re.compile(r"(?<!!)\[(?P<text>[^\[\]]+)\]\[[^\[\]]*\]")
_OPENER = re.compile(rf"^(?:This|It)\s+(?:{VAGUE_VERBS})\b")
_NOT_PARAGRAPH = re.compile(r"^(?:[-*+>|<]|\d+[.)]\s|#{1,6}\s|\[[^\]]+\]:)")
_EMAIL = re.compile(
    r"(?<![\w.+-])(?P<local>[\w.+-]+)@(?P<domain>[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)"
)
_TOKENS = (
    ("GitHub token", re.compile(r"ghp_[A-Za-z0-9]{36}")),
    ("GitHub token", re.compile(r"github_pat_[A-Za-z0-9_]{20,}")),
    ("Anthropic key", re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}")),
    ("AWS access key", re.compile(r"AKIA[0-9A-Z]{16}")),
)


def _blank_spans(text: str) -> str:
    return _CODE_SPAN.sub(lambda m: " " * len(m.group(0)), text)


def _word_is_exempt(word: str) -> bool:
    """Return whether an uppercase-initial word may stay capitalized."""
    base = word[:-2] if word.endswith("'s") else word
    return base in PROPER_NOUNS or any(c.isupper() for c in base[1:])


def _cased_words(text: str) -> list[str]:
    """Return the words after the first that start uppercase and have no exemption."""
    masked = _LINK_URL.sub("]", _blank_spans(text)).split(":", 1)[0]
    words = [w.strip("()[]\"'*_,.;!?") for w in masked.split()]
    words = [w for w in words if w]
    while words and _NUMBERING.match(words[0]):
        words.pop(0)
    return [w for w in words[1:] if w[0].isupper() and not _word_is_exempt(w)]


def _heading_hits(lines: list[str]) -> list[StyleHit]:
    hits = []
    for number, line in enumerate(lines, start=1):
        heading = _ATX.match(line)
        if not heading:
            continue
        offenders = _cased_words(heading.group("text"))
        if offenders:
            hits.append(
                StyleHit(
                    number,
                    heading.start("text") + 1,
                    "heading-case",
                    offenders[0],
                    "heading is not sentence case; lowercase "
                    + ", ".join(repr(w) for w in offenders)
                    + " unless a proper noun",
                )
            )
    return hits


def _link_hits(lines: list[str]) -> list[StyleHit]:
    hits = []
    for number, line in enumerate(lines, start=1):
        blanked = _blank_spans(line)
        links = [(m, m.group("dest")) for m in _LINK.finditer(blanked)]
        links += [(m, "") for m in _REF_LINK.finditer(blanked)]
        for link, dest in sorted(links, key=lambda pair: pair[0].start()):
            text = link.group("text").strip()
            lowered = text.lower()
            bare_url = (bool(dest) and text == dest) or lowered.startswith(("http://", "https://"))
            if lowered in VAGUE_LINK_TEXT or bare_url:
                hits.append(
                    StyleHit(
                        number,
                        link.start() + 1,
                        "link-text",
                        text,
                        "link text does not describe the target; name the destination",
                    )
                )
    return hits


def _opener_hits(raw: list[str], blanked: list[str]) -> list[StyleHit]:
    hits = []
    after_heading = False
    for number, (source, line) in enumerate(zip(raw, blanked, strict=True), start=1):
        if _ATX.match(line):
            after_heading = True
            continue
        if not after_heading or not source.strip():
            continue
        after_heading = False
        text = line.strip()
        if text and not _NOT_PARAGRAPH.match(text) and _OPENER.match(text):
            hits.append(
                StyleHit(
                    number,
                    line.index(text) + 1,
                    "vague-opener",
                    text.split(maxsplit=2)[0] + " " + text.split(maxsplit=2)[1],
                    "section opens with a vague pronoun; name the subject",
                )
            )
    return hits


def _email_is_fine(local: str, domain: str) -> bool:
    lowered = domain.lower()
    tld = lowered.rsplit(".", 1)[-1]
    if tld in FILE_EXTENSIONS or not tld.isalpha() or local == "git":
        return True
    if lowered in NOREPLY_DOMAINS or lowered.endswith(tuple("." + d for d in NOREPLY_DOMAINS)):
        return False
    if lowered == "anthropic.com":
        return local == "noreply"
    return lowered in EXAMPLE_DOMAINS or lowered.endswith(tuple("." + d for d in EXAMPLE_DOMAINS))


def _literal_hits(raw: list[str]) -> list[StyleHit]:
    hits = []
    for number, line in enumerate(raw, start=1):
        for email in _EMAIL.finditer(line):
            if not _email_is_fine(email.group("local"), email.group("domain")):
                hits.append(
                    StyleHit(
                        number,
                        email.start() + 1,
                        "example-email",
                        email.group(0),
                        "use an address at example.com, example.org, or example.net",
                    )
                )
        for label, pattern in _TOKENS:
            for token in pattern.finditer(line):
                hits.append(
                    StyleHit(
                        number,
                        token.start() + 1,
                        "token-shaped",
                        token.group(0)[:6] + "...",
                        f"looks like a {label}; use an obvious placeholder",
                    )
                )
    return hits


def docs_style_findings(raw_lines: list[str], blanked_lines: list[str]) -> list[StyleHit]:
    """Return advisory hits for a document.

    ``raw_lines`` are the source lines. ``blanked_lines`` are the same lines
    with fenced code blocks emptied, so line numbers align.
    """
    hits = (
        _heading_hits(blanked_lines)
        + _link_hits(blanked_lines)
        + _opener_hits(raw_lines, blanked_lines)
        + _literal_hits(raw_lines)
    )
    return sorted(hits, key=lambda h: (h.line, h.column, h.kind))
