"""Finding rules for the cross-family Sol pass: filter, overlap, failure class.

Pure functions with no I/O, so ``sol_pass.py`` stays a thin runner. A finding
is kept only with a file, a line, and a repro, and never as a style nit. A kept
finding is ``sol_only`` unless the critic cited a nearby location.
"""

from __future__ import annotations

import json
import re

OVERLAP_LINE_WINDOW = 3
STYLE_TOKENS = (
    "style",
    "nit",
    "naming",
    "format",
    "typo",
    "wording",
    "cosmetic",
    "readability",
    "whitespace",
)


_FAILURE_RULES = (
    (re.compile(r"not supported|unknown model|model_not_found", re.I), "model-unsupported"),
    (re.compile(r"\b(?:401|403)\b|unauthori[sz]ed|not logged in|login required", re.I), "auth"),
    (re.compile(r"rate.?limit|\b429\b", re.I), "rate-limit"),
    (re.compile(r"quota|usage limit", re.I), "quota"),
    (re.compile(r"\b5\d\d\b|server error|service unavailable|overloaded", re.I), "5xx"),
)


def classify_failure(message: str) -> str:
    """Map a CLI failure message to a failure class, ``unknown`` when unmatched."""
    return next((label for pattern, label in _FAILURE_RULES if pattern.search(message)), "unknown")


def failure_message(events_text: str, stderr: str) -> str:
    """Return the ``turn.failed`` message from Codex JSON events, else stderr."""
    for raw in events_text.splitlines():
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("type") == "turn.failed":
            return str((event.get("error") or {}).get("message", ""))
    return stderr.strip()[-500:]


def _drop_reason(item: dict) -> str:
    line = item.get("line")
    category = str(item.get("category") or "").lower()
    if not str(item.get("file") or "").strip():
        return "missing-file"
    if not isinstance(line, int) or isinstance(line, bool) or line < 1:
        return "missing-line"
    if not str(item.get("repro") or "").strip():
        return "missing-repro"
    if any(token in category for token in STYLE_TOKENS):
        return "style-nit"
    return ""


def filter_findings(raw: list[object]) -> tuple[list[dict], list[dict]]:
    """Split findings into kept and dropped. Dropped entries carry a reason."""
    kept: list[dict] = []
    dropped: list[dict] = []
    for item in raw:
        reason = _drop_reason(item) if isinstance(item, dict) else "not-an-object"
        if reason:
            dropped.append({"reason": reason, "finding": item})
        else:
            kept.append(
                {**item, "file": str(item["file"]).strip(), "repro": str(item["repro"]).strip()}
            )
    return kept, dropped


_LOCATION = re.compile(r"([A-Za-z0-9_./\\-]+\.[A-Za-z0-9]+):(\d+)(?:-(\d+))?")


def _norm_path(value: str) -> str:
    value = value.replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    return value


def critic_locations(critic_text: str) -> list[tuple[str, int, int]]:
    """Extract ``path:line`` and ``path:start-end`` locations the critic cited."""
    found = []
    for match in _LOCATION.finditer(critic_text):
        start = int(match.group(2))
        end = int(match.group(3)) if match.group(3) else start
        found.append((_norm_path(match.group(1)), min(start, end), max(start, end)))
    return found


def _same_file(a: str, b: str) -> bool:
    a, b = _norm_path(a), _norm_path(b)
    return a == b or a.endswith("/" + b) or b.endswith("/" + a)


def mark_sol_only(findings: list[dict], critic_text: str) -> list[dict]:
    """Flag each finding ``sol_only`` unless the critic cited a nearby location.

    A critic citation that names a shorter path suffix (for example a bare
    file name) counts as the same file. That errs toward overlap, so the
    ``sol_only`` count is a lower bound, never inflated.
    """
    cited = critic_locations(critic_text)
    window = OVERLAP_LINE_WINDOW

    def near(finding: dict) -> bool:
        return any(
            _same_file(finding["file"], path) and start - window <= finding["line"] <= end + window
            for path, start, end in cited
        )

    return [{**finding, "sol_only": not near(finding)} for finding in findings]
