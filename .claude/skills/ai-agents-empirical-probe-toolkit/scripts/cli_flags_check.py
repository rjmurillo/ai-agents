#!/usr/bin/env python3
"""Check that eval-harness flags named in SKILL.md are declared by the script they belong to.

  cli_flags_check.py --repo .

Reads SKILL.md, attributes each `--flag` to the last `scripts/...py` path named
before it (fenced command or prose), then parses that script with `ast` and
collects the string literals passed to `add_argument`. The script is never run.
A flag written after "no" (for example "there is no `--mock`") is a negation
and is skipped.

Exit codes: 0 every cited flag is declared, 1 an undeclared flag or missing
script, 2 bad arguments or unreadable input.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

SKILL = "ai-agents-empirical-probe-toolkit"
SCRIPT_RE = re.compile(r"(?:[\w.-]+/)*[\w.-]+\.py")
FLAG_RE = re.compile(r"(?<![\w-])(--[a-z][a-z0-9-]*)")
NEGATION_RE = re.compile(r"\bno\s+`?$", re.IGNORECASE)
EVAL_PREFIX = "scripts/eval/"
IMPLICIT = {"--help"}


def declared_flags(path: Path) -> set[str]:
    """Return every long option string passed to an add_argument call."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    flags: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "add_argument":
            for arg in node.args:
                if (
                    isinstance(arg, ast.Constant)
                    and isinstance(arg.value, str)
                    and arg.value.startswith("--")
                ):
                    flags.add(arg.value)
    return flags


def cited_flags(text: str) -> list[tuple[str, str, int]]:
    """Return (script, flag, line) for each flag attributed to an eval script."""
    out: list[tuple[str, str, int]] = []
    current: str | None = None
    for lineno, line in enumerate(text.splitlines(), 1):
        events = [(m.start(), "script", m.group(0)) for m in SCRIPT_RE.finditer(line)]
        events += [(m.start(), "flag", m.group(1)) for m in FLAG_RE.finditer(line)]
        for pos, kind, value in sorted(events):
            if kind == "script":
                current = value if EVAL_PREFIX in value else None
            elif current and not NEGATION_RE.search(line[:pos]):
                out.append((current, value, lineno))
    return out


def run(repo: Path, skill_md: Path) -> tuple[dict, int]:
    text = skill_md.read_text(encoding="utf-8")
    cites = cited_flags(text)
    cache: dict[str, set[str] | None] = {}
    checked, undeclared = [], []
    for script, flag, lineno in cites:
        if script not in cache:
            target = repo / script
            cache[script] = declared_flags(target) if target.is_file() else None
        flags = cache[script]
        row = {"script": script, "flag": flag, "line": lineno}
        if flags is None:
            undeclared.append({**row, "reason": "script missing"})
        elif flag not in flags and flag not in IMPLICIT:
            undeclared.append({**row, "reason": "flag not declared"})
        checked.append(row)
    report = {
        "skill": SKILL,
        "examined": len(checked),
        "scripts": sorted(cache),
        "undeclared": undeclared,
    }
    return report, 1 if undeclared else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--repo", default=".")
    parser.add_argument("--skill-md", help=f"default: <repo>/.claude/skills/{SKILL}/SKILL.md")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 0 if exc.code in (0, None) else 2
    repo = Path(args.repo)
    skill_md = (
        Path(args.skill_md) if args.skill_md else repo / ".claude" / "skills" / SKILL / "SKILL.md"
    )
    try:
        report, code = run(repo, skill_md)
    except (OSError, SyntaxError, UnicodeDecodeError) as exc:
        print(json.dumps({"error": str(exc), "examined": 0}), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
