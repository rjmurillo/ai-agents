#!/usr/bin/env python3
"""Read-only probes for the ai-agents-architecture-contract skill.

  contract_probe.py --repo . adrs [--adr ADR-072 ...]
  contract_probe.py --repo . guard

`adrs` reads the frontmatter of each ADR the skill cites (or each --adr given)
under .project-toolkit/architecture/ADR-*.md and prints status, superseded-by,
and the implemented flag. `guard` finds the definition and call sites of
assert_no_claude_writes in build/scripts and tests. Both print JSON with an
`examined` count. Exit codes: 0 ok, 1 findings (a cited ADR has no file, or the
guard has no definition), 2 bad arguments or configuration, 3 external failure
(a file could not be read).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SKILL = "ai-agents-architecture-contract"
ADR_DIR = ".project-toolkit/architecture"
ADR_RE = re.compile(r"\bADR-(\d{2,3})\b")
GUARD = "assert_no_claude_writes"
FIELDS = ("status", "superseded-by", "implemented", "date")


def parse_frontmatter(text: str) -> dict[str, str]:
    """Return key/value pairs from the first `---` block. Comments are skipped."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    out: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.lstrip().startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        out[key.strip()] = value.strip()
    return out


def cited_adrs(repo: Path) -> list[str]:
    """Return sorted ADR ids named in the skill's SKILL.md and references."""
    root = repo / ".claude" / "skills" / SKILL
    files = [root / "SKILL.md", *sorted((root / "references").glob("*.md"))]
    found: set[str] = set()
    for path in files:
        if path.is_file():
            found.update(f"ADR-{n}" for n in ADR_RE.findall(path.read_text(encoding="utf-8")))
    return sorted(found)


def probe_adrs(repo: Path, wanted: list[str]) -> tuple[dict[str, Any], int]:
    adr_dir = repo / ADR_DIR
    if not adr_dir.is_dir():
        raise FileNotFoundError(f"{ADR_DIR} not found under {repo}")
    ids = wanted or cited_adrs(repo)
    rows, missing = [], []
    for adr_id in ids:
        paths = sorted(adr_dir.glob(f"{adr_id}-*.md"))
        if not paths:
            missing.append(adr_id)
            continue
        for path in paths:
            fm = parse_frontmatter(path.read_text(encoding="utf-8"))
            rows.append(
                {
                    "id": adr_id,
                    "path": path.relative_to(repo).as_posix(),
                    "status": fm.get("status"),
                    "superseded_by": None
                    if fm.get("superseded-by") in (None, "null")
                    else fm["superseded-by"],
                    "implemented": fm.get("implemented"),
                    "date": fm.get("date"),
                }
            )
    return {"adrs": rows, "missing": missing, "examined": len(ids)}, 1 if missing else 0


def probe_guard(repo: Path) -> tuple[dict[str, Any], int]:
    roots = [repo / "build" / "scripts", repo / "tests"]
    definitions, calls = [], []
    examined = 0
    for root in roots:
        for path in sorted(root.rglob("*.py")) if root.is_dir() else []:
            examined += 1
            rel = path.relative_to(repo).as_posix()
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if GUARD not in line:
                    continue
                entry = {"file": rel, "line": number}
                if re.match(rf"\s*def {GUARD}\(", line):
                    definitions.append(entry)
                elif f"{GUARD}(" in line:
                    calls.append(entry)
    result = {"definitions": definitions, "calls": calls, "examined": examined}
    return result, 0 if definitions else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default=".", help="repository root (default: .)")
    sub = parser.add_subparsers(dest="command", required=True)
    adrs = sub.add_parser("adrs", help="status of each cited ADR")
    adrs.add_argument("--adr", action="append", default=[], help="ADR id such as ADR-072")
    sub.add_parser("guard", help="locate assert_no_claude_writes")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo = Path(args.repo)
    if not repo.is_dir():
        print(f"error: --repo {args.repo} is not a directory", file=sys.stderr)
        return 2
    try:
        if args.command == "adrs":
            bad = [a for a in args.adr if not re.fullmatch(r"ADR-\d{2,3}", a)]
            if bad:
                print(f"error: bad ADR id {bad[0]} (use ADR-NNN)", file=sys.stderr)
                return 2
            result, code = probe_adrs(repo, args.adr)
        else:
            result, code = probe_guard(repo)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (OSError, UnicodeDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3
    print(json.dumps(result, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
