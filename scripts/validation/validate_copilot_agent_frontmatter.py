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

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parents[1]
for _path in (_REPO_ROOT, _SCRIPT_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))


def parse_frontmatter(text: str) -> dict[str, object] | None:
    """Return parsed frontmatter using the canonical pre-PR parser.

    Importing lazily avoids a cycle when ``pre_pr`` imports the plugin checks that
    run this validator as a subprocess.
    """
    from scripts.validation.pre_pr import _parse_yaml_frontmatter

    return _parse_yaml_frontmatter(text)


def find_malformed(agents_dir: Path) -> list[tuple[Path, str]]:
    """Return (path, error) for each agent file whose frontmatter does not parse.

    A file with no frontmatter is reported as malformed: a Copilot agent without a
    frontmatter block cannot declare its name/description and will not load.
    """

    offenders: list[tuple[Path, str]] = []
    for path in sorted(agents_dir.glob("*.agent.md")):
        text = path.read_text(encoding="utf-8")
        parsed = parse_frontmatter(text)
        if not isinstance(parsed, dict) or not parsed.get("name"):
            offenders.append(
                (path, "frontmatter is malformed or missing required 'name' field")
            )
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
