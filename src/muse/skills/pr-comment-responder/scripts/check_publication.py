#!/usr/bin/env python3
"""Check published review comments against the validated findings they render.

Deterministic gate for two rules in references/review-conversation.md
(Publishing a finding, Exemplary AI standard): publication never changes a
finding's disposition, and duplicate AI comments are not published.

Input is a JSON file::

    {"findings": [{"id": "F1", "disposition": "BLOCKING"}],
     "comments": [{"finding_id": "F1", "path": "a.py", "line": 3,
                   "body": "Unbounded retry loop. Why: ..."}]}

The prefix table below mirrors the Publishing table in the protocol, which is
the one owner of the mapping. tests/skills/pr-comment-responder/
test_check_publication.py reads that table and fails if the two differ.

Exit codes follow ADR-035:
    0 - Every comment renders its finding's disposition and none duplicate
    1 - At least one violation (listed in the JSON report)
    2 - Config/usage error (unreadable file, malformed input)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# Disposition -> comment prefix. BLOCKING carries no prefix.
PREFIXES: dict[str, str] = {
    "BLOCKING": "",
    "OPTIONAL": "Optional:",
    "NIT": "Nit:",
    "FYI": "FYI:",
}

_PREFIXED = {prefix.lower(): name for name, prefix in PREFIXES.items() if prefix}
_PREFIX_RE = re.compile(r"^\s*(optional:|nit:|fyi:)", re.IGNORECASE)
_WHITESPACE_RE = re.compile(r"\s+")


class InputError(ValueError):
    """The input file does not match the documented shape."""


def rendered_disposition(body: str) -> str:
    """Return the disposition a comment body renders to its reader."""
    match = _PREFIX_RE.match(body)
    if match is None:
        return "BLOCKING"
    return _PREFIXED[match.group(1).lower()]


def _normalize(body: str) -> str:
    return _WHITESPACE_RE.sub(" ", body).strip().lower()


def _violation(kind: str, comment_index: int, detail: str) -> dict[str, Any]:
    return {"kind": kind, "comment_index": comment_index, "detail": detail}


def _require_list(data: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = data.get(key)
    if not isinstance(value, list) or not all(isinstance(i, dict) for i in value):
        raise InputError(f"'{key}' must be a list of objects")
    return value


def _finding_dispositions(findings: list[dict[str, Any]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for finding in findings:
        fid, disposition = finding.get("id"), finding.get("disposition")
        if not isinstance(fid, str) or not fid:
            raise InputError("every finding needs a non-empty string 'id'")
        if not isinstance(disposition, str) or disposition not in PREFIXES:
            raise InputError(f"finding '{fid}' has unknown disposition {disposition!r}")
        if fid in result:
            raise InputError(f"finding id '{fid}' appears twice")
        result[fid] = disposition
    return result


def _comment_body(comment: dict[str, Any], index: int) -> str:
    body = comment.get("body")
    if not isinstance(body, str) or not body.strip():
        raise InputError(f"comment {index} needs a non-empty string 'body'")
    return body


def _check_comment(
    index: int,
    comment: dict[str, Any],
    dispositions: dict[str, str],
    seen_findings: set[str],
    seen_bodies: set[tuple[str, str, str]],
) -> list[dict[str, Any]]:
    body = _comment_body(comment, index)
    fid = comment.get("finding_id")
    violations: list[dict[str, Any]] = []
    if not isinstance(fid, str) or fid not in dispositions:
        violations.append(_violation("unknown_finding", index, f"no finding {fid!r}"))
    else:
        expected, actual = dispositions[fid], rendered_disposition(body)
        if expected != actual:
            violations.append(
                _violation(
                    "severity_mutation",
                    index,
                    f"finding is {expected}, comment renders {actual}",
                )
            )
        if fid in seen_findings:
            violations.append(_violation("duplicate", index, f"finding {fid} published twice"))
        seen_findings.add(fid)
    key = (repr(comment.get("path")), repr(comment.get("line")), _normalize(body))
    if key in seen_bodies:
        violations.append(
            _violation("duplicate", index, "same path, line, and text as an earlier comment")
        )
    seen_bodies.add(key)
    return violations


def check_publication(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Return every violation found in ``data``; an empty list means clean."""
    dispositions = _finding_dispositions(_require_list(data, "findings"))
    comments = _require_list(data, "comments")
    seen_findings: set[str] = set()
    seen_bodies: set[tuple[str, str, str]] = set()
    violations: list[dict[str, Any]] = []
    for index, comment in enumerate(comments):
        violations.extend(_check_comment(index, comment, dispositions, seen_findings, seen_bodies))
    return violations


def _load(path: str) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InputError(f"cannot read {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise InputError("top-level JSON must be an object")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("input", help="JSON file with 'findings' and 'comments'")
    args = parser.parse_args(argv)
    try:
        violations = check_publication(_load(args.input))
    except InputError as exc:
        print(f"check_publication: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"violations": violations, "count": len(violations)}, indent=2))
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
