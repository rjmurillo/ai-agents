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

# Fields a Copilot custom agent file must declare as non-empty strings: Copilot
# needs name/description to register and select the agent (issue #2500). ``tier``
# is checked only when present (see find_malformed), per the issue's "if the
# repository requires it" qualifier.
_REQUIRED_STRING_FIELDS = ("name", "description")
_OPTIONAL_STRING_FIELDS = ("tier",)

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parents[1]
for _path in (_REPO_ROOT, _SCRIPT_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))


def parse_frontmatter(text: str) -> dict[str, object] | None:
    """Return parsed frontmatter using the canonical validation parser.

    ``pre_pr`` re-exports this helper for compatibility, but importing the
    source module avoids loading the full pre-PR runner here.
    """
    from scripts.validation.yaml_utils import _parse_yaml_frontmatter

    return _parse_yaml_frontmatter(text)


def find_malformed(agents_dir: Path) -> list[tuple[Path, str]]:
    """Return (path, error) for each agent file whose frontmatter is invalid.

    Catches (issues #2491-#2497, #2500):
    1. No frontmatter block, or YAML that does not parse. The message carries the
       YAML parser error so the offending line is actionable.
    2. Frontmatter that is not a mapping.
    3. A missing or non-string ``name``/``description`` (Copilot needs both to
       register and select the agent); a non-string ``tier`` when present.

    A colon-bearing description authored as an unquoted plain scalar fails class 1
    here exactly as it does in Copilot, which is the regression these issues fix.
    """

    offenders: list[tuple[Path, str]] = []
    for path in sorted(agents_dir.glob("*.agent.md")):
        text = path.read_text(encoding="utf-8")
        block = _raw_frontmatter(text)
        if block is None:
            offenders.append((path, "no YAML frontmatter block found"))
            continue
        try:
            parsed = yaml.safe_load(block)
        except yaml.YAMLError as exc:
            detail = str(exc).replace("\n", " ").strip()
            offenders.append((path, f"invalid YAML frontmatter: {detail}"))
            continue
        if not isinstance(parsed, dict):
            offenders.append((path, "frontmatter is not a YAML mapping"))
            continue
        missing = [
            field
            for field in _REQUIRED_STRING_FIELDS
            if not isinstance(parsed.get(field), str) or not parsed[field].strip()
        ]
        if missing:
            offenders.append(
                (path, f"missing or non-string field(s): {', '.join(missing)}")
            )
            continue
        bad_optional = [
            field
            for field in _OPTIONAL_STRING_FIELDS
            if field in parsed and not isinstance(parsed[field], str)
        ]
        if bad_optional:
            offenders.append((path, f"non-string field(s): {', '.join(bad_optional)}"))
    return offenders





def _raw_frontmatter(text: str) -> str | None:
    """Return the raw text between the first two ``---`` fences, or None."""

    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[1:i])
    return None


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
