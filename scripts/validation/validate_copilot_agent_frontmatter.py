#!/usr/bin/env python3
"""Validate that every Copilot custom-agent file has parseable YAML frontmatter.

Copilot loads `.github/agents/*.agent.md` by parsing the YAML frontmatter between
the leading `---` fences. A description authored as an unquoted plain scalar that
embeds colon-bearing example text (`Context:`, `user:`, `assistant:`, XML) makes
the parser read the examples as YAML mapping keys, so the whole agent fails to
load with "mapping values are not allowed in this context". Six agents shipped
that way and were silently unavailable to Copilot (issues #2491-#2496).

This gate parses each agent file's frontmatter exactly as a YAML loader would and
fails when any file is malformed, so the class cannot regress. The fix for an
offender is a quoted or block-scalar description (see the issues).

Exit codes follow ADR-035:
    0 - All Copilot agent files have valid YAML frontmatter
    1 - One or more files have malformed frontmatter
    2 - Config error (agents directory missing)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

_FENCE = "---"


def split_frontmatter(text: str) -> str | None:
    """Return the YAML frontmatter block of an agent file, or None if absent.

    The frontmatter is the text between the first two `---` fence lines. Returns
    None when the file does not open with a fence (no frontmatter to validate).
    """

    lines = text.splitlines()
    if not lines or lines[0].strip() != _FENCE:
        return None
    for i in range(1, len(lines)):
        if lines[i].strip() == _FENCE:
            return "\n".join(lines[1:i])
    return None


def find_malformed(agents_dir: Path) -> list[tuple[Path, str]]:
    """Return (path, error) for each agent file whose frontmatter does not parse.

    A file with no frontmatter is reported as malformed: a Copilot agent without a
    frontmatter block cannot declare its name/description and will not load.
    """

    offenders: list[tuple[Path, str]] = []
    for path in sorted(agents_dir.glob("*.agent.md")):
        text = path.read_text(encoding="utf-8")
        block = split_frontmatter(text)
        if block is None:
            offenders.append((path, "no YAML frontmatter block found"))
            continue
        try:
            parsed = yaml.safe_load(block)
        except yaml.YAMLError as err:
            offenders.append((path, str(err).splitlines()[0]))
            continue
        if not isinstance(parsed, dict) or not parsed.get("name"):
            offenders.append((path, "frontmatter missing required 'name' field"))
    return offenders


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate YAML frontmatter of .github/agents/*.agent.md files.",
    )
    parser.add_argument(
        "--agents-dir",
        default=".github/agents",
        help="Directory of Copilot agent files (default: .github/agents).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    agents_dir = Path(args.agents_dir)
    if not agents_dir.is_dir():
        print(f"[FAIL] agents directory not found: {agents_dir}", file=sys.stderr)
        return 2

    offenders = find_malformed(agents_dir)
    total = len(sorted(agents_dir.glob("*.agent.md")))
    if offenders:
        print(f"[FAIL] {len(offenders)} of {total} Copilot agent file(s) have malformed frontmatter:")
        for path, err in offenders:
            print(f"  - {path}: {err}")
        print(
            "Fix: quote the description or use a YAML block scalar "
            "(description: |-), or move colon-bearing examples into the body."
        )
        return 1

    print(f"[PASS] All {total} Copilot agent file(s) have valid YAML frontmatter.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
