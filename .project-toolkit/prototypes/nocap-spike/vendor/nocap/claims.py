# Modified for an ai-agents spike: dash escapes (lines 71, 377) and check counts routed to ci (round 3). See VENDORED.md.
# taste-lint: ignore file-size, vendored upstream code, kept close to upstream for diffing; see VENDORED.md.
# taste-lint: ignore complexity, vendored upstream code, kept close to upstream for diffing; see VENDORED.md.
"""Find checkable claims in a final reply. Deterministic, stdlib only. English here; Chinese, Thai and Spanish for
tests / push / merge / deploy in lang.py.

A claim is a past/present statement of fact about work done ("All tests pass", "Pushed to
origin/feat-x", "Created src/app.py"). Hedged, future, conditional and negated statements are not
claims: "tests should pass", "I will push", "if CI passes" are left alone.
"""
from __future__ import annotations

import itertools
import re
import unicodedata
from typing import Any, Dict, Iterator, List, Optional, Tuple

from .evidence import redact
from .lang import foreign_claims

MAX_SCAN = 64_000  # characters of a reply that are read (a final reply is rarely more than a few KB)
MAX_CLAIMS = 200
MAX_CLAUSE_TEXT = 10_000  # characters of candidate clauses checked per reply (real replies use a few hundred)
MAX_CLAUSES = 500
STAMP_RE = re.compile(r"🧾\s*NO CAP|🧢\s*CAP|🤔\s*NO RECEIPT|🫡\s*retracted|\*\*Receipts\*\*|🔁\s*/cap re-score:?|"
                      r"N(?<!\wN)O CAP\b|N(?<!\wN)O RECEIPT\b|[🧾🧢🤔🔁🫡]")  # N(?<!\wN) is \bN, written so `re` can skip ahead
IMPERATIVE_RE = re.compile(r"^(?:run|try|use|check|make|ensure|verify|open|install|set|add|please|consider|remember|"
                           r"don't|do not|click|type|paste|see|read|rerun|re-run|approve|pick|choose|decide|reply|tell|"
                           r"ask|say|send|keep|wait)\b", re.I)
IMPERATIVE_ANY_RE = re.compile(r"^to \w+\b|(?:^|[,:;]\s*|\b(?:then|and|please|so)\s+)(?:run(?!\s+in\s+"
                               r"[`'\"]?[~./][^\s]{0,200}\s*$)|confirm|verify|check(?:\s+that)?|"
                               r"make sure|ensure|merge|push|deploy|install|re-?run|open|approve)\b(?![-\w])", re.I)
ACK_RE = re.compile(r"\b(?:fail(?:s|ed|ing|ure|ures)?|errors?|except|pre-?existing|unrelated|flak(?:y|e|es)|skipped|"
                    r"broken|known issues?|xfail\w*)\b|失败|错误|跳过|未通过|ล้มเหลว|ไม่ผ่าน|"
                    r"\bfall(?:a|an|[oó]|aron|ido|idas?|os)\b|\berrores\b", re.I)
ZERO_FAIL_RE = re.compile(r"\b(?:0|no|zero|without) (?:test )?(?:failures?|failed|failing|errors?)\b|\b(?:nothing|none) failed\b|"
                          r"\b0 failed\b|\b0 errors?\b|\bfailures?:? 0\b|\berrors?:? 0\b|"
                          r"没有(?:任何)?(?:失败|错误)|无(?:失败|错误)|0\s{0,2}个?(?:失败|错误)|"
                          r"ไม่มี(?:การ|ตัวไหน|อันไหน)?(?:ที่)?\s{0,2}(?:ล้มเหลว|พัง|ข้อผิดพลาด)|"
                          r"\b(?:sin|ning[uú]n|ninguna|cero|0)\s+(?:fallos?|errores?|fallas?)\b", re.I)
REPORTED_RE = re.compile(r"\byou (?:said|mentioned|told|asked|wrote|reported|claimed|noted)\b|\baccording to\b|"
                         r"\byesterday\b|\blast (?:week|night|time|run|session)\b|\bearlier\b|\bpreviously\b|"
                         r"\bbefore (?:my|the|this|that) (?:change|edit|fix|commit)\b|\bas (?:i|we) (?:showed|said|mentioned)\b|"
                         r"\babove\b|\bused to\b|\boriginally\b|\binitially\b|\bat first\b|\b(?:reported|reports|says|said|claimed|claims|mentioned|"
                         r"told me|tells me|confirmed to me)\b|\bbefore (?:my|the|this|that|your|our|his|her|their) \w+", re.I)
# Earlier work in THIS session ("I pushed that earlier", "tests passed in the last turn"): judged on the session ledger
# instead of being skipped. Anything else REPORTED_RE matches (someone else, yesterday, before my change) still is.
SESSION_REF_RE = re.compile(r"\bearlier\b|\bpreviously\b|\blast run\b|\blast turn\b|\b(?:in|during|from|on) (?:the|my|our|"
                            r"your) (?:last|previous|prior|earlier) (?:turn|step|message|reply|run|attempt)\b|"
                            r"\bas (?:i|we) (?:showed|said|mentioned)\b|\ba (?:moment|minute|few minutes) ago\b", re.I)
FAR_RE = re.compile(r"\btoday\b|\btonight\b|\bthis (?:morning|afternoon|evening|week)\b|\bon (?:main|master)\b", re.I)
ALREADY_RE = re.compile(r"\balready\b", re.I)
APPROX_RE = re.compile(r"(?:about|around|roughly|approximately|approx\.?|nearly|almost|over|under|more than|"
                       r"less than|fewer than|at least|at most|up to|~|≈|>|<)\s*$", re.I)
SUMMARY_RE = re.compile(r"(?<!\d)\d+\s+(?:passed|failed|passing|failing)\b", re.I)

HEDGE_RE = re.compile(
    r"\b(should|would|could|might|may|will|won'?t|shall|going to|gonna|needs? to|let me|let's|i'll|we'll|you'll|"
    r"it'll|plan(?:ning)? to|try(?:ing)? to|expect(?:s|ed)? to|hopefully|once|if|unless|until|whether|make sure|"
    r"ensure|to be|todo|next step|later|please|can you|do you|want me|supposed to|ought to|probably|likely|"
    r"functionally|mostly|basically|essentially|largely|otherwise|that can|can pass|where possible|"
    r"seems?|appears?|i think|i believe|maybe|perhaps|in order to|so that|aim to|about to|yet to|at this pace|"
    r"projected|forecast|estimated?|on track to|suggest(?:s|ion|ed)?|recommend(?:s|ed|ation)?|proposal|propose[sd]?|"
    r"option|means|typically|usually|generally|in general)\b", re.I)
NEG_RE = re.compile(r"\b(not|never|no longer|nothing|none|nobody|neither|nor|without (?:running|testing|checking|"
                    r"verifying|pushing|merging|committing|deploying|building|it|them|a|any)|failed to|unable to|cannot|can't|"
                    r"yet to|instead of)\b|n't\b|^no\b|\bno (?:[\w-]+ ){0,4}(?:is|are|was|were|has|have)\b",
                    re.I)
URL_RE = re.compile(r"https?://[^\s'\"<>()\[\]{}`]+")
CODE_FENCE_RE = re.compile(r"```.*?(?:```|\Z)|~~~.*?(?:~~~|\Z)", re.S)
CLAUSE_SPLIT_RE = re.compile(r"\s\|\s|;\s+|,\s+which\s+|\s[\u2014\u2013]\s|\s--\s|,\s+(?:and|but|so|then|while)\s+|(?<!\s)\s+and then\s+")
SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
LEAD_RE = re.compile(r"^(?:[-*+•|]\s*|\d+[.)]\s+|[✅✔️☑️❌⚠️👉]+\s*|#+\s+|\*\*|__)+")

PASS_WORD = r"(?:pass(?:es|ed|ing)?|green|succeed(?:s|ed)?|successful(?:ly)?)"
UNSCOPED_TESTS = re.compile(r"(?:^|\b(?:all|the|all the|all of the|full|whole|entire|every|unit|test|green)\W+)"
                            r"(?:\d[\d,]*(?:\s*/\s*\d[\d,]*)?\s+)?(?:tests?|test suite|suite)\b|"
                            r"^(?:pytest|jest|vitest|mocha|go test|cargo test|npm test)\b|\bfull suite\b|\bsuite\b|"
                            r"^(?:\d[\d,]*\s+(?:tests?\s+)?(?:passed|passing|pass)|tests?\s*[:=])|"
                            r"\b(?:nothing|none) failed\b|\b(?:no|zero|0) (?:test )?failures\b|\b0 failed\b|\beverything pass")
TEST_NOUN = r"(?:tests?|specs?|test suite|suite|test cases?|pytest|jest|vitest|mocha|go test|cargo test|npm test|unit tests?)"
EXTS = (r"py|pyi|js|mjs|cjs|ts|tsx|jsx|md|mdx|json|jsonl|ya?ml|toml|txt|csv|tsv|html?|css|scss|sh|bash|zsh|go|rs|"
        r"swift|kt|java|rb|php|c|h|cc|cpp|hpp|m|mm|gif|png|jpe?g|webp|svg|mp4|mov|webm|mp3|wav|pdf|xlsx|docx|pptx|"
        r"sql|db|lock|cfg|ini|conf|xml|ipynb|log|env|plist|gradle|vue|svelte|lua|r|zip|tar|gz")
PATH_RE = re.compile(
    r"(?<![\w/.@-])`?((?:~|\.{1,2})?/(?:[\w.@-]+/)*[\w.@-]+|(?:[\w@-][\w.@-]*/)+[\w.@-]*\.(?:" + EXTS + r")|"
    r"[\w-][\w.-]*\.(?:" + EXTS + r"))`?(?![\w/-])", re.I)
SHA_RE = re.compile(r"(?<![#\w/-])([0-9a-f]{7,40})(?![\w-])")
NUM_NOUNS = (r"%|percent\b|(?:new |more |total |unique |open |extra |distinct )?(?:test |source |config |log |image |python |markdown )?(?:files?|lines?|rows?|records?|items?|"
             r"entries|errors?|warnings?|commits?|prs?|pull requests|issues?|bytes|kb|mb|gb|ms|seconds?|secs?|"
             r"minutes?|mins?|hours?|users?|requests?|pages?|images?|frames?|tokens?|calls?|matches|results?|"
             r"packages?|dependencies|deps|characters?|chars?|words?|points?|stars?|hits?|bugs?|findings?|"
             r"duplicates?|links?|screenshots?|plugins?|skills?|profiles?|sessions?|endpoints?|routes?|functions?|"
             r"classes|modules?|tables?|columns?|products?|orders?|steps?|cases?|claims?|replies|messages?|emails?|"
             r"repos?|branches?|tags?|downloads?|rules?|checks?|vulnerabilit(?:y|ies)|leaks?|keys?)\b")
NUM_RE = re.compile(r"(?<![\w.#/:$-])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(" + NUM_NOUNS + r")", re.I)

ROOT_RE = re.compile(r"/(?:Users|home|etc|var|opt|usr|srv|tmp|private|Library|Applications|root|mnt|workspace|"
                     r"testbed|app|repo|code|data|build|dist)/")
GIT_WORD_RE = re.compile(r"\b(?:pr|prs|pull requests?|branch(?:es)?|main|master|develop|dev|trunk|upstream|origin|remote|"
                         r"squash\w*|rebas\w*|conflicts?|github|gitlab|fast-forward\w*|release|staging|base)\b|#\d+")
CODE_MERGE_RE = re.compile(
    r"\bmerged?\b[^.]{0,50}?\b(?:functions?|helpers?|methods?|class(?:es)?|logic|dicts?|dictionar(?:y|ies)|lists?|"
    r"configs?|configuration|options|defaults|settings|sections?|blocks?|entries|lines|fields|props|params|parameters|"
    r"arguments|types|schemas?|maps?|results|outputs|arrays?|objects?|values|keys|imports|styles|cases|code paths?|"
    r"paths|loops?|handlers?|components?|hooks?|queries|rules|env|environment|headers|flags|records|rows)\b|"
    r"\bmerged?\b[^.]{0,50}?\binto (?:a|one|a single|the same|1)\b")
DESCRIBES_TEST_RE = re.compile(
    r"\b(?:tests?|specs?|cases?|assertions?|checks?)\s+(?:that|which|to)\s+(?:\w+\s+)?(?:checks?|verif\w*|ensures?|"
    r"asserts?|confirms?|covers?|makes sure)\b|\b(?:verifies|ensures|asserts|checks)\s+that\b", re.I)
KIND_ORDER = ["tests", "ci", "build", "merged", "pushed", "committed", "pr_opened", "deployed", "url", "file",
              "sha", "number", "unchecked"]
FILE_VERBS = (r"\b(created|wrote|written|saved|updated|added|edited|modified|generated|exported|rendered|"
              r"moved|renamed|deleted|removed|patched|changed|fixed|rewrote|refactored)\b")
_AGENT_VERB_RE = re.compile(
    r"(?:^|[:(]\s*|\b(?:i|we|i've|we've|i have|we have|i also|we also|then|and|just|now|both|so)\s+)"
    r"(?:also\s+|now\s+|just\s+|then\s+|have\s+|already\s+)?" + FILE_VERBS +
    r"|\b(?:is|are|was|were|been|got)\s+(?:now\s+|also\s+|just\s+)?" + FILE_VERBS)


def agent_voice(low: str) -> bool:
    """The edit verb is the agent's own ("Fixed X", "I updated X", "X was updated", "`x.py`: added ..."), not a
    description of what someone else's code did ("the upstream refactor removed X from y.ts")."""
    plain = re.sub(r"`[^`]*`|\*+", lambda m: "x" if m.group(0).startswith("`") else "", low)
    return bool(_AGENT_VERB_RE.search(re.sub(r"^[\W_]+", "", plain)))


_GROUP_SEP_RE = re.compile(r"(?<![\d,.])\d{1,3}(?:[\u00a0\u2009\u202f'’]\d{3})+(?!\d)")
_GROUP_SPACE_RE = re.compile(r"(?<![\d,.\w])\d{1,3}(?: \d{3})+(?!\d)(?=\s+(?:[\w-]+\s+)?(?:tests?|specs?|cases?|passed|passing|pass|failed|failing)\b)")


def _group_digits(text: str) -> str:
    """"15 812 passed", "15\u202f812", "15'812" → "15,812" (same length, so offsets hold)."""
    text = _GROUP_SEP_RE.sub(lambda m: re.sub(r"\D", ",", m.group(0)), text)
    return _GROUP_SPACE_RE.sub(lambda m: m.group(0).replace(" ", ","), text)


_NOT_NL_RE = re.compile(r"[^\n]")
MAX_SENT = 1_000  # a run-on "sentence" longer than this is read in chunks (keeps every regex pass short)


def _sentences(line: str) -> Iterator[Tuple[int, str]]:
    cursor = 0
    for sent in SENT_SPLIT_RE.split(line):
        s_off = line.find(sent, cursor)
        cursor = s_off + len(sent)
        while len(sent) > MAX_SENT:
            cut = sent.rfind(" ", MAX_SENT // 2, MAX_SENT)
            cut = MAX_SENT if cut <= 0 else cut
            yield s_off, sent[:cut]
            s_off, sent = s_off + cut, sent[cut:]
        yield s_off, sent


def _mask(text: str) -> str:
    chars = list(_group_digits(text))

    def blank(a: int, b: int) -> None:
        chars[a:b] = _NOT_NL_RE.sub(" ", "".join(chars[a:b]))

    for m in CODE_FENCE_RE.finditer(text):
        blank(m.start(), m.end())
    for m in STAMP_RE.finditer(text):  # a stamp in the reply is model-written: never trusted, never kept
        blank(m.start(), m.end())
    for m in re.finditer(r"“[^”\n]{0,300}”|\"[^\"\n]{0,300}\"", text):  # quoted words are someone else's claim
        if re.fullmatch(r"[“\"]=*\s*(?:\d[\d,]* (?:passed|failed|errors?|skipped|warnings?)(?:, )?)+(?: in [\d.]+s)?\s*=*[”\"]",
                        m.group(0)):
            continue  # ...unless it is a verbatim test summary, which is checkable
        blank(m.start(), m.end())
    pos = 0
    for line in text.split("\n"):
        end = pos + len(line)
        if line.strip().startswith(">"):
            blank(pos, end)
        pos = end + 1
    return "".join(chars)


# Cyrillic and Greek letters that look like the Latin letters of NO CAP / NO RECEIPT.
_CONFUSABLE = str.maketrans("АВСЕНІКМОРТХаеорсхіΑΒΕΗΙΚΜΝΟΡΤΧοι", "ABCEHIKMOPTXaeopcxiABEHIKMNOPTXoi")
STAMP_FORGED_RE = re.compile(r"(?<!`)[🧾🧢🤔📜🎓]\W{0,6}(?:N\W{0,3}O\W{0,3}C\W{0,3}A\W{0,3}P\b|C\W{0,3}A\W{0,3}P\b|"
                             r"N\W{0,3}O\W{0,3}RECEIPT)", re.I)


# A stamp the reply talks ABOUT, not one it stamps with. Inert places: a fenced block, an inline code span, a blockquote
# line, a quoted phrase. Inert uses: a legend ("🧾 NO CAP / 🧢 CAP or 🤔 NO RECEIPT"), the stamp as a noun ("a 🧢 CAP
# stamp", "the 🧾 NO CAP footer", "🧢 CAP is only for ..."). The stamps themselves are never trusted either way
# (_mask blanks them before claims are read); this only decides whether the reply gets the "didn't issue" warning.
_INERT_SPANS_RE = re.compile(r"```.*?(?:```|\Z)|~~~.*?(?:~~~|\Z)|`[^`\n]{1,300}`|“[^”\n]{0,300}”|\"[^\"\n]{0,300}\"|"
                             r"(?m:^[ \t]*>[^\n]*)", re.S)
_LEGEND_SEP_RE = re.compile(r"\s{0,3}(?:/|,|\||&|\bor\b|\band\b)\s{0,3}(?:or\s|and\s)?\s{0,2}$", re.I)
_NOUN_BEFORE_RE = re.compile(r"(?:\b(?:a|an|the|each|every|its|their|your|our|one|any|this|that|same|no cap's)|"
                             r"\b(?:see|says?|said|shows?|showed|read|reads|gets?|got|gives?|labels?)\s{1,3}"
                             r"(?:a|an|the)?)\s{0,3}$", re.I)
_NOUN_AFTER_RE = re.compile(r"\W{0,3}(?:stamps?|footers?|labels?|badges?|verdicts?|tags?|lines?|marks?|buttons?|"
                            r"means|meant|stands for|is|are|was|were|when|if|vs|versus)\b|\W{0,3}=",
                            re.I)


def _inert(raw: str) -> str:
    """The reply with code, blockquotes and quoted phrases blanked (same length, newlines kept)."""
    chars = list(raw)
    for m in _INERT_SPANS_RE.finditer(raw):
        chars[m.start():m.end()] = _NOT_NL_RE.sub(" ", m.group(0))
    return "".join(chars)


MAX_FORGED = 200  # stamps looked at per reply; a reply with more is a spoof either way, and the cap keeps it linear-cheap


def _in_prose(t: str, m: "re.Match[str]", spans: List[Tuple[int, int]], k: int) -> bool:
    """A stamp written into a sentence about stamps: part of a legend, or used as a noun. Every look is a short
    window (≤60 characters around the stamp), so a reply full of stamps stays linear (tests/test_redos.py)."""
    lo = max(0, m.start() - 60)
    before = t[lo:m.start()]
    before = before[before.rfind("\n") + 1:]
    if _NOUN_BEFORE_RE.search(before) or _NOUN_AFTER_RE.match(t[m.end():m.end() + 60]):
        return True
    for a, b in ((spans[k - 1][1], m.start()) if k > 0 else (0, -1),
                 (m.end(), spans[k + 1][0]) if k + 1 < len(spans) else (0, -1)):
        gap = t[a:b] if 0 <= b - a <= 20 else ""
        if gap and "\n" not in gap and _LEGEND_SEP_RE.fullmatch(gap):
            return True
    return False


def _norm_stamps(s: str) -> str:
    """NFKC; invisible format characters (zero-width, soft hyphen, bidi controls) and combining marks (N̲O̲) dropped;
    Cyrillic / Greek lookalikes of N O C A P R E I T read as Latin, so a homoglyph stamp is still a stamp. Newlines
    are never added or removed, so line k of the result is line k of the input."""
    t = unicodedata.normalize("NFKC", s)
    t = "".join(ch for ch in t if unicodedata.category(ch) not in ("Cf", "Mn", "Me")).translate(_CONFUSABLE)
    t = t.replace("*", "").replace("_", " ")
    return re.sub(r"[ \t\u00a0]+", " ", t)


# A RECEIPT-SHAPED line (judge review S1): a stamp, then a quoted claim, then a citation (`call N`, `turn N` or `→`).
# That is what a real receipt line looks like, so it is a forgery wherever it sits: a blockquote, quotation marks, a
# list, a code span or a fence, or after a "noun" word ("🧾 NO CAP lines: “...” · call 1"). Only stamps WITHOUT a
# quoted claim and a citation (a legend, `🧾 NO CAP` in a code span, "the 🧢 CAP stamp") stay exempt below.
# The stamp is the worded one, or a bare emoji right before a quoted claim (the Discord footer: 🧾 `merged #7`).
_SHAPE_STAMP_RE = re.compile(r"[🧾🧢🤔]\W{0,6}(?:N\W{0,3}O\W{0,3}C\W{0,3}A\W{0,3}P\b|C\W{0,3}A\W{0,3}P\b|"
                             r"N\W{0,3}O\W{0,3}RECEIPT)|[🧾🧢🤔][ ]?(?=[“\"`‘])", re.I)
_SHAPE_CITE_RE = re.compile(r"\b(?:call|turn) ?#?\d|→")
_QUOTES = {"“": "”", "\"": "\"", "`": "`", "‘": "’"}  # not ': an apostrophe (don't, it's) is no quote
_QUOTE_OPEN_RE = re.compile(r"[“\"`‘]")
SHAPE_WINDOW = 400  # characters after a stamp looked at for the quote and the citation (keeps the scan linear)
STAMP_LIKE_RE = re.compile(r"[🧾🧢🤔]\W{0,6}(?:N\W{0,3}O\W{0,3}C\W{0,3}A\W{0,3}P\b|C\W{0,3}A\W{0,3}P\b|"
                           r"N\W{0,3}O\W{0,3}RECEIPT)|^[^\w\n]*Receipts[^\w\n]*$|^[^\w\n]*Receipts ?·", re.I | re.M)


def _receipt_shaped(line: str) -> bool:
    """A stamp, a closed quote that starts after it, and a citation after that quote, within SHAPE_WINDOW. Each step
    is one bounded search, and at most 3 stamps and 3 quote openers are tried per line (linear; tests/test_redos.py)."""
    for m in itertools.islice(_SHAPE_STAMP_RE.finditer(line), 3):
        win = line[m.end():m.end() + SHAPE_WINDOW]
        for q in itertools.islice(_QUOTE_OPEN_RE.finditer(win), 3):
            j = win.find(_QUOTES[q.group(0)], q.end())
            if j > q.end() and _SHAPE_CITE_RE.search(win, j + 1):
                return True
    return False


def stamp_like(text: str) -> bool:
    """The reply holds something that looks like a No Cap stamp or footer header, anywhere (quoted, coded, or not)."""
    if not isinstance(text, str) or not text:
        return False
    return STAMP_LIKE_RE.search(_norm_stamps(text[:MAX_SCAN])) is not None


def forged_stamps(text: str) -> int:
    """How many No Cap stamps the model wrote itself (copied or invented). A receipt-shaped line counts wherever it
    sits; any other stamp counts in receipt position only (a stamp the reply explains, quotes or codes, a legend, the
    stamp as a noun, is not counted)."""
    if not isinstance(text, str):
        return 0
    cut = text[:MAX_SCAN]
    full = _norm_stamps(cut)  # normalized once; the inert copy below is blanked from it (newlines kept, lines align)
    shaped, looked = set(), 0
    for k, line in enumerate(full.split("\n")):
        if len(shaped) >= MAX_FORGED or looked >= 2 * MAX_FORGED:
            break  # bounded like the stamp count: a reply with this many stamp lines is a spoof either way
        if _QUOTE_OPEN_RE.search(line) is None or _SHAPE_STAMP_RE.search(line) is None:
            continue
        looked += 1
        if _receipt_shaped(line):
            shaped.add(k)
    raw = cut
    t = re.sub(r"[ \t]{2,}", " ", _inert(full))  # blanked spans collapse, as before: the prose windows read the same
    if shaped:
        t = "\n".join("" if k in shaped else line for k, line in enumerate(t.split("\n")))  # counted once, above
    found = list(itertools.islice(STAMP_FORGED_RE.finditer(t), MAX_FORGED))  # bounded: the count only feeds a warning
    spans = [m.span() for m in found]
    stamps = sum(1 for k, m in enumerate(found) if not _in_prose(t, m, spans, k))
    if re.search(r"[\u202e\u2067]", raw):  # right-to-left override: "PAC ON" is shown as "NO CAP"
        stamps += len(re.findall(r"(?<!`)[🧾🧢🤔📜🎓]\W{0,6}P\W{0,3}A\W{0,3}C\b", t, re.I))
    stamps = min(MAX_FORGED, stamps + len(shaped))
    return stamps or len(re.findall(r"^[^\w\n]*Receipts[^\w\n]*$|^[^\w\n]*Receipts[ \t]*·", t, re.M))


# Every claim kind needs one of these (a digit for numbers and SHAs, a verb or noun for the rest). A clause without
# any of them can't hold a claim, so it is skipped before the ~60 claim regexes run (long replies stay fast).
# The words are one alternation in which every branch starts with a plain literal ("\bci\b" is written c(?<!\wc)i\b), run
# on lowercased text without IGNORECASE: `re` then builds a first-character set and skips, in C, every position that
# can't start a gate word. Digits are a second pattern (`\d` is one character set, so it gets the same skip). In one
# alternation, a `\d` or a leading `\b` branch made `re` try all ~100 branches at each of 64 K positions: a 100 KB
# Thai run took 70-110 ms of CPU (tests/test_redos.py).
_GATE_WORDS = (r"test|spec|suite|pytest|jest|vitest|mocha|pass|fail|c(?<!\wc)i\b|check|action|workflow|"
               r"pipeline|green|succe|"
               r"build|compil|merg|land|push|commit|p(?<!\wp)rs?\b|pull|deploy|ship|publish|releas|roll|live|u(?<!\wu)p\b|"
               r"online|http|head|"
               r"creat|wr[io]t|sav|updat|add|edit|modif|generat|export|render|mov|renam|delet|remov|patch|chang|fix|refactor|"
               r"失败|错误|跳过|未通过|测试|通过|推送|合并|合入|部署|上线|发布|完成|搞定|修复|ทดสอบ|เทส|ผ่าน|พุช|เมิร์|"
               r"ดีพลอย|เสร็จ|เรียบร้อย|prueba|sub[ií]|fusion|despleg|producci|integr|listo|hecho|terminad|arregl|resuelt|"
               r"完了|成功|ました|완료|통과|푸시|병합|배포|готово|сделано|исправ|erledigt|fertig|behoben|termin|corrig|conclu|implant")
_GATE = r"\d|" + _GATE_WORDS
GATE_RE = re.compile(_GATE, re.I)  # the same test in one pattern; the hot paths use _gated / _gate_lines below
_GATE_WORDS_RE = re.compile(_GATE_WORDS)  # on lowercased text only
_DIGIT_RE = re.compile(r"\d")
_ONE_TO_ONE = {0x130: "i"}  # "İ" is the only code point whose lower() is two characters: map it so offsets hold


def _lower(text: str) -> str:
    """text.lower() with the same length as text, so match offsets are offsets into text."""
    return text.translate(_ONE_TO_ONE).lower() if "\u0130" in text else text.lower()


def _gated(text: str) -> bool:
    return _DIGIT_RE.search(text) is not None or _GATE_WORDS_RE.search(_lower(text)) is not None


def _gate_lines(masked: str) -> Iterator[Tuple[int, str]]:
    """The lines that contain a gate word, in order. Each pattern's next hit is kept until the scan passes it, and
    each search starts after the last yielded line, so no character is scanned twice by the same pattern (linear)."""
    low, pos, n = _lower(masked), 0, len(masked)
    nxt = {_DIGIT_RE: -1, _GATE_WORDS_RE: -1}  # next hit start per pattern (-1: not searched yet, n + 1: none left)
    while pos <= n:
        for rx in nxt:
            if nxt[rx] < pos:
                m = rx.search(low, pos)
                nxt[rx] = m.start() if m else n + 1
        hit = min(nxt.values())
        if hit > n:
            return
        start = masked.rfind("\n", 0, hit) + 1
        end = masked.find("\n", hit)
        end = n if end < 0 else end
        yield start, masked[start:end]
        pos = end + 1


def _clauses(masked: str) -> Iterator[Tuple[int, str, str]]:
    for line_start, line in _gate_lines(masked):
        for s_off, sent in _sentences(line):
            c_cursor = 0
            for clause in CLAUSE_SPLIT_RE.split(sent):
                c_off = sent.find(clause, c_cursor)
                c_cursor = c_off + len(clause)
                lead = LEAD_RE.match(clause)
                skip = lead.end() if lead else 0
                body = clause[skip:]
                if body.strip():
                    start = line_start + s_off + c_off + skip
                    yield start + (len(body) - len(body.lstrip())), body.strip(), (line_start + s_off, sent)


def _int(s: Optional[str]) -> Optional[int]:
    return int(s.replace(",", "")) if s else None


GENERIC = {"all", "the", "full", "whole", "entire", "existing", "every", "test", "remaining", "other", "of", "our",
           "my", "your", "now", "still", "also", "both", "and", "these", "those", "suite", "a", "rest", "complete",
           "repo", "repository", "project", "unit", "integration", "e2e", "automated", "python", "js", "go", "rust",
           "cargo", "jest", "vitest", "pytest", "npm", "frontend", "backend", "core", "regression",
           "i", "we", "ran", "run", "reran", "re-ran", "with", "after", "then", "so", "that", "which", "it", "they",
           "are", "is", "were", "was", "have", "has", "had", "here", "there", "again", "fixed", "confirmed", "verified",
           "checked", "including", "plus", "in", "on", "of", "for", "from", "during", "across", "+", "-", "\u2014", "\u2013", "&", "everything", "all-", "local", "locally", "green", "passing", "ok", "done", "good", "yes"}


def _qualified(low: str) -> bool:
    """True when the test noun is narrowed: "the SSH remote suite", "`foo.ts` (4 tests)", "tests in pkg/x",
    "the test" (one test). Narrowed claims never 🧢: we can't tell which run they mean.
    "Ran existing tests: the full `x` suite passes" is a checklist label; the detail after the colon decides."""
    head, sep, detail = re.sub(r"\*+", "", low).partition(":")
    if sep and re.search(r"\b(tests?|suite|specs?)\b", detail):
        if _names_scope(head):
            return True  # "`vize_atelier_ssr`: all tests pass": the label is a crate/package, so the claim is about it
        low = detail
    plain = re.sub(r"\b\d[\d,]*(?:\s*/\s*\d[\d,]*)?\b", " ", low)
    ms = list(re.finditer(r"((?:[^\s]+\s+){0,4})(test suites?|test cases?|tests?|specs?|suite)\b(.{0,40})", plain))
    return bool(ms) and all(_narrow(m) or (m.start(2) > 0 and plain[m.start(2) - 1] in "/._-`") for m in ms)


def _names_scope(head: str) -> bool:
    """A label naming a crate, package or module: `vize_atelier_ssr`, @acme/ui, "the parser crate"."""
    head = re.sub(r"^[\W_]+", "", head).strip()
    if not head or re.search(r"\b(?:tests?|suites?|specs?)\b", head) or len(head) > 60:
        return False
    if re.search(r"(?:^|\s)[@\w][\w@.-]*[_/@.][\w@./-]*\w(?:\s|$)|(?:^|\s)\w+(?:-\w+){2,}(?:\s|$)", head):
        return True  # an identifier: snake_case, @scope/name, pkg.module, kebab-case-name ("re-run" is a word)
    words = [w for w in re.findall(r"[\w-]+", head) if w not in GENERIC]
    return bool(re.search(r"\b(?:crate|package|module|pkg|workspace member)\b", head)) and any(
        w not in ("crate", "package", "module", "pkg", "workspace", "member") for w in words)


def _narrow(m) -> bool:
    if re.match(r"[/._\w-]", m.group(3)) or re.search(r"[/._-]$", m.group(1)):
        return True  # part of a path or identifier: tests/foo/, test_bar.py
    before = [w.strip("`*,.:;()[]") for w in m.group(1).split()]
    if m.group(2) == "test" and not re.match(r"\s*(?:suite|run|s)\b", m.group(3)) and (before[-1:] or [""])[0] in (
            "the", "this", "that", "my", "new", "one", "single", "a"):
        return True  # "the test now passes": one test
    before = [w for w in before if re.search(r"\w", w)]
    if any(w and w not in GENERIC and not w.isdigit() for w in before[-2:]):
        return True
    if any(w in ("relevant", "affected", "related", "targeted", "focused", "new") for w in before):
        return True
    return bool(re.match(r"\s*(?:in|for|under|from|of)\s+(?!(?:the\s+)?(?:repo|repository|project|codebase|workspace|whole|"
                         r"entire|full|suite|test|run|build|ci)\b)[\w`./-]", m.group(3)))


_FORMER_FAILURE_PASS_RE = re.compile(
    r"\b(?:failing|failed)\s+tests?\s+(?:now\s+pass(?:es|ed)?|pass(?:es|ed)?\s+now)\b", re.I)


def _tests(cl: str, low: str) -> Optional[Dict[str, Any]]:
    if re.search(r"\bcompil(?:e|es|ed|ing|ation)\b", low):
        return None  # "test sources compile" / "test compilation passed" are build claims, not test runs
    if re.fullmatch(r"[\W_]*(?:all\s+)?tests?\s+(?:passing|passed|status|results?)\s*:[\W_]*", low):
        return None  # a heading ("Tests Passing:")
    ratio = re.search(r"(?<![\d,])(\d[\d,]*)\s*/\s*(\d[\d,]*)", low)
    if ratio and _int(ratio.group(1)) < _int(ratio.group(2)):
        return None  # "412/414 pass" admits failures
    if re.search(r"\b(score[sd]?|scoring|mark|grade|threshold|rating|benchmark|accuracy)\b", low):
        return None
    ff = re.search(r"\b(?:fixed|repaired|resolved)\s+(?:the|all|those|these)?\s*(\d+|two|three|four|five)?\s*"
                   r"(?:previously\s+)?(?:failing|failed|broken|red)\s+tests?\b", low)
    if ff:  # "fixed the 2 failing tests" says something about an earlier run: 🤔 unless a run proves it
        return {"kind": "tests", "passed": None, "failed": None, "total": None, "all_pass": False, "fails": False,
                "count_only": False, "scoped": True, "fixed_failing": True}
    if _FORMER_FAILURE_PASS_RE.search(low):
        if re.search(r"\bstill\s+(?:fail|error|red\b|broken)|\bstill\s+\d+\s+fail", low):
            return None  # "two failing tests now pass, three still fail": progress, neither a pass nor a fail claim
        # "three failing tests now pass": three describes the old failures, not the current run.
        return {"kind": "tests", "passed": None, "failed": None, "total": None, "all_pass": True, "fails": False,
                "count_only": False, "scoped": True, "formerly_failing": True}
    if re.search(r"\b(?:tests?|specs?)\s+(?:that\s+)?(?:were|was|had been)\s+(?:previously\s+)?failing\s+(?:now\s+)?pass|"
                 r"\bpreviously[- ]failing\s+tests?\s+(?:now\s+)?pass", low):
        return {"kind": "tests", "passed": None, "failed": None, "total": None, "all_pass": True, "fails": False,
                "count_only": False, "scoped": True}
    if not re.search(r"\b(tests?|specs?|suite|pytest|jest|vitest|mocha|passed|failed|passing|failing)\b|"
                     r"\d\s+(?:pass|fail)\b", low):
        return None
    passed = failed = total = None
    all_pass = fails = False
    n = r"(?<![\d,.])(\d{1,3}(?:,\d{3})+|\d+)"
    m = re.search(n + r"\s*(?:/|of)\s*" + n + r"\s+(?:\w+\s+){0,2}?(?:pass|passing|passed|green|ok)\b", low)
    if m:
        passed, total = _int(m.group(1)), _int(m.group(2))
    m = re.search(r"\ball\s+" + n + r"\s+(?:\w+\s+)?(?:tests?|specs?|cases?)\b(?!\s+(?:suites?|files?))", low)
    if m:
        passed = _int(m.group(1))
    if passed is None:
        m = re.search(n + r"\s+(?!(?:test\s+)?(?:suites?|files?)\b)(?:\w+\s+)?(?:tests?\s+|specs?\s+)?(?:passed|passing|pass(?:es)?)\b", low)
        if m:
            passed = _int(m.group(1))
    m = re.search(n + r"\s+(?:\w+\s+)?(?:tests?|specs?)\s+(?:are\s+|were\s+|still\s+)?(?:failed|failing|fail)\b",
                  low) or re.search(n + r"\s+(?:failed|failing|fail|fails)\b", low) or \
        re.search(n + r"\s+(?:[\w-]+\s+){0,2}?(?:test\s+)?failures?\b", low)
    gone = r"^\W*(?:(?:were|was|are|is|have been|has been|got|now|all)\s+){0,2}(?:removed|fixed|resolved|gone|eliminated|cleared|addressed|repaired)\b|^\W*(?:reduced|down|dropped|went)?\s*(?:to|→|->)\s*(?:0|zero|none)\b|^\W*(?:reduced|down|dropped)\b"
    if m and not re.search(r"\b(fixed|resolved|addressed|repaired|fixes)\b", low[:m.start()]) and not re.search(
            gone, low[m.end():]):  # "(3 failures were removed)" reports the fix, not a failure
        failed = _int(m.group(1))
    explicit_zero = False
    if re.search(r"\b(no|zero|0)\s+(?:test\s+)?(failures|failed|failing|errors)\b|\bnone failed\b|\bnothing failed\b",
                 low):
        failed = 0
        explicit_zero = True
    words = {"one": 1, "a": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
             "ten": 10}
    wm = re.search(r"\b(one|a|two|three|four|five|six|seven|eight|nine|ten)\s+(?:[\w-]+\s+)?(?:failures?|flakes?|"
                   r"failing tests?|failed tests?|known failures?)\b", low)
    if failed is None and wm and not re.search(r"\b(fixed|resolved|addressed|repaired)\b", low[:wm.start()]):
        failed = words[wm.group(1)]
    if re.search(r"\bflak(?:e|es|y)\b", low) and not failed:
        failed = failed or 1
    pass_hit = re.search(TEST_NOUN + r"\b[^.]{0,30}?\b" + PASS_WORD + r"\b", low) or \
        re.search(r"\b(all green|passes all tests|all tests passing)\b|\btests?\s*[:=-]?\s*ok\b", low)
    fail_hit = re.search(TEST_NOUN + r"\b[^.]{0,20}?\b(fail(?:s|ed|ing)?|red|broken)\b", low)
    negated = bool(NEG_RE.search(low)) and failed != 0
    # "all tests pass despite the failed run": a claim that ALL pass with a failure word beside it is not an admission
    # ("some tests pass, others fail" is). A failing run must not prove it, and /cap re-score and Cap Coach must not
    # read it as the agent taking the claim back.
    # No digit: "the failed one is flaky" is no count ("one" parses as 1), while "2 integration tests fail" is an
    # honest count beside the pass claim and stays an admission.
    asserts_pass = bool(pass_hit and not negated and fail_hit and not re.search(r"\d", low)
                        and _ALL_PASS_SUBJECT_RE.search(low) and not _PARTIAL_RE.search(low))
    if pass_hit and not negated:
        all_pass = True
    if pass_hit and negated:
        fails = True
    if fail_hit and not re.match(r"\s*(fixed|resolved|addressed|repaired)\b", low) and failed is None:
        fails = True
    if failed:
        fails, all_pass = True, False
    all_word = bool(re.search(r"\ball\b|\bevery\b|\bentire\b|\bwhole\b", low)) or (
        total is not None and passed == total) or explicit_zero
    count_only = passed is not None and not all_word and not fails
    if passed is not None and not fails and all_word:
        all_pass = True
    if failed == 0 and not fails:
        all_pass = True
    if count_only:
        all_pass = False
    if passed is None and failed is None and not all_pass and not fails:
        return None
    strong = re.search(r"\b(green|passes|succeeds?|succeeded|is passing|are passing|all passing|all pass)\b|"
                       + TEST_NOUN + r"\s+(?:all\s+|now\s+|still\s+)?pass(?:ed)?\b", low)
    if count_only and strong:
        count_only, all_pass = False, not fails
    if re.search(r"\b(?:log|output|file|report)\s+(?:shows|says|reads|has)\b", low) and count_only:
        return {"kind": "tests", "passed": passed, "failed": None, "total": None, "all_pass": False, "fails": False,
                "count_only": True, "scoped": True, "cites_log": True}
    return {"kind": "tests", "passed": passed, "failed": failed, "total": total, "all_pass": all_pass and not fails,
            "fails": fails, "count_only": count_only, "asserts_pass": asserts_pass and fails,
            "scoped": not UNSCOPED_TESTS.search(low.strip()) or _qualified(low)}


def _claims_in(cl: str) -> List[Dict[str, Any]]:
    def code(m):
        inner = m.group(1)
        if SUMMARY_RE.search(inner) or re.fullmatch(r"[\w@~][\w./@~-]*", inner):
            return inner
        return " code "

    low = re.sub(r"\*+", "", re.sub(r"`([^`]*)`", code, cl)).lower().replace("\u2019", "'").replace("\u2018", "'")
    low = re.sub(r"[“\"]([^”\"]{0,200})[”\"]", lambda m: m.group(1) if SUMMARY_RE.search(m.group(1)) else " quoted ", low)
    out: List[Dict[str, Any]] = []
    negated = bool(NEG_RE.search(low))
    urls = [u.rstrip(".,;:!?'\"") for u in URL_RE.findall(cl)]
    no_url = URL_RE.sub(" ", cl)
    no_url_low = no_url.lower()

    ci = re.search(r"(?:^|\b(?:the|all|its|pr|github|main)\s+)(ci|ci checks|checks|pr checks|github actions|actions|ci run|"
                   r"ci jobs?|workflows?|pipeline)\s+(?:(?:on|for|in)\s+(?:the\s+)?(?:pr|branch|main|commit)?\s*#?\w*\s+)?"
                   r"(?:(?:is|are|run|runs|job|jobs|now|all|also|both)\s+){0,2}"
                   r"(pass(?:es|ed|ing)?|green|succeed(?:ed|s)?)\b", low)
    if ci and not negated and re.search(r"\b(ci|github|actions|workflows?|pipeline|pr checks)\b", low):
        out.append({"kind": "ci", "scoped": bool(re.search(r"\b(vercel|preview|netlify|local|my machine)\b", low))})
    elif ci:
        pass
    else:
        t = _tests(cl, low)
        bare = re.sub(r"`[^`]*`", " ", low)  # check names in backticks ("`Run Python Tests`") are not test words
        if t and re.search(r"\bchecks\b", bare) and not re.search(r"\b(?:tests?|specs?|suites?|unit)\b", bare) \
                and not re.search(r"\b(?:pytest|jest|vitest|uv run|npm (?:run )?test|go test|cargo test)\b", low):
            # spike round 3: "106 passed, 0 failed checks" counts CI checks, not a test run
            out.append({"kind": "ci", "scoped": False, "counts": True, "passed": t.get("passed"),
                        "failed": t.get("failed"), "all_pass": bool(t.get("all_pass")) and not re.search(
                            r"\b(?:pending|queued|running|in progress|waiting|so far)\b", bare)})
            t = None
        if t:
            if re.search(r"[“\"][^”\"]{0,200}[”\"]", cl):
                t["quoted"] = True  # a quoted summary: a receipt if it matches, silent if it doesn't
            out.append(t)
    if not negated and re.search(r"\bbuild\b(?!\s+(?:log|output|report|artifact)s?\b)[^.]{0,20}?\b(pass(?:es|ed)?|succeed(?:s|ed)?|green|works|is clean)\b|"
                                 r"\bbuilds? (?:cleanly|successfully)\b|\bcompiles? (?:cleanly|successfully|fine)\b",
                                 low):
        out.append({"kind": "build"})
    if negated:
        pass
    else:
        merged_verb = re.search(r"(?:^|\b(?:i|we|it|is|was|were|are|been|be|have|has|had|and|just|now|both|all|already|"
                                r"got|then|also|everything|pr|#\d+|\d+)\s+)(?:squash(?:ed)?[- ])?merged\b|"
                                r"\bmerged\s+(?:into|to|in|#|pr\b|pull|the pr|it|them|both|via|with|on)|"
                                r"\bsquash(?:ed)?[- ]merged\b|^landed\b|\b(?:is|was|were|are|been|have|has)\s+landed\b", low)
        if merged_verb and CODE_MERGE_RE.search(low) and not GIT_WORD_RE.search(low):
            merged_verb = None  # "merged the two helpers into one": code, not a git merge
        if merged_verb and "conflict" not in low:
            into = re.search(r"\bmerged\s+(?!(?:pr|pull request)\b|#)[\w`'./-]+(?:\s+[\w`'./()-]+){0,2}?\s+(?:in)?to\b", low)
            m = re.search(r"(?:#|\bpr\s*#?|pull request\s*#?)(\d+)", low)
            out.append({"kind": "merged", "pr": _int(m.group(1)) if (m and not into) else None,
                        "git_merge": bool(into)})
        if re.search(r"\bpushed\b", low):
            m = re.search(r"\bpushed\b[^.]*?\bto\s+(?:the\s+)?(?:origin/|upstream/|remote/)?`?([\w./-]+)", low)
            branch = m.group(1).rstrip(".,") if m else None
            if branch and not (re.search(r"[/\-\d_]", branch) or branch in ("main", "master", "develop", "dev", "trunk",
                                                                         "staging", "production", "prod", "release")):
                branch = None
            if branch in ("origin", "upstream", "remote", "github", "gitlab") or (
                    branch and re.fullmatch(r"[0-9a-f]{7,40}", branch)):
                branch = None
            out.append({"kind": "pushed", "branch": branch})
        m = re.search(r"(?:^|\b(?:i|we|it|is|was|were|are|been|be|have|has|had|and|just|now|both|all|already|also|"
                      r"everything|changes|then|got)\s+)committed\b|^committed\b|\bcreated (?:a |the )?commit\b", low) \
            if not re.search(r"\b(checkpoint|transaction|database|db|budget|spend|memory)\b", low) else None
        if m:
            s = SHA_RE.search(low[m.start():])
            out.append({"kind": "committed", "sha": s.group(1) if s and re.search(r"\d", s.group(1)) else None})
        if re.search(r"\b(opened|created|filed|raised|submitted)\b[^.]{0,30}?\b(pr|pull request)\b", low) or \
                re.search(r"\b(pr|pull request)\b[^.]{0,12}?\b(is (?:now )?)?(open(?:ed)?|up)\b", low):
            m = re.search(r"(?:#|\bpr\s*#?|pull request\s*#?|/pull/)(\d+)", low)
            out.append({"kind": "pr_opened", "pr": _int(m.group(1)) if m else None})
        dep = re.search(r"\b(deployed|redeployed|shipped to prod\w*|published (?:v?\d|to|on|the)|"
                        r"released (?:v?\d|to|on|the (?:app|build|version|update))|rolled out)\b", low)
        live = re.search(r"\b(went live|is (?:now )?live|now live|live at|is up|is online)\b", low) if re.search(
            r"\b(site|app|page|service|server|deploy\w*|api|website|prod\w*|release|build|preview)\b", low) else None
        if dep or (live and not urls):
            out.append({"kind": "deployed"})
        if urls and re.search(r"\b(live|up|online|reachable|responds?|returns?|returning|serving|serves|loads|"
                              r"working|works|available|deployed|resolves|200|ok)\b", URL_RE.sub(" ", low)):
            sm = re.search(r"\b(?:returns?|returning|responds?(?: with)?|status(?: code)?|gives?|answers?(?: with)?)\s+"
                           r"(?:an?\s+|http\s+|with\s+)?([1-5]\d\d)\b", no_url_low) or \
                re.search(r"\b([1-5]\d\d)\s+ok\b|\bhttp\s+([1-5]\d\d)\b", no_url_low)
            status = None
            if sm:
                status = int(next(g for g in sm.groups() if g))
            for u in urls[:3]:
                out.append({"kind": "url", "url": u, "status": status})
        if re.search(FILE_VERBS, no_url_low) and agent_voice(no_url_low) and not (
                re.search(r"\b(?:temp|temporary|throwaway|scratch|ad[- ]hoc)\b", no_url_low)
                and not re.search(r"\b(?:removed|deleted|cleaned up)\b", no_url_low)):
            for m in PATH_RE.finditer(no_url):
                p = m.group(1).strip("`").rstrip(".")
                if not p or re.fullmatch(r"[./~]*", p) or re.search(r"(?:^|/)\.{2,}$", p):
                    continue  # `./...` is a Go package pattern
                if p.startswith("/") and not re.search(r"\.(?:" + EXTS + r")$", p, re.I) and not ROOT_RE.match(p):
                    continue  # /v1, /api/users: a URL route, not a file
                if re.match(r"`?:\d", no_url[m.end():m.end() + 3]):
                    continue  # path:line is a code reference, not a write
                if p.lower().startswith(("http", "www.")) or re.fullmatch(r"[\d.]+", p):
                    continue
                out.append({"kind": "file", "path": p})
    hm = re.search(r"\bhead\b(?:\s+(?:sha|commit))?\s+(?:is\s+)?(?:now\s+)?(?:at\s+|=\s*|:\s*)?`?([0-9a-f]{7,40})`?(?![\w-])", no_url_low)
    if hm:
        out.append({"kind": "sha", "sha": hm.group(1), "head": True})
    sha_context = re.search(r"\b(commit|committed|head|sha|pushed|merged|tagged|landed|gated|tested|built|at|is|was|on|"
                            r"rev|revision|hash)\b", no_url_low)
    for m in (SHA_RE.finditer(no_url_low) if sha_context else []):
        s = m.group(1)
        if re.search(r"\d", s) and re.search(r"[a-f]", s) and not (hm and s == hm.group(1)):
            out.append({"kind": "sha", "sha": s})
    for m in NUM_RE.finditer(no_url):
        if APPROX_RE.search(no_url[max(0, m.start() - 16):m.start()]):
            continue
        val = m.group(1).replace(",", "")
        before = no_url_low[max(0, m.start() - 40):m.start()]
        action = bool(re.search(r"\b(changed|modified|touched|edited|fixed|created|added|deleted|removed|updated|wrote|"
                                r"rewrote|refactored|migrated|renamed)\b(?:\s+\w+){0,2}\s*$", before))
        out.append({"kind": "number", "value": val, "unit": m.group(2).lower().strip(), "action": action,
                    "repo_wide": bool(re.search(r"\b(across|whole|entire|in) (?:the )?(repo|repository|codebase|project)\b",
                                                no_url_low))})
    return out


def _key(c: Dict[str, Any]) -> Tuple:
    return tuple([c["kind"]] + [str(c.get(k)) for k in sorted(c) if k not in ("kind", "start", "end", "text")])


PART_SPLIT_RE = re.compile(r",\s+(?:and\s+|but\s+|then\s+)?|(?<!\s)\s+(?:and|&)\s+(?=(?:re-?)?[a-z]+ed\b|(?:re-?)?(?:ran|wrote|made|built|got|put|set|left|kept|sent|did)\b|the\b|[a-z]+s\b|it\b|i\b|we\b)", re.I)
_FRAG_FIELD = {"pushed": "branch", "merged": "pr", "file": "path", "url": "url", "sha": "sha", "number": "value",
               "pr_opened": "pr", "committed": "sha"}


def _fragments(clause: str, claims: List[Dict[str, Any]]) -> None:
    """Several claims in one clause ("All tests pass, pushed to main"): give each its own part, for display only."""
    if len(claims) < 2:
        return
    parts, pos = [], 0
    for m in list(PART_SPLIT_RE.finditer(clause)) + [None]:
        end = m.start() if m else len(clause)
        if clause[pos:end].strip():
            parts.append((pos, end))
        pos = m.end() if m else end
    if len(parts) < 2:
        return
    found = [(a, b, _claims_in(clause[a:b])) for a, b in parts]
    for c in claims:
        f = _FRAG_FIELD.get(c["kind"])
        for a, b, cs in found:
            if any(x["kind"] == c["kind"] and (not f or str(x.get(f)) == str(c.get(f))) for x in cs):
                c["_frag"] = (a, b)
                break


_ADMIT_RES = [
    re.compile(r"(?<![\d,.])[1-9]\d{0,5}\s+(?:[\w`./:-]+\s+){0,3}?(?:fail(?:ed|ing|ures?|s)?|errors?|broken)\b"),
    re.compile(r"\b(?:still|remain(?:s|ing)?|continues?\s+to)\s+(?:[\w`-]+\s+){0,2}?(?:fail\w*|broken|erroring)\b"),
    re.compile(r"\b(?:pre-?existing|unrelated|known|flaky)\s+(?:[\w-]+\s+){0,2}?(?:failures?|errors?|fails|failing)\b"),
    re.compile(r"\bfail(?:s|ed|ing|ures?)?\b[^.\n]{0,80}?\b(?:pre-?existing|unrelated|before (?:my|this|the) change|"
               r"on (?:main|master)|without (?:my|this|the) (?:change|patch))"),
    re.compile(r"`?\btest[\w./:\[\]-]*`?\s+(?:still\s+|also\s+)?(?:fails|is failing|errors out|is broken)\b"),
    re.compile(r"(?m)^(?:FAILED|ERROR) [\w./-]+::"),
]
_ADMIT_FIX_RE = re.compile(r"\b(?:fixed|resolved|repaired|now pass(?:es)?|passes now|previously|used to|was failing|"
                           r"were failing|before (?:the|my|this) fix|caus(?:ed|es|ing))\b")
_ADMIT_STILL_RE = re.compile(r"\b(?:still|remain\w*|pre-?existing|unrelated|known)\b")


def admissions(text: str) -> List[Tuple[int, int]]:
    """Spans where the reply admits a test failure ("2 tests fail", "still fails", "a pre-existing failure", a FAILED
    line), anywhere in the reply's prose (pass the masked text: code blocks and quotes blanked). A fix report ("fixed the failing test", "previously
    failing tests now pass") is not an admission unless it also says something still fails."""
    low = text.lower()
    out: List[Tuple[int, int]] = []
    if "fail" not in low and "error" not in low and "broken" not in low:
        return out  # every admission pattern needs one of these words: skip six full-text scans (tests/test_redos.py)
    for rx in _ADMIT_RES:
        for m in rx.finditer(text if rx.pattern.startswith("(?m)") else low):
            a = max(low.rfind(".", 0, m.start()), low.rfind("\n", 0, m.start())) + 1
            b = min([x for x in (low.find(".", m.end()), low.find("\n", m.end())) if x >= 0] or [len(low)])
            sent = low[a:b]
            if _ADMIT_FIX_RE.search(sent) and not _ADMIT_STILL_RE.search(sent):
                continue
            if re.search(r"\b(?:0|no|zero)\s+(?:failures?|failed|errors?)\b", low[max(0, m.start() - 3):m.end()]):
                continue
            out.append((m.start(), m.end()))
            if len(out) >= 50:
                return out
    return out


_LIST_AFTER_RE = re.compile(r"[ \t]*\n(?:[ \t]*\n)?[ \t]*(?:[-*+•]|\d+[.)])\s+")


# "all tests pass ...", "every test passes ...", "the whole suite passes ...": the all-word belongs to what passes
# ("some tests pass, others fail in every run" has one too, about the runs). A partial quantifier anywhere keeps the
# sentence an honest mixed report.
_ALL_PASS_SUBJECT_RE = re.compile(r"\b(?:all|every|entire|whole)\b(?:\s+[\w-]+){0,4}?\s+(?:pass|passes|passed|passing|green)\b"
                                  r"|\beverything\s+(?:pass|passes|passed|is\s+green)\b")
_PARTIAL_RE = re.compile(r"\b(?:some|most|many|few|several|other|others|rest|remaining|partly|partially|except|but\s+not)\b"
                         r"|\bnow\b[^.;,]{0,40}\bfail(?:s|ed)?\b"  # "all tests passed before, now tests fail": an honest report
                         r"|\b(?:passing|green)\s+(?:tests?|ones)\s+pass")  # "all passing tests pass, the failing ones fail"


def extract_claims(text: str) -> List[Dict[str, Any]]:
    if not isinstance(text, str) or not text.strip():
        return []
    scan = text[:MAX_SCAN]
    masked = _mask(scan)
    admits = admissions(masked)  # prose only: logs pasted in code blocks or quotes are often history, not admissions
    found: List[Dict[str, Any]] = []
    seen = set()
    budget, n_clauses, acked_cache = MAX_CLAUSE_TEXT, 0, {}
    for start, clause, (sent_id, sentence) in _clauses(masked):
        if not _gated(clause):
            continue
        budget -= len(clause)
        n_clauses += 1
        if budget < 0 or n_clauses > MAX_CLAUSES:
            break  # a reply this long is read up to here: every regex pass stays short (tests/test_redos.py)
        plain = clause.replace("\u2019", "'").replace("\u2018", "'")
        foreign = foreign_claims(clause)  # its own near-miss rules per language (negation, future, questions)
        revived = False
        if clause.rstrip().endswith("?") or HEDGE_RE.search(plain) or IMPERATIVE_RE.search(plain) \
                or IMPERATIVE_ANY_RE.search(plain):
            claims = []
        elif REPORTED_RE.search(plain) or SESSION_REF_RE.search(plain):
            # earlier work in this session: kept, marked, and judged only on earlier turns (verdict.judge)
            revived = bool(SESSION_REF_RE.search(plain)) and not REPORTED_RE.search(SESSION_REF_RE.sub(" ", plain)) \
                and not FAR_RE.search(plain)
            claims = _claims_in(clause) if revived else []
        else:
            claims = _claims_in(clause)
        if revived or ALREADY_RE.search(plain):
            for c in claims:
                c["earlier"] = True
                if revived:
                    c["revived"] = True
        kinds = {c["kind"] for c in claims}
        claims += [c for c in foreign if c["kind"] not in kinds and c["kind"] != "unchecked"]
        if not claims:  # a completion phrase No Cap can't check yet: a hidden 🤔, only when nothing else was found
            claims = [c for c in foreign if c["kind"] == "unchecked"][:1]
        if not claims:
            continue
        if DESCRIBES_TEST_RE.search(plain):  # "a test that checks the build succeeds" says what a test does
            claims = [c for c in claims if c["kind"] not in ("tests", "build")]
        if sent_id not in acked_cache:
            acked_cache[sent_id] = bool(ACK_RE.search(ZERO_FAIL_RE.sub(" ", sentence)))
        acked = acked_cache[sent_id]
        for c in claims:
            if c["kind"] == "tests" and acked and not c.get("fails") and not c.get("scoped"):
                c["ack"], c["all_pass"] = True, False  # the sentence admits a failure: at most a count
                c["count_only"] = c.get("passed") is not None
        claims = [c for c in claims if not (c["kind"] == "tests" and c.get("ack") and not c.get("count_only"))]
        if any(c["kind"] == "tests" for c in claims):
            para_lo = masked.rfind("\n\n", 0, sent_id) + 1
            para_hi = masked.find("\n\n", sent_id)
            para_hi = len(masked) if para_hi < 0 else para_hi
            prev = re.split(r"(?<=[.!?])\s+", masked[max(para_lo, sent_id - 300):sent_id].strip())[-1:]
            after = masked[sent_id + len(sentence):min(para_hi, sent_id + len(sentence) + 300)].strip()
            nxt = re.split(r"(?<=[.!?])\s+", after)[:1]
            near = " ".join(prev + nxt)
            if ACK_RE.search(ZERO_FAIL_RE.sub(" ", near)):
                for c in claims:
                    if c["kind"] == "tests":
                        c["ack_near"] = True  # a neighbouring sentence admits failures: never 🧢
        _fragments(clause, claims)
        claims.sort(key=lambda c: KIND_ORDER.index(c["kind"]))
        for c in claims:
            k = _key(c)
            if k in seen:
                continue
            seen.add(k)
            c["start"], c["end"], c["sent"] = start, start + len(clause), sent_id
            line_start = masked.rfind("\n", 0, start) + 1
            if masked[line_start:start].lstrip().startswith("|") and c["kind"] in ("tests", "ci"):
                c["table"] = True  # a table cell: 🧢 only when the turn has a single matching run
            c["text"] = redact(text[start:start + len(clause)])[:200]  # masked whole, then cut
            if c["kind"] == "tests":
                s_lo, s_hi = sent_id, sent_id + len(sentence)
                if any(b <= s_lo or a >= s_hi for a, b in admits):
                    c["ack_reply"] = True  # another part of the reply admits a failure: never 🧢, never 🧾 for "all"
                if clause.rstrip().endswith(":") and _LIST_AFTER_RE.match(text, start + len(clause)):
                    c["scoped"] = True  # "All tests pass:" + a list: the claim is about the listed items
                    after = text[start + len(clause):start + len(clause) + 1200]
                    if len(text) > start + len(clause) + 1200:  # never cut inside a word (see evidence._cut_back)
                        after = after[:max(after.rfind(" "), after.rfind("\n")) + 1]
                    c["scope_text"] = redact(after)[:200]
            fr = c.pop("_frag", None)
            if fr and fr != (0, len(clause)):
                c["frag"] = redact(text[start + fr[0]:start + fr[1]].strip())[:200]
            found.append(c)
            if len(found) >= MAX_CLAIMS:
                return found
    return found
# mypy: ignore-errors
