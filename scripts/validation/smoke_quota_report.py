#!/usr/bin/env python3
"""Report the quota-skipped smoke checks of a passing leg (REQ-047 D25, D26).

``assert_smoke_ran.py`` lets a prompt-based check skip with ``QUOTA_SKIP:`` when
the provider budget is spent, so the skip must stay visible. After the gate
passes, a workflow step runs this script on the same JUnit report. It

- prints a ``::notice::`` line naming each skipped check and its reason,
- appends the same line to ``GITHUB_STEP_SUMMARY`` when that is set, and
- with ``--skip-count-file PATH``, appends the skip count (0 when none) as one
  line. The workflow uploads the file per leg and ``CLI Smoke Result`` sums them.

A skip counts only when its ``message`` STARTS WITH the marker, the same prefix
rule the gate applies. The script is stdlib-only and runs with ``python -I``.

Exit codes (ADR-035): 0 reported, 2 usage or an unreadable or hostile report.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from xml.etree import ElementTree

EXIT_OK = 0
EXIT_CONFIG = 2

_PHRASE = "best-effort test(s) quota-skipped by marker"
_MAX_REASON = 200


def quota_skips(report: Path, smoke_substr: str, marker: str) -> list[str]:
    """Return ``id (reason)`` for each smoke case skipped with the marker prefix.

    Raises ``ValueError`` on an unreadable report, bad XML, or a DTD or entity
    declaration (CWE-611, CWE-776): pytest never writes one.
    """
    try:
        text = report.read_text(encoding="utf-8")
        if "<!doctype" in text.lower() or "<!entity" in text.lower():
            raise ValueError(f"report declares a DTD or entity; refusing to parse {report}")
        cases = ElementTree.fromstring(text).iter("testcase")
    except (OSError, ElementTree.ParseError) as exc:
        raise ValueError(f"report could not be read as XML: {report}: {exc}") from exc
    found = []
    for case in cases:
        classname, name = case.get("classname", ""), case.get("name", "")
        case_id = f"{classname}::{name}" if classname else name
        skipped = case.find("skipped")
        if smoke_substr in case_id and skipped is not None:
            reason = skipped.get("message", "")
            if reason.lstrip().startswith(marker):
                found.append(f"{case_id} ({reason.strip()[:_MAX_REASON]})")
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("report", type=Path, help="JUnit XML report from the smoke pytest run.")
    parser.add_argument("--smoke-substr", default="test_cli_hook_e2e")
    parser.add_argument("--allow-skip-marker", required=True, help="Skip message prefix.")
    parser.add_argument("--skip-count-file", type=Path, help="Append the skip count here.")
    args = parser.parse_args(argv)
    marker: str = args.allow_skip_marker
    try:
        skips = quota_skips(args.report, args.smoke_substr, marker)
    except ValueError as exc:
        print(f"::error::smoke quota report: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    if skips:
        note = f"{len(skips)} {_PHRASE} {marker!r}: {'; '.join(skips)}."
        print(f"::notice::smoke gate: {note}")
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a", encoding="utf-8") as handle:
                handle.write(f"Prompt checks were quota-skipped. {note}\n")
    if args.skip_count_file:
        with args.skip_count_file.open("a", encoding="utf-8") as handle:
            handle.write(f"{len(skips)}\n")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
