"""Deterministic reply-friction flags.

A flag is a sampling stratum, never a verdict. Every flag is a pure function of
the text, so a rerun over the same frozen population gives the same strata.
Labels come from a reader through `replies_audit.py tally`.

Agent-side flags read a reply. Human-side flags read the typed follow-up that
directly follows it and carry the `h_` prefix when attached to a reply.
Prior authority (the human points back at an earlier grant) is kept apart from
a generic nudge (a bare "continue"), because the two mean opposite things about
whether the agent stopped too early.
"""

from __future__ import annotations

import hashlib
import re

SWEAR = re.compile(r"\b(fuck\w*|shit\w*|wtf|damn\w*|bullshit|crap|ffs|goddamn|hell)\b", re.I)
CONFUSED = re.compile(
    r"\b(confus\w+|what do you (want|need)|what are you asking|i don'?t (understand|know what|remember)|"
    r"what does (that|this) mean|what is (that|this)\b|makes? no sense|unclear|huh\b|eli5|eli10|"
    r"plain (english|language)|what am i (supposed|looking)|why are you (telling|asking)|tl;?dr|"
    r"what'?s the (ask|bottom line))",
    re.I,
)
REPEAT = re.compile(
    r"\b(again|i (already|just) (said|told|asked)|as i said|i told you|like i said|"
    r"stop (doing|asking)|how many times|still (not|broken|failing|wrong))\b",
    re.I,
)
OWNJOB = re.compile(
    r"\b(rebase|update (the|your) branch|merge (origin/)?main|rerun|re-run|"
    r"fix (it|that|this|them|your)|finish (it|the|this)|do it|just do|go ahead|"
    r"you (should|need to|must) (have )?(do|fix|run|check|verify)|that'?s your job|"
    r"why (did|didn'?t|haven'?t) you|keep going|don'?t stop|why did you stop|"
    r"resolve (the )?conflict)",
    re.I,
)
NUDGE = re.compile(
    r"^\s*(continue|keep going|go|proceed|resume|carry on|and\?|status\??|done\??|ded\??|well\??|\?+)\s*[.!?]*\s*$",
    re.I,
)
AUTHORITY = re.compile(
    r"\b(i (already )?(approved|authori[sz]ed|said (yes|ok|okay|go))|"
    r"you (already )?have (my )?(approval|permission|authority|the go[- ]ahead)|"
    r"already (approved|authori[sz]ed|granted)|as (approved|authori[sz]ed|agreed|discussed)|"
    r"full[- ]send|i gave you (approval|permission|the go[- ]ahead)|"
    r"(approved|authori[sz]ed) (earlier|before|already|above))\b",
    re.I,
)
WRONG = re.compile(
    r"\b(that'?s (wrong|not|incorrect)|not what i|you (said|claimed|told me)|"
    r"didn'?t (work|pass|merge|happen)|it'?s (not|still)|but (it|the|you)|"
    r"isn'?t (merged|done|fixed|passing)|never (ran|merged|pushed))\b",
    re.I,
)
NEG_START = re.compile(r"^\s*(no[,. !]|nope|stop\b|wrong|don'?t\b|why\b)", re.I)
OFFER_TAIL = re.compile(
    r"(want me to|would you like|shall i|should i\b|do you want|let me know|happy to|i can also|"
    r"if you(?:'d| would)? (like|want|prefer)|say the word|tell me (if|which|whether|and)|"
    r"point me at|your call|up to you|which (would|do) you (prefer|want))",
    re.I,
)
ADR = re.compile(r"\bADR-\d{2,4}\b")
ISSUE = re.compile(r"(?<![\w/\[])#\d{3,5}\b")
DECISION_HEAD = re.compile(
    r"^\s*(#+\s*|\*\*)?.{0,40}\b(for your decision|decisions? (for|needed|you)|needs? (you|your)|"
    r"your (call|decision|input)|open (questions|decisions)|what i need from you|"
    r"action(s)? (for|needed))\b",
    re.I | re.M,
)
SELF_CHORE = re.compile(
    r"\b(\d+ commits? behind|behind (origin/)?main|needs? (a )?rebas\w+|may conflict|"
    r"possible (merge )?conflict|might conflict|merge conflict|out of date with)\b",
    re.I,
)
ANSWER_FIRST = re.compile(
    r"^\s*(\*\*)?(bottom line|tl;?dr|needs you|no action|nothing needs|result|done|merged|"
    r"blocked|decision|status|verdict|answer)\b",
    re.I,
)
EVAL_MARK = re.compile(r"^\s*(\[eval\]|<eval|eval[-_ ]?(case|replay|run)\b)", re.I)

MIN_FINGERPRINT_CHARS = 40
HEAD_CHARS = 600


def _glossed(text: str, match: re.Match[str]) -> bool:
    """True when an identifier has a nearby gloss: parenthesis, quote, colon, or link text."""
    tail = text[match.end() : match.end() + 4]
    head = text[max(0, match.start() - 2) : match.start()]
    return tail.lstrip().startswith(("(", '"', ":")) or head.endswith(("[", "("))


def bare_ids(text: str) -> int:
    """Count ADR and issue identifiers with no nearby gloss."""
    return sum(
        1
        for pattern in (ADR, ISSUE)
        for found in pattern.finditer(text)
        if not _glossed(text, found)
    )


def agent_flags(text: str) -> list[str]:
    """Flags for one agent reply."""
    flags: list[str] = []
    tail = text[-400:]
    if tail.rstrip().endswith("?"):
        flags.append("ends_question")
    if OFFER_TAIL.search(tail):
        flags.append("offer_tail")
    bare = bare_ids(text)
    if bare >= 3:
        flags.append("bare_ids3")
    if bare >= 8:
        flags.append("bare_ids8")
    if DECISION_HEAD.search(text):
        flags.append("decision_head")
    if SELF_CHORE.search(text):
        flags.append("self_chore")
    if len(text) > 1500:
        flags.append("long1500")
        if not ANSWER_FIRST.search(text[:200]):
            flags.append("long_no_lead")
    if len(text) > 4000:
        flags.append("long4000")
    return flags


def human_flags(text: str, prev_len: int) -> list[str]:
    """Flags for a typed follow-up. `prev_len` is the length of the reply it answers."""
    head = text[:HEAD_CHARS]
    checks = (
        ("swear", SWEAR.search(head)),
        ("confused", CONFUSED.search(head)),
        ("repeat", REPEAT.search(head)),
        ("ownjob", OWNJOB.search(head)),
        ("wrong_claim", WRONG.search(head)),
        ("neg_start", NEG_START.search(head)),
        ("short_question", len(text) < 200 and "?" in text),
        ("short_after_long", len(text) < 120 and prev_len > 1500),
    )
    flags = [name for name, hit in checks if hit]
    if NUDGE.match(text):
        flags.append("generic_nudge")
    elif AUTHORITY.search(head):
        flags.append("prior_authority")
    return flags


def prompt_fingerprint(text: str) -> str | None:
    """Stable id of a long first prompt, used to spot replayed eval sessions."""
    norm = " ".join(text.lower().split())
    if len(norm) < MIN_FINGERPRINT_CHARS:
        return None
    return hashlib.sha256(norm.encode("utf-8", errors="replace")).hexdigest()[:16]


def is_eval_marked(text: str) -> bool:
    """True when a first prompt starts with an explicit eval marker."""
    return bool(EVAL_MARK.match(text))
