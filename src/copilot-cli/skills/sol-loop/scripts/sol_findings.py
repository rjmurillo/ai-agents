"""Finding rules for sol-loop: parse Sol's reply, filter it, mark overlap.

Pure functions with no I/O, so ``sol_loop.py`` stays a thin command layer.

Sol replies in the line format the sol-loop brief asks for:

    VERDICT: APPROVE or CHANGES
    S1 [blocker|should|nit] <file>:<line> <claim>. Repro: <repro>. Fix: <fix>

A finding is kept only when it is a ``blocker`` or ``should`` with a file, a
line, and a repro. A ``nit`` is dropped (style and other nits are out of
scope). A kept finding is ``sol_only`` unless the fresh critic cited a nearby
location.
"""

from __future__ import annotations

import re

OVERLAP_LINE_WINDOW = 3
KEPT_SEVERITIES = ("blocker", "should")
SEVERITIES = (*KEPT_SEVERITIES, "nit")

_VERDICT = re.compile(r"^\s*\**\s*VERDICT\s*:\s*\**\s*(APPROVE|CHANGES)\b", re.I | re.M)
# Any bracketed label counts, so a finding tagged [P1] or [major] is parsed and
# then dropped with a reason instead of vanishing. A list marker ("-", "*", or
# "1.") may lead the line.
_FINDING = re.compile(r"^\s*(?:[-*]|\d+[.)])?\s*\**(S\d+)\**\s*\[([^\]\n]+)\]\s*(.*)$")
# An optional drive letter keeps a Windows path such as C:\repo\a.py:12 whole.
_LEADING_LOCATION = re.compile(r"^`?((?:/?[A-Za-z]:[\\/])?[^\s`:\[\]()]+)(?::|#L)(\d+)`?\s*(.*)$")
# Sol often cites a location as a markdown link: [file.py:12](/abs/path/file.py:12).
# The link target carries the full path, so it wins over the label.
_LINK_LOCATION = re.compile(r"^\[([^\]\n]+)\]\(<?([^)>\s]+)>?\)\s*(.*)$")
# An optional ":col" after the line is allowed, so "f.py:12:5" is line 12.
_PATH_LINE = re.compile(r"^`?(.+?)`?(?::|#L)(\d+)(?::\d+)?(?:-L?\d+)?$")
_REPRO = re.compile(r"\bRepro:\s*(.*?)(?=\s*\bFix:|$)", re.I)
_FIX = re.compile(r"\bFix:\s*(.*)$", re.I)


class ReplyError(ValueError):
    """Sol's reply has no ``VERDICT:`` line, so it is not a review."""


def _location(rest: str) -> tuple[str, int | None, str]:
    """Return (file, line, remaining text) from the start of a finding's text."""
    link = _LINK_LOCATION.match(rest)
    if link:
        for candidate in (link.group(2), link.group(1)):
            parts = _PATH_LINE.match(candidate)
            if parts:
                return parts.group(1), int(parts.group(2)), link.group(3)
        return "", None, link.group(3)
    plain = _LEADING_LOCATION.match(rest)
    if plain:
        return plain.group(1), int(plain.group(2)), plain.group(3)
    return "", None, rest


def _parse_finding(fid: str, severity: str, rest: str) -> dict:
    file_value, line, body = _location(rest.strip())
    repro = _REPRO.search(body)
    fix = _FIX.search(body)
    claim = body[: repro.start()] if repro else body[: fix.start()] if fix else body
    return {
        "id": fid,
        "severity": severity.strip().lower(),
        "file": file_value,
        "line": line,
        "claim": claim.strip().rstrip("."),
        "repro": repro.group(1).strip().rstrip(".") if repro else "",
        "fix": fix.group(1).strip() if fix else "",
    }


def parse_reply(text: str) -> tuple[str, list[dict]]:
    """Return (verdict, findings) from Sol's reply. Raises ReplyError without a verdict."""
    verdict = _VERDICT.search(text)
    if not verdict:
        raise ReplyError("reply has no 'VERDICT: APPROVE' or 'VERDICT: CHANGES' line")
    findings = []
    for raw_line in text.splitlines():
        match = _FINDING.match(raw_line)
        if match:
            findings.append(_parse_finding(match.group(1), match.group(2), match.group(3)))
    return verdict.group(1).upper(), findings


def drop_reason(item: dict) -> str:
    """Why a finding is dropped, or "" when it is kept."""
    line = item.get("line")
    severity = str(item.get("severity") or "").strip().lower()
    if severity == "nit":
        return "nit"
    if severity not in KEPT_SEVERITIES:
        return "unknown-severity"
    if not str(item.get("file") or "").strip():
        return "missing-file"
    if not isinstance(line, int) or isinstance(line, bool) or line < 1:
        return "missing-line"
    if not str(item.get("repro") or "").strip():
        return "missing-repro"
    return ""


def filter_findings(raw: list[object]) -> tuple[list[dict], list[dict]]:
    """Split findings into kept and dropped. Dropped entries carry a reason."""
    kept: list[dict] = []
    dropped: list[dict] = []
    for item in raw:
        reason = drop_reason(item) if isinstance(item, dict) else "not-an-object"
        if reason:
            dropped.append({"reason": reason, "finding": item})
        else:
            kept.append(
                {**item, "file": str(item["file"]).strip(), "repro": str(item["repro"]).strip()}
            )
    return kept, dropped


# Matches `path:12`, `path:12-40`, `` `path`:12 ``, `path#L12`, and extensionless
# names such as `Makefile:10`. A false match only adds overlap. A critic citation
# with no line anchor is not matched, so the sol_only count is an estimate.
_LOCATION = re.compile(r"([A-Za-z0-9_./\\-]*[A-Za-z0-9_])`?(?::|#L)(\d+)(?:-L?(\d+))?")


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
    file name) counts as the same file. That errs toward overlap, but a critic
    citation with no line anchor is missed, so ``sol_only`` is an estimate.
    """
    cited = critic_locations(critic_text)
    window = OVERLAP_LINE_WINDOW

    def near(finding: dict) -> bool:
        return any(
            _same_file(finding["file"], path) and start - window <= finding["line"] <= end + window
            for path, start, end in cited
        )

    return [{**finding, "sol_only": not near(finding)} for finding in findings]
