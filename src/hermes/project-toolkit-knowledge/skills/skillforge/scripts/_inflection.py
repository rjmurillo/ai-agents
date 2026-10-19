#!/usr/bin/env python3
"""
_inflection.py - Shared word-inflection helpers for skill discovery and triage

These helpers are used by:
- discover_skills.py (domain assignment)
- triage_skill_request.py (term matching and coverage)

One definition keeps the matcher and the coverage count in agreement: a query
that mentions "shipped" explains a skill that says "ship", in both places.
"""

from __future__ import annotations

import re

# Final consonants that double before "ing" and "ed" (debug -> debugging).
DOUBLING_CONSONANTS = frozenset("bdglmnprt")

_SUFFIXES = ("ing", "es", "ed", "s")
_MIN_STEM_LENGTH = 3


def has_term(text: str, term: str) -> bool:
    """
    True when term appears in text as a whole word or phrase, allowing inflection.

    Inflections are s, es, ing, and ed. A final consonant also doubles before ing
    and ed, so "debug" matches "debugging" and "ship" matches "shipped". The term
    never extends into another word: "test" does not match "attest".
    """
    term = term.lower()
    suffixes = ["s", "es", "ing", "ed"]
    if term and term[-1] in DOUBLING_CONSONANTS:
        suffixes += [re.escape(term[-1]) + "ing", re.escape(term[-1]) + "ed"]
    pattern = r"(?<![a-z0-9])" + re.escape(term) + r"(?:" + "|".join(suffixes) + r")?(?![a-z0-9])"
    return re.search(pattern, text.lower()) is not None


def stem_forms(token: str) -> set[str]:
    """
    Return the token plus each form with one inflectional suffix removed.

    After "ing" or "ed" is removed, a doubled final consonant is also collapsed
    (shipp -> ship, plann -> plan), the inverse of what has_term accepts.
    """
    forms = {token}
    for suffix in _SUFFIXES:
        if not token.endswith(suffix):
            continue
        stem = token[: -len(suffix)]
        if len(stem) < _MIN_STEM_LENGTH:
            continue
        forms.add(stem)
        if (
            suffix in ("ing", "ed")
            and len(stem) - 1 >= _MIN_STEM_LENGTH
            and stem[-1] == stem[-2]
            and stem[-1] in DOUBLING_CONSONANTS
        ):
            forms.add(stem[:-1])
    return forms
