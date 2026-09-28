#!/usr/bin/env python3
"""Provenance rules for new_issue.py (issue #5700).

Who selected the work (``--source``), the Step 0 evidence an agent-sourced
issue must carry (Q3 who is blocked, Q5 the signal that proves it), and the
``source:*`` label rules. Every validation here is pure (no network, no
argparse), so it runs before new_issue.py resolves a repository or calls gh.
``ensure_source_label`` is the one function that calls gh.
"""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys


def _load_bundled_redact():
    """Load ``redact`` from the redact_secrets.py beside this script.

    The file is a byte-identical copy of the spec skill's redactor, so an
    installed plugin needs no toolkit checkout. Loading it by path, not by
    module name, keeps a same-named module on sys.path from replacing it.
    """
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "redact_secrets.py")
    spec = importlib.util.spec_from_file_location("_new_issue_redact_secrets", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load bundled redactor: {path}")
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolves a class's module through sys.modules while the
    # module body runs, so register it first.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.redact


redact = _load_bundled_redact()


SOURCES = ("human", "agent")
SOURCE_LABELS = frozenset(f"source:{source}" for source in SOURCES)

# Phrase column of the canonical hedge phrase list, copied verbatim and in order
# from skills/spec-generator/references/spec-step0-gates.md (the table that ends
# at the <!-- step0:hedge-table-end --> marker). Match rule, quoted from that
# file: "Case-insensitive word-boundary match: `\bphrase\b`".
HEDGE_PHRASES = (
    "would be nice",
    "would be useful",
    "would be helpful",
    "we believe",
    "we expect",
    "we anticipate",
    "we predict",
    "we hope",
    "we assume",
    "stakeholders want",
    "users want",
    "customers want",
    "should we",
    "might be useful",
    "might be needed",
    "could be useful",
    "probably",
    "eventually",
    "someday",
    "down the road",
    "nice to have",
)

# The same file exempts the technical term `eventually-consistent`. Its gate
# parser keys the exemption by phrase and lists eight entries, "consistent"
# plus seven single-punctuation variants:
#     "eventually": {"consistent", "consistent.", "consistent,", ...}
# Different than canonical: this script strips trailing punctuation before the
# lookup instead of enumerating it, so "consistent.)" is exempt here too.
_HEDGE_TECHNICAL_SUFFIXES = {"eventually": frozenset({"consistent"})}
_TRAILING_PUNCTUATION = ".,;:)!?"

# ATX headings may be indented up to three spaces and still render. Step 0
# means "Step 0" but not "Step 0.5" or "Step 01", in any case.
_STEP0_HEADING = re.compile(
    r"^[ \t]{0,3}##[ \t]+Step 0(?![.\w])[^\n]*$", re.MULTILINE | re.IGNORECASE
)
# A level-1 or level-2 heading ends the Step 0 section.
_SECTION_END = re.compile(r"^[ \t]{0,3}#{1,2}[ \t]", re.MULTILINE)
# A heading of level 1 to 3 ends an answer, or could forge a Q3/Q5 subsection.
_ANSWER_END_HEADING = r"^[ \t]{0,3}#{1,3}[ \t]"
_HEADING_LINE = re.compile(_ANSWER_END_HEADING, re.MULTILINE)
_STEP0_KEYS = ("Q3", "Q5")
# HTML comments and fenced code blocks, closed or running to the end of the
# body. GitHub renders neither as headings, so Step 0 text inside them is not
# evidence a reader can see.
_HIDDEN_MARKDOWN = re.compile(
    r"<!--.*?(?:-->|\Z)|^[ \t]*(```|~~~).*?(?:^[ \t]*\1[^\n]*$|\Z)",
    re.MULTILINE | re.DOTALL,
)
# Text after a hedge match that is inspected for the technical-term suffix.
_SUFFIX_WINDOW = 64

def _is_technical_term(phrase: str, text_after: str) -> bool:
    words = text_after.lstrip(" \t-").split(maxsplit=1)
    first_word = words[0].rstrip(_TRAILING_PUNCTUATION) if words else ""
    return first_word in _HEDGE_TECHNICAL_SUFFIXES.get(phrase, frozenset())


def hedge_match(text: str) -> str | None:
    """Return the first canonical hedge phrase in ``text``, or None."""
    lowered = text.lower()
    for phrase in HEDGE_PHRASES:
        matches = re.finditer(r"\b" + re.escape(phrase) + r"\b", lowered)
        if any(
            not _is_technical_term(phrase, lowered[m.end() : m.end() + _SUFFIX_WINDOW])
            for m in matches
        ):
            return phrase
    return None


def answer_error(field: str, answer: str, required_when: str) -> str | None:
    """Validate one Step 0 answer: present, heading-free, hedge-free."""
    if not answer.strip():
        return f"{field} is required when {required_when}"
    if _HEADING_LINE.search(answer):
        return f"{field} must not contain a Markdown heading line"
    phrase = hedge_match(answer)
    if phrase:
        return f"{field} contains hedge phrase '{phrase}'"
    return None


def _step0_section(body: str) -> str | None:
    """Return the visible text under the body's ``## Step 0`` heading, or None."""
    visible = _HIDDEN_MARKDOWN.sub("", body)
    heading = _STEP0_HEADING.search(visible)
    if heading is None:
        return None
    rest = visible[heading.end() :]
    next_section = _SECTION_END.search(rest)
    return rest[: next_section.start()] if next_section else rest


def _step0_answer(section: str, key: str) -> str:
    """Return the text under ``### <key>`` inside a Step 0 section."""
    match = re.search(
        rf"^[ \t]{{0,3}}###[ \t]+{key}\b[^\n]*\n(.*?)(?={_ANSWER_END_HEADING}|\Z)",
        section,
        re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    return match.group(1).strip() if match else ""


def _body_evidence_error(source: str, section: str, blocked_by: str, signal: str) -> str | None:
    if blocked_by.strip() or signal.strip():
        return "Body already carries a Step 0 block; drop --blocked-by and --signal."
    required_when = "--source=agent" if source == "agent" else "the body carries a Step 0 block"
    for key in _STEP0_KEYS:
        error = answer_error(f"Step 0 ### {key}", _step0_answer(section, key), required_when)
        if error:
            return error
    return None


def _render_step0(blocked_by: str, signal: str) -> str:
    q3 = redact(blocked_by.strip()).text
    q5 = redact(signal.strip()).text
    return f"## Step 0\n\n### Q3\n\n{q3}\n\n### Q5\n\n{q5}\n"


def _flag_evidence(source: str, blocked_by: str, signal: str) -> tuple[str | None, str]:
    if source != "agent" and not (blocked_by.strip() or signal.strip()):
        return None, ""
    answers = (("--blocked-by", blocked_by, "--signal"), ("--signal", signal, "--blocked-by"))
    for flag, answer, other_flag in answers:
        required_when = "--source=agent" if source == "agent" else f"{other_flag} is given"
        error = answer_error(flag, answer, required_when)
        if error:
            return error, ""
    return None, _render_step0(blocked_by, signal)


def step0_evidence(source: str, body: str, blocked_by: str, signal: str) -> tuple[str | None, str]:
    """Validate Step 0 evidence from the body or the flags, never both.

    Returns ``(error, block)``: an error message, or the rendered Step 0 block
    to append (empty when the body already carries one or none is needed).
    """
    section = _step0_section(body)
    if section is not None:
        return _body_evidence_error(source, section, blocked_by, signal), ""
    return _flag_evidence(source, blocked_by, signal)


def split_source_labels(labels: str, source: str) -> tuple[str | None, str]:
    """Return ``(error, caller labels minus the source label)``.

    GitHub label names are case-insensitive, so ``SOURCE:AGENT`` counts.
    """
    expected = f"source:{source}"
    kept: list[str] = []
    for label in (part.strip() for part in labels.split(",")):
        lowered = label.lower()
        if lowered in SOURCE_LABELS and lowered != expected:
            return f"--labels carries {lowered}, which conflicts with --source {source}", ""
        if label and lowered not in SOURCE_LABELS:
            kept.append(label)
    return None, ",".join(kept)


_SOURCE_LABEL_COLOR = "ededed"
_SOURCE_LABEL_DESCRIPTIONS = {
    "human": "Work selected by an explicit human request",
    "agent": "Work selected by an agent",
}


def ensure_source_label(owner: str, repo: str, label: str, source: str) -> None:
    """Create the source label in the target repository when it is missing.

    Best effort by design. ``gh issue create --label`` resolves every label
    name before it sends the create mutation and fails with "could not add
    label" when one is missing, so the create call is the fail-closed point:
    a failure here (no triage permission, timeout) cannot leave an unlabeled
    issue, it only lets the create call report the missing label.
    """
    gh_args = [
        "gh",
        "label",
        "create",
        label,
        "--repo",
        f"{owner}/{repo}",
        "--color",
        _SOURCE_LABEL_COLOR,
        "--description",
        _SOURCE_LABEL_DESCRIPTIONS[source],
    ]
    try:
        result = subprocess.run(
            gh_args,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        print(f"Could not ensure label {label}: {exc}", file=sys.stderr)
        return

    detail = (result.stderr or result.stdout or "").strip()
    if result.returncode != 0 and "already exists" not in detail.lower():
        print(f"Could not ensure label {label}: {detail}", file=sys.stderr)
