"""Rebuild verification for the requirements-interview audit mode.

Checks a rebuilt specification against the original and the decision log: each
accepted decision lands exactly once, superseded text is gone, unresolved
decisions stay explicit, and no unaffected source line was deleted.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from audit_source import normalize, parse_sections, resolve_anchor, section_body

OUTCOMES = frozenset({"accepted", "open"})
OPEN_SECTION = "open decisions"


def _lines(text: str) -> list[str]:
    return text.splitlines()


def _open_section_body(rebuilt_lines: list[str]) -> str | None:
    for section in parse_sections(rebuilt_lines):
        if section.heading.lower() == OPEN_SECTION:
            return section_body(rebuilt_lines, section)
    return None


def _accepted_problems(entry: dict[str, Any], source_norm: str, rebuilt_norm: str) -> list[str]:
    text = normalize(str(entry.get("text", "")))
    if not text:
        return ["text: an accepted decision needs the exact text it adds"]
    problems: list[str] = []
    count = rebuilt_norm.count(text)
    if count != 1:
        problems.append(f"text appears {count} times in the rebuilt document, expected exactly 1")
    if text in source_norm:
        problems.append("text already exists in the source, so it proves nothing")
    replaces = [normalize(str(q)) for q in entry.get("replaces") or []]
    for quote in replaces:
        if quote not in source_norm:
            problems.append(f"replaces: {quote!r} is not in the source")
        elif quote in rebuilt_norm:
            problems.append(f"replaces: {quote!r} is still in the rebuilt document")
    return problems


def _open_problems(
    entry: dict[str, Any], anchor_texts: list[str], rebuilt_norm: str, open_body: str | None
) -> list[str]:
    if open_body is None:
        return ["the rebuilt document has no 'Open decisions' section"]
    problems: list[str] = []
    uses = len(re.findall(rf"\b{re.escape(entry['id'])}\b", open_body))
    if uses != 1:
        problems.append(f"id appears {uses} times under 'Open decisions', expected exactly 1")
    problems.extend(
        f"anchor text was removed without a decision: {text!r}"
        for text in anchor_texts
        if text not in rebuilt_norm
    )
    return problems


def _entry_problems(
    entry: dict[str, Any], candidate: dict[str, Any], texts: dict[str, str], open_body: str | None
) -> list[str]:
    outcome = entry.get("outcome")
    if outcome not in OUTCOMES:
        return [f"outcome: must be one of {sorted(OUTCOMES)}"]
    if outcome == "open":
        return _open_problems(entry, candidate["_anchor_texts"], texts["rebuilt"], open_body)
    problems = _accepted_problems(entry, texts["source"], texts["rebuilt"])
    if candidate["category"] == "contradiction" and not entry.get("replaces"):
        problems.append("replaces: an accepted contradiction must supersede one side")
    return problems


def _with_anchor_texts(candidates: list[dict[str, Any]], source_lines: list[str]) -> None:
    sections = parse_sections(source_lines)
    for candidate in candidates:
        candidate["_anchor_texts"] = [
            normalize(resolve_anchor(a, source_lines, sections)[1]) for a in candidate["anchors"]
        ]


def _preservation_problems(source: str, rebuilt: str, replaced: list[str]) -> list[str]:
    needles = [normalize(q) for q in replaced if normalize(q)]
    keep = Counter(
        normalize(line)
        for line in _lines(source)
        if normalize(line) and not any(n in normalize(line) for n in needles)
    )
    have = Counter(normalize(line) for line in _lines(rebuilt) if normalize(line))
    lost = [line for line, count in keep.items() if have[line] < count]
    return [f"unaffected source line deleted: {line!r}" for line in lost]


def verify_rebuild(
    candidates: list[dict[str, Any]], log: list[dict[str, Any]], source: str, rebuilt: str
) -> dict[str, Any]:
    """Verify the rebuilt document. Growth is reported, never scored."""

    asked = {c["id"]: c for c in candidates if c["disposition"] == "ask"}
    _with_anchor_texts(list(asked.values()), _lines(source))
    by_id = {str(e.get("id")): e for e in log}
    texts = {"source": normalize(source), "rebuilt": normalize(rebuilt)}
    open_body = _open_section_body(_lines(rebuilt))
    problems: list[dict[str, str]] = []
    problems.extend({"id": i, "problem": "no decision log entry"} for i in asked if i not in by_id)
    problems.extend(
        {"id": i, "problem": "log entry matches no ask candidate"} for i in by_id if i not in asked
    )
    for cid, entry in by_id.items():
        if cid in asked:
            found = _entry_problems(entry, asked[cid], texts, open_body)
            problems.extend({"id": cid, "problem": p} for p in found)
    replaced = [q for e in log if e.get("outcome") == "accepted" for q in e.get("replaces") or []]
    problems.extend(
        {"id": "preservation", "problem": p}
        for p in _preservation_problems(source, rebuilt, replaced)
    )
    return {
        "status": "failed" if problems else "verified",
        "problems": problems,
        "decision_log": _decision_log(asked, by_id),
        "growth": {
            "source_chars": len(source),
            "rebuilt_chars": len(rebuilt),
            "delta_chars": len(rebuilt) - len(source),
            "note": "observation only, not a quality metric",
        },
    }


def _decision_log(
    asked: dict[str, dict[str, Any]], by_id: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    return [
        {"id": cid, "outcome": by_id[cid].get("outcome"), "anchors": c["anchors"]}
        for cid, c in asked.items()
        if cid in by_id
    ]
